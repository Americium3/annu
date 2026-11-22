from __future__ import annotations

import json
import math
import re
import sys
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(REPO_ROOT / "backend"),
    str(REPO_ROOT / "model" / "src"),
]

from carepath_model.condition_service import (  # noqa: E402
    ConditionMapping,
    ConditionServiceMapper,
)
from carepath_model.facility_reranker import (  # noqa: E402
    MODEL_VERSION as RERANKER_VERSION,
    rerank_condition_candidate,
)
from carepath_model.query import Urgency, detect_urgency, distance_weight  # noqa: E402
from carepath_model.taxonomy import normalize_text  # noqa: E402
from data_store import get_snapshot, haversine_km  # noqa: E402
from recommender import LocationNotFound, Recommender  # noqa: E402


SNAPSHOT_DIR = REPO_ROOT / "model" / "artifacts" / "cloud_snapshot"
RADIUS_STEPS_KM = (25.0, 50.0, 100.0, 200.0)
SERVICE_MODEL_VERSION = "service-catalog-local-v1"
CONDITION_MODEL_VERSION = "condition-service-local-v4"
RERANK_POOL_SIZE = 200

WEAK_FIELD_WEIGHTS = {
    "procedure": 0.55,
    "capability": 0.50,
    "equipment": 0.30,
}
WEAK_TIER_MULTIPLIERS = {1: 1.0, 2: 0.85, 3: 0.70}
FIELD_COLUMN_NAMES = {
    "procedure": "procedure_arr",
    "capability": "capability_arr",
    "equipment": "equipment_arr",
    "specialty": "specialties_std",
}
NEGATIVE_EVIDENCE_RE = re.compile(
    r"\b(no|not|without|unavailable|not available|does not|do not)\b"
    r"|没有|无|未提供|不可用",
    re.IGNORECASE,
)
EMERGENCY_WEAK_TEXT_RE = re.compile(
    r"\b(emergency|urgent|acute|critical|intensive|resuscitation|trauma|"
    r"stroke unit|thrombolysis|thrombectomy|24\s*/\s*7|24x7|heart attack|"
    r"angioplasty|catheteri[sz]ation|ventilat|icu|nicu|picu|"
    r"neurointervention)\b"
    r"|急诊|急救|重症|卒中中心|溶栓|取栓|24小时",
    re.IGNORECASE,
)
STROKE_ACUTE_RE = re.compile(
    r"\b(stroke unit|acute stroke|ischemic stroke|thrombolysis|thrombectomy|"
    r"neurointervention|neuro icu|neurointensive|24\s*/\s*7 stroke)\b"
    r"|卒中中心|溶栓|取栓|神经重症",
    re.IGNORECASE,
)
CARDIAC_ACUTE_RE = re.compile(
    r"\b(acute coronary|heart attack|myocardial infarction|angioplasty|pci|"
    r"cardiac catheteri[sz]ation|emergency cardiology|chest pain unit)\b"
    r"|急性冠脉|心梗|心肌梗死|急诊心",
    re.IGNORECASE,
)
TRAUMA_ACUTE_RE = re.compile(
    r"\b(trauma care|trauma centre|trauma center|fracture|head injury|"
    r"emergency department|24\s*/\s*7 emergency|emergency care)\b"
    r"|创伤|骨折|急诊|急救",
    re.IGNORECASE,
)
EMERGENCY_WEAK_SERVICE_IDS = {
    "tag:emergency-24x7",
    "tag:ambulance",
    "tag:icu",
    "tag:nicu",
    "tag:picu",
    "tag:ct-scan",
    "tag:x-ray",
    "tag:mri",
    "tag:ecg",
    "tag:echocardiography",
    "tag:angiography",
    "tag:angioplasty",
    "tag:blood-bank",
    "tag:pathology-lab",
    "tag:cardiac-surgery",
    "tag:neurosurgery",
}
CONDITION_WEAK_SERVICE_EXCLUSIONS = {"tag:vaccination"}
EVIDENCE_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]+")
EVIDENCE_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


class Coordinates(BaseModel):
    latitude: float
    longitude: float


class RecommendationRequest(BaseModel):
    conditionText: str | None = Field(default=None, min_length=1, max_length=2000)
    serviceText: str | None = Field(default=None, min_length=1, max_length=300)
    locationText: str = Field(default="", max_length=200)
    radiusKm: float | None = Field(default=None, ge=0, le=200)
    coordinates: Coordinates | None = None
    limit: int = Field(default=10, ge=1, le=30)


class LocalModel:
    def __init__(self) -> None:
        self.services = json.loads(
            (SNAPSHOT_DIR / "service_catalog.json").read_text(encoding="utf-8")
        )
        self.service_actions = json.loads(
            (SNAPSHOT_DIR / "service_action_map.json").read_text(encoding="utf-8")
        )
        self.facility_actions = json.loads(
            (SNAPSHOT_DIR / "facility_action_match.json").read_text(encoding="utf-8")
        )
        self.condition_edges = json.loads(
            (SNAPSHOT_DIR / "condition_action_edge.json").read_text(encoding="utf-8")
        )
        self.snapshot = get_snapshot()
        self.base_recommender = Recommender(self.snapshot)
        self.facilities = self.base_recommender.fac
        self.clinical_tags = self.snapshot.tags.to_dict(orient="records")
        self.clinical_tags_by_id = {
            str(tag.get("tag_id")): tag for tag in self.clinical_tags
        }
        self.emergency_facility_ids = set(
            self.snapshot.index.loc[
                self.snapshot.index["lists_emergency_24x7"] == True,  # noqa: E712
                "unique_id",
            ].astype(str)
        )
        self.condition_mapper = ConditionServiceMapper(
            self.condition_edges,
            self.service_actions,
            self.clinical_tags,
        )

        self.services_by_id = {
            str(service["service_id"]): service for service in self.services
        }
        self.services_by_tag_id = {
            service_id.removeprefix("tag:"): service
            for service_id, service in self.services_by_id.items()
            if service_id.startswith("tag:")
        }
        self.actions_by_service: dict[str, list[dict]] = defaultdict(list)
        for link in self.service_actions:
            self.actions_by_service[str(link["service_id"])].append(link)

        self.facility_actions_by_action: dict[str, list[dict]] = defaultdict(list)
        for match in self.facility_actions:
            self.facility_actions_by_action[str(match["action_id"])].append(match)

        self.tag_facilities: dict[str, list[dict]] = defaultdict(list)
        for row in self.snapshot.index.to_dict(orient="records"):
            if row.get("eligibility") == "formal":
                self.tag_facilities[str(row["tag_id"])].append(row)

        self.alias_index: dict[str, list[str]] = defaultdict(list)
        for service in self.services:
            service_id = str(service["service_id"])
            for alias in service.get("aliases") or [service["service_label"]]:
                normalized = normalize_text(str(alias))
                if normalized:
                    self.alias_index[normalized].append(service_id)

        self.condition_evidence: list[dict] = []
        self.condition_evidence_postings: dict[str, set[int]] = defaultdict(set)
        self._build_condition_evidence_index()

    def service_catalog(self) -> list[dict]:
        return sorted(
            self.services,
            key=lambda service: (
                -int(service.get("facility_count") or 0),
                str(service.get("service_label") or ""),
            ),
        )

    def resolve_service(self, text: str) -> tuple[dict, str, float]:
        normalized = normalize_text(text)
        exact = self.alias_index.get(normalized, [])
        if exact:
            service = self._best_service(exact)
            return service, service["service_label"], 1.0

        candidates: dict[str, float] = {}
        query_tokens = set(normalized.split())
        for alias, service_ids in self.alias_index.items():
            if len(alias) < 3:
                continue
            alias_tokens = set(alias.split())
            substring = alias in normalized or normalized in alias
            overlap = (
                len(query_tokens & alias_tokens) / max(len(query_tokens | alias_tokens), 1)
            )
            similarity = SequenceMatcher(None, normalized, alias).ratio()
            score = max(
                0.94 if substring else 0.0,
                0.85 * overlap,
                0.80 * similarity,
            )
            if score >= 0.55:
                for service_id in service_ids:
                    candidates[service_id] = max(candidates.get(service_id, 0.0), score)

        if not candidates:
            raise HTTPException(
                status_code=422,
                detail={
                    "field": "service",
                    "message": f"Could not map '{text}' to a service.",
                    "suggestions": [
                        service["service_label"] for service in self.service_catalog()[:8]
                    ],
                },
            )
        best_id = max(
            candidates,
            key=lambda service_id: (
                candidates[service_id],
                int(self.services_by_id[service_id].get("facility_count") or 0),
            ),
        )
        service = self.services_by_id[best_id]
        return service, service["service_label"], candidates[best_id]

    def _best_service(self, service_ids: list[str]) -> dict:
        return max(
            (self.services_by_id[service_id] for service_id in set(service_ids)),
            key=lambda service: int(service.get("facility_count") or 0),
        )

    def resolve_location(
        self,
        text: str,
        coordinates: Coordinates | None,
    ) -> dict:
        try:
            return self.base_recommender.resolve_location(
                text,
                coordinates.model_dump() if coordinates else None,
            )
        except LocationNotFound as error:
            raise HTTPException(
                status_code=422,
                detail={
                    "field": "location",
                    "message": str(error),
                    "suggestions": error.suggestions,
                },
            )

    def location_suggestions(self, query: str) -> list[dict]:
        return self.base_recommender.location_suggestions(query)

    def condition_suggestions(self, query: str) -> list[dict]:
        return self.condition_mapper.suggest_conditions(query)

    def resolve_conditions(self, text: str) -> ConditionMapping:
        mapping = self.condition_mapper.resolve(text)
        if not mapping.conditions:
            suggestions = self.condition_mapper.suggest_conditions(text, 8)
            if not suggestions:
                suggestions = self.condition_mapper.suggest_conditions("", 8)
            raise HTTPException(
                status_code=422,
                detail={
                    "field": "condition",
                    "message": (
                        f"Could not map '{text}' to a supported symptom or disease."
                    ),
                    "suggestions": [item["name"] for item in suggestions],
                },
            )
        return mapping

    def _build_condition_evidence_index(self) -> None:
        seen: set[tuple[str, str, str, str]] = set()
        for row in self.snapshot.index.to_dict(orient="records"):
            if row.get("eligibility") != "formal":
                continue
            facility_id = str(row["unique_id"])
            tag_id = str(row["tag_id"])
            for item in row.get("evidence") or []:
                field = str(item.get("field") or "")
                text = str(item.get("text") or "").strip()
                if field not in WEAK_FIELD_WEIGHTS or not text:
                    continue
                if NEGATIVE_EVIDENCE_RE.search(text):
                    continue
                key = (facility_id, tag_id, field, text)
                if key in seen:
                    continue
                seen.add(key)
                normalized = normalize_text(text)
                if not normalized:
                    continue
                index = len(self.condition_evidence)
                self.condition_evidence.append(
                    {
                        "facility_id": facility_id,
                        "tag_id": tag_id,
                        "field": field,
                        "text": text,
                        "normalized": normalized,
                        "evidence_tier": int(row.get("evidence_tier") or 3),
                        "only_equipment": bool(row.get("only_equipment")),
                    }
                )
                tokens = {
                    token
                    for token in EVIDENCE_TOKEN_RE.findall(normalized)
                    if token not in EVIDENCE_STOPWORDS
                }
                for token in tokens:
                    self.condition_evidence_postings[token].add(index)

    def _condition_text_matches(
        self,
        terms: tuple[str, ...],
    ) -> list[tuple[dict, str]]:
        matches: dict[tuple[str, str, str], tuple[dict, str]] = {}
        for phrase in terms:
            tokens = [
                token
                for token in EVIDENCE_TOKEN_RE.findall(phrase)
                if token not in EVIDENCE_STOPWORDS
            ]
            if not tokens:
                continue
            postings = [
                self.condition_evidence_postings.get(token, set())
                for token in tokens
            ]
            if any(not posting for posting in postings):
                continue
            candidate_ids = set.intersection(*postings)
            for index in candidate_ids:
                record = self.condition_evidence[index]
                if phrase not in record["normalized"]:
                    continue
                key = (
                    record["facility_id"],
                    record["tag_id"],
                    record["text"],
                )
                matches[key] = (record, phrase)
        return list(matches.values())

    def recommend_conditions(
        self,
        mapping: ConditionMapping,
        location: dict,
        limit: int,
    ) -> tuple[list[dict], float]:
        candidates: dict[str, dict] = {}
        seen_weak: set[tuple[str, str, str, str]] = set()
        related_service_ids = {
            f"tag:{tag.tag_id}" for tag in mapping.related_tags
        }

        def emergency_facility_allowed(facility_id: str) -> bool:
            return (
                mapping.urgency != Urgency.EMERGENCY
                or facility_id in self.emergency_facility_ids
            )

        for route in mapping.services:
            for action_id in route.action_ids:
                for match in self.facility_actions_by_action.get(action_id, []):
                    facility_id = str(match["unique_id"])
                    if not emergency_facility_allowed(facility_id):
                        continue
                    score = float(route.score) * float(match["match_strength"])
                    inferred = "related_condition" in route.route_type
                    fields = list(match.get("source_fields") or [])
                    roles = list(match.get("evidence_roles") or [])
                    for quote in match.get("matched_values") or []:
                        if inferred and not self._emergency_weak_evidence_allowed(
                            mapping.urgency,
                            {"service_id": route.service_id, "service_group": ""},
                            str(quote),
                            " + ".join(route.condition_labels),
                        ):
                            continue
                        self._merge_condition_candidate(
                            candidates,
                            facility_id,
                            direct_score=0.0 if inferred else score,
                            weak_score=score if inferred else 0.0,
                            evidence={
                                "quote": str(quote),
                                "field": fields[0]
                                if len(fields) == 1
                                else " + ".join(fields),
                                "role": roles[0]
                                if len(roles) == 1
                                else "action_evidence",
                                "condition_label": ", ".join(route.condition_labels),
                                "condition_ids": list(route.condition_ids),
                                "action_ids": [action_id],
                                "action_labels": list(route.action_labels),
                                "service_id": route.service_id,
                                "service_label": route.service_label,
                                "route_type": route.route_type,
                                "evidence_tier": "weak" if inferred else "direct",
                                "strength": (
                                    "weak"
                                    if inferred
                                    else "strong"
                                    if float(match["match_strength"]) >= 0.9
                                    else "medium"
                                ),
                            },
                        )

        for condition in (*mapping.conditions, *mapping.related_conditions):
            inferred = condition.match_method == "related_condition"
            for phrase in self.condition_mapper.search_terms(
                condition.condition_label
            ):
                for record, matched_phrase in self._condition_text_matches((phrase,)):
                    if not emergency_facility_allowed(record["facility_id"]):
                        continue
                    service = self.services_by_tag_id.get(record["tag_id"])
                    if not service:
                        continue
                    if str(service["service_id"]) not in related_service_ids:
                        continue
                    if not self._emergency_weak_evidence_allowed(
                        mapping.urgency,
                        service,
                        record["text"],
                        condition.condition_label,
                    ):
                        continue
                    if not self._routine_weak_service_allowed(mapping, service):
                        continue
                    weak_score = (
                        condition.confidence
                        * WEAK_FIELD_WEIGHTS[record["field"]]
                        * WEAK_TIER_MULTIPLIERS.get(
                            record["evidence_tier"], 0.65
                        )
                    )
                    if inferred:
                        weak_score *= 0.70
                    if record["only_equipment"]:
                        weak_score *= 0.80
                    seen_key = (
                        record["facility_id"],
                        str(service["service_id"]),
                        condition.condition_id,
                        record["text"],
                    )
                    if seen_key in seen_weak:
                        continue
                    seen_weak.add(seen_key)
                    self._merge_condition_candidate(
                        candidates,
                        record["facility_id"],
                        direct_score=0.0,
                        weak_score=weak_score,
                        evidence={
                            "quote": record["text"],
                            "field": FIELD_COLUMN_NAMES[record["field"]],
                            "role": "weak_bridge",
                            "condition_label": condition.condition_label,
                            "condition_ids": [condition.condition_id],
                            "action_ids": [],
                            "action_labels": [],
                            "service_id": str(service["service_id"]),
                            "service_label": str(service["service_label"]),
                            "route_type": (
                                "related_condition_text_tag"
                                if inferred
                                else "condition_text_tag"
                            ),
                            "evidence_tier": "weak",
                            "strength": "weak",
                            "matched_phrase": matched_phrase,
                        },
                    )

        primary_condition = mapping.conditions[0]
        main_terms = {
            term
            for condition in mapping.conditions
            for term in self.condition_mapper.search_terms(
                condition.condition_label
            )
        }
        for phrase in mapping.treatment_terms:
            if phrase in main_terms:
                continue
            for record, matched_phrase in self._condition_text_matches((phrase,)):
                if not emergency_facility_allowed(record["facility_id"]):
                    continue
                service = self.services_by_tag_id.get(record["tag_id"])
                if not service:
                    continue
                if str(service["service_id"]) not in related_service_ids:
                    continue
                if not self._emergency_weak_evidence_allowed(
                    mapping.urgency,
                    service,
                    record["text"],
                    primary_condition.condition_label,
                ):
                    continue
                if not self._routine_weak_service_allowed(mapping, service):
                    continue
                weak_score = (
                    primary_condition.confidence
                    * 0.75
                    * WEAK_FIELD_WEIGHTS[record["field"]]
                    * WEAK_TIER_MULTIPLIERS.get(record["evidence_tier"], 0.65)
                )
                if record["only_equipment"]:
                    weak_score *= 0.80
                seen_key = (
                    record["facility_id"],
                    str(service["service_id"]),
                    primary_condition.condition_id,
                    record["text"],
                )
                if seen_key in seen_weak:
                    continue
                seen_weak.add(seen_key)
                self._merge_condition_candidate(
                    candidates,
                    record["facility_id"],
                    direct_score=0.0,
                    weak_score=weak_score,
                    evidence={
                        "quote": record["text"],
                        "field": FIELD_COLUMN_NAMES[record["field"]],
                        "role": "related_treatment",
                        "condition_label": primary_condition.condition_label,
                        "condition_ids": [primary_condition.condition_id],
                        "action_ids": [],
                        "action_labels": [],
                        "service_id": str(service["service_id"]),
                        "service_label": str(service["service_label"]),
                        "route_type": "related_treatment_text",
                        "evidence_tier": "weak",
                        "strength": "weak",
                        "matched_phrase": matched_phrase,
                    },
                )

        for related_tag in mapping.related_tags:
            service_id = f"tag:{related_tag.tag_id}"
            tag_metadata = self.clinical_tags_by_id.get(related_tag.tag_id)
            if not tag_metadata or tag_metadata.get("kind") != "condition":
                continue
            service = {
                "service_id": service_id,
                "service_label": related_tag.label,
                "service_group": str(tag_metadata.get("group_name") or ""),
            }
            if not self._routine_weak_service_allowed(mapping, service):
                continue
            for tag_row in self.tag_facilities.get(related_tag.tag_id, []):
                if not emergency_facility_allowed(str(tag_row["unique_id"])):
                    continue
                evidence_items = [
                    item
                    for item in tag_row.get("evidence") or []
                    if item.get("field") in WEAK_FIELD_WEIGHTS
                    and item.get("text")
                    and not NEGATIVE_EVIDENCE_RE.search(str(item["text"]))
                ]
                if mapping.urgency == Urgency.EMERGENCY:
                    evidence_items = [
                        item
                        for item in evidence_items
                        if self._emergency_weak_evidence_allowed(
                            mapping.urgency,
                            service,
                            str(item["text"]),
                            primary_condition.condition_label,
                        )
                    ]
                if not evidence_items:
                    continue
                tier = int(tag_row.get("evidence_tier") or 3)
                tier_factor = WEAK_TIER_MULTIPLIERS.get(tier, 0.65)
                best_item = max(
                    evidence_items,
                    key=lambda item: WEAK_FIELD_WEIGHTS[str(item["field"])],
                )
                weak_score = min(
                    0.55,
                    related_tag.weight
                    * primary_condition.confidence
                    * WEAK_FIELD_WEIGHTS[str(best_item["field"])]
                    * tier_factor
                    * 1.30,
                )
                if tag_row.get("only_equipment"):
                    weak_score *= 0.80
                for item in evidence_items[:2]:
                    seen_key = (
                        str(tag_row["unique_id"]),
                        service_id,
                        primary_condition.condition_id,
                        str(item["text"]),
                    )
                    if seen_key in seen_weak:
                        continue
                    seen_weak.add(seen_key)
                    self._merge_condition_candidate(
                        candidates,
                        str(tag_row["unique_id"]),
                        direct_score=0.0,
                        weak_score=weak_score,
                        evidence={
                            "quote": str(item["text"]),
                            "field": FIELD_COLUMN_NAMES[str(item["field"])],
                            "role": "related_tag",
                            "condition_label": primary_condition.condition_label,
                            "condition_ids": [primary_condition.condition_id],
                            "action_ids": [],
                            "action_labels": [],
                            "service_id": service_id,
                            "service_label": related_tag.label,
                            "route_type": "condition_related_tag",
                            "evidence_tier": "weak",
                            "strength": "weak",
                            "matched_phrase": related_tag.label,
                        },
                    )

        if not candidates:
            return [], RADIUS_STEPS_KM[-1]

        for radius in RADIUS_STEPS_KM:
            within = self._condition_rank_within(
                candidates,
                mapping,
                location,
                radius,
                limit,
            )
            if within:
                return within, radius
        return [], RADIUS_STEPS_KM[-1]

    @staticmethod
    def _emergency_weak_evidence_allowed(
        urgency: Urgency,
        service: dict,
        evidence_text: str = "",
        condition_label: str = "",
    ) -> bool:
        if urgency != Urgency.EMERGENCY:
            return True
        service_id = str(service.get("service_id") or "")
        if service_id in EMERGENCY_WEAK_SERVICE_IDS:
            return True
        service_group = str(service.get("service_group") or "").casefold()
        if "emergency" in service_group or "critical care" in service_group:
            return True
        normalized_condition = normalize_text(condition_label)
        if "stroke" in normalized_condition:
            return bool(STROKE_ACUTE_RE.search(evidence_text))
        if "chest pain" in normalized_condition:
            return bool(CARDIAC_ACUTE_RE.search(evidence_text))
        if "fall" in normalized_condition:
            return bool(TRAUMA_ACUTE_RE.search(evidence_text))
        return bool(EMERGENCY_WEAK_TEXT_RE.search(evidence_text))

    @staticmethod
    def _routine_weak_service_allowed(
        mapping: ConditionMapping,
        service: dict,
    ) -> bool:
        service_id = str(service.get("service_id") or "")
        if service_id not in CONDITION_WEAK_SERVICE_EXCLUSIONS:
            return True
        normalized = normalize_text(mapping.input_text)
        return bool(
            re.search(
                r"\b(vaccine|vaccination|immuni[sz]ation|prevention|preventive)\b"
                r"|疫苗|预防|接种",
                normalized,
            )
        )

    def _merge_condition_candidate(
        self,
        candidates: dict[str, dict],
        facility_id: str,
        *,
        direct_score: float,
        weak_score: float,
        evidence: dict,
    ) -> None:
        candidate = candidates.setdefault(
            facility_id,
            {
                "direct_relevance": 0.0,
                "weak_relevance": 0.0,
                "relevance": 0.0,
                "evidence": [],
                "route_types": set(),
                "condition_ids": set(),
                "condition_labels": set(),
                "action_ids": set(),
                "action_labels": set(),
                "services": {},
            },
        )
        candidate["direct_relevance"] = max(
            float(candidate["direct_relevance"]), direct_score
        )
        candidate["weak_relevance"] = max(
            float(candidate["weak_relevance"]), weak_score
        )
        direct = float(candidate["direct_relevance"])
        weak = float(candidate["weak_relevance"])
        candidate["relevance"] = min(
            1.0,
            max(direct, weak)
            + (0.08 * min(direct, weak) if direct > 0 and weak > 0 else 0.0),
        )
        evidence_key = (
            evidence["quote"],
            evidence["route_type"],
            evidence["condition_label"],
        )
        if not any(
            existing["_key"] == evidence_key
            for existing in candidate["evidence"]
        ):
            candidate["evidence"].append({**evidence, "_key": evidence_key})
        candidate["route_types"].add(evidence["route_type"])
        candidate["condition_ids"].update(evidence["condition_ids"])
        candidate["condition_labels"].add(evidence["condition_label"])
        candidate["action_ids"].update(evidence["action_ids"])
        candidate["action_labels"].update(evidence["action_labels"])
        service = candidate["services"].setdefault(
            evidence["service_id"],
            {
                "id": evidence["service_id"],
                "label": evidence["service_label"],
                "score": 0.0,
                "routeTypes": set(),
            },
        )
        service["score"] = max(
            float(service["score"]),
            direct_score if direct_score > 0 else weak_score,
        )
        service["routeTypes"].add(evidence["route_type"])

    def _condition_rank_within(
        self,
        candidates: dict[str, dict],
        mapping: ConditionMapping,
        location: dict,
        radius: float,
        limit: int,
    ) -> list[dict]:
        weight = distance_weight(mapping.urgency)
        rows = []
        for facility_id, candidate in candidates.items():
            try:
                facility = self.facilities.loc[facility_id]
            except KeyError:
                continue
            if str(facility.get("facility_category") or "").casefold() != "hospital":
                continue
            latitude = float(facility["rec_lat"])
            longitude = float(facility["rec_lon"])
            if not math.isfinite(latitude) or not math.isfinite(longitude):
                continue
            distance = float(
                haversine_km(
                    location["lat"],
                    location["lon"],
                    np.asarray([latitude], dtype=float),
                    np.asarray([longitude], dtype=float),
                )[0]
            )
            if distance > radius:
                continue
            relevance = float(candidate["relevance"])
            distance_score = 1.0 - min(distance / radius, 1.0)
            stage1_score = 100.0 * (
                (1.0 - weight) * relevance + weight * distance_score
            )
            rows.append(
                {
                    "facility": facility,
                    "facility_id": facility_id,
                    "distance_km": distance,
                    "relevance": relevance,
                    "distance_score": distance_score,
                    "stage1_score": round(stage1_score, 1),
                    "weight": weight,
                    "urgency": mapping.urgency.name.lower(),
                    "candidate": candidate,
                    "condition_mapping": mapping,
                }
            )
        rows.sort(
            key=lambda row: (
                -row["stage1_score"],
                row["distance_km"],
                str(row["facility"]["name"]),
            )
        )
        for index, row in enumerate(rows, start=1):
            row["stage1_rank"] = index
        pool = rows[:RERANK_POOL_SIZE]
        for row in pool:
            rerank = rerank_condition_candidate(
                row["candidate"],
                distance_score=row["distance_score"],
                urgency=Urgency[mapping.urgency.name],
                facility_source_count=len(
                    row["facility"].get("source_urls") or []
                ),
                candidate_pool_size=len(pool),
            )
            row["reranking"] = rerank
            row["final_score"] = rerank.total_score
        pool.sort(
            key=lambda row: (
                -row["final_score"],
                -row["reranking"].evidence_score,
                row["distance_km"],
                str(row["facility"]["name"]),
            )
        )
        return pool[:limit]

    def recommend(
        self,
        service: dict,
        service_match_confidence: float,
        location: dict,
        limit: int,
        requested_text: str,
    ) -> tuple[list[dict], float]:
        service_id = str(service["service_id"])
        action_links = self.actions_by_service.get(service_id, [])
        action_confidence = {
            str(link["action_id"]): float(link["confidence"])
            for link in action_links
        }

        candidates: dict[str, dict] = {}

        for action_id, mapping_confidence in action_confidence.items():
            for match in self.facility_actions_by_action.get(action_id, []):
                facility_id = str(match["unique_id"])
                relevance = mapping_confidence * float(match["match_strength"])
                self._merge_candidate(
                    candidates,
                    facility_id,
                    relevance,
                    {
                        "quotes": list(match.get("matched_values") or []),
                        "fields": list(match.get("source_fields") or []),
                        "roles": list(match.get("evidence_roles") or []),
                        "action_ids": [action_id],
                    },
                )

        # Procedure/equipment/capability tag evidence is a weak bridge. Direct
        # action matches above remain stronger but are not required for coverage.
        if service_id.startswith("tag:"):
            tag_id = service_id.removeprefix("tag:")
            for row in self.tag_facilities.get(tag_id, []):
                tier = int(row.get("evidence_tier") or 3)
                relevance = {1: 0.55, 2: 0.45, 3: 0.35}.get(tier, 0.30)
                evidence = row.get("evidence") or []
                quotes = [
                    str(item.get("text") or "")
                    for item in evidence
                    if item.get("text")
                ]
                fields = [
                    FIELD_COLUMN_NAMES.get(
                        str(item.get("field") or ""),
                        str(item.get("field") or ""),
                    )
                    for item in evidence
                    if item.get("field")
                ]
                self._merge_candidate(
                    candidates,
                    str(row["unique_id"]),
                    relevance,
                    {
                        "quotes": quotes,
                        "fields": fields,
                        "roles": [],
                        "action_ids": list(action_confidence),
                    },
                )

        if not candidates:
            return [], RADIUS_STEPS_KM[-1]

        for radius in RADIUS_STEPS_KM:
            within = self._rank_within(
                candidates,
                service,
                service_match_confidence,
                location,
                radius,
                limit,
                requested_text,
            )
            if within:
                return within, radius
        return [], RADIUS_STEPS_KM[-1]

    def _merge_candidate(
        self,
        candidates: dict[str, dict],
        facility_id: str,
        relevance: float,
        evidence: dict,
    ) -> None:
        candidate = candidates.setdefault(
            facility_id,
            {"relevance": 0.0, "quotes": [], "fields": [], "roles": [], "action_ids": []},
        )
        candidate["relevance"] = max(candidate["relevance"], relevance)
        for key in ("quotes", "fields", "roles", "action_ids"):
            for value in evidence[key]:
                if value and value not in candidate[key]:
                    candidate[key].append(value)

    def _rank_within(
        self,
        candidates: dict[str, dict],
        service: dict,
        service_match_confidence: float,
        location: dict,
        radius: float,
        limit: int,
        requested_text: str,
    ) -> list[dict]:
        service_urgency = str(service.get("urgency_level") or "routine")
        query_urgency = max(
            detect_urgency(requested_text),
            detect_urgency(str(service.get("service_label") or "")),
        )
        urgency = max(
            query_urgency,
            {
                "routine": Urgency.ROUTINE,
                "urgent": Urgency.URGENT,
                "emergency": Urgency.EMERGENCY,
            }.get(service_urgency, Urgency.ROUTINE),
        )
        weight = distance_weight(urgency)
        rows = []

        for facility_id, candidate in candidates.items():
            try:
                facility = self.facilities.loc[facility_id]
            except KeyError:
                continue
            if service.get("service_id") == "tag:emergency-24x7" and (
                str(facility.get("facility_category") or "").casefold()
                != "hospital"
                or facility_id not in self.emergency_facility_ids
            ):
                continue
            latitude = float(facility["rec_lat"])
            longitude = float(facility["rec_lon"])
            if not math.isfinite(latitude) or not math.isfinite(longitude):
                continue
            distance = float(
                haversine_km(
                    location["lat"],
                    location["lon"],
                    np.asarray([latitude], dtype=float),
                    np.asarray([longitude], dtype=float),
                )[0]
            )
            if distance > radius:
                continue
            relevance = min(1.0, candidate["relevance"] * service_match_confidence)
            distance_score = 1.0 - min(distance / radius, 1.0)
            final_score = 100.0 * ((1.0 - weight) * relevance + weight * distance_score)
            rows.append(
                {
                    "facility": facility,
                    "facility_id": facility_id,
                    "distance_km": distance,
                    "relevance": relevance,
                    "distance_score": distance_score,
                    "final_score": round(final_score, 1),
                    "weight": weight,
                    "urgency": urgency.name.lower(),
                    "candidate": candidate,
                }
            )

        rows.sort(
            key=lambda row: (
                -row["final_score"],
                row["distance_km"],
                str(row["facility"]["name"]),
            )
        )
        return rows[:limit]


MODEL: LocalModel | None = None
MODEL_LOCK = threading.Lock()


def model() -> LocalModel:
    global MODEL
    if MODEL is None:
        with MODEL_LOCK:
            if MODEL is None:
                MODEL = LocalModel()
    return MODEL


app = FastAPI(title="CarePath local condition and service recommender")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    current = model()
    return {
        "status": "ok",
        "modelVersion": CONDITION_MODEL_VERSION,
        "serviceModelVersion": SERVICE_MODEL_VERSION,
        "services": len(current.services),
        "conditionConcepts": current.condition_mapper.condition_count,
        "conditionActionEdges": len(current.condition_edges),
        "conditionEvidenceRecords": len(current.condition_evidence),
        "serviceActionLinks": len(current.service_actions),
        "facilityActionMatches": len(current.facility_actions),
    }


@app.get("/api/services")
def services() -> list[dict]:
    current = model()
    return [
        {
            "id": service["service_id"],
            "name": service["service_label"],
            "synonyms": [
                alias
                for alias in (service.get("aliases") or [])
                if alias != service["service_label"]
            ][:6],
            "category": service.get("service_group") or service.get("service_type"),
            "facilityCount": int(service.get("facility_count") or 0),
        }
        for service in current.service_catalog()
    ]


@app.get("/api/conditions")
def conditions(q: str = "") -> list[dict]:
    return model().condition_suggestions(q)


@app.get("/api/locations")
def locations(q: str = "") -> list[dict]:
    if not q.strip():
        return []
    return model().location_suggestions(q)


@app.post("/api/recommendations")
def recommendations(request: RecommendationRequest) -> dict:
    started = time.perf_counter()
    current = model()
    location = current.resolve_location(request.locationText, request.coordinates)
    request_id = f"local-{uuid.uuid4().hex[:12]}"

    if request.conditionText:
        mapping = current.resolve_conditions(request.conditionText)
        results, radius = current.recommend_conditions(
            mapping,
            location,
            request.limit,
        )
        payload_results = [
            _condition_facility_payload(
                row=row,
                rank=index,
                mapping=mapping,
                request_id=request_id,
                radius=radius,
            )
            for index, row in enumerate(results, start=1)
        ]
        condition_names = [item.condition_label for item in mapping.conditions]
        condition_confidence = max(
            (item.confidence for item in mapping.conditions),
            default=0.0,
        )
        services_by_route: dict[str, dict] = {
            route.service_id: {
                "id": route.service_id,
                "label": route.service_label,
                "score": route.score,
                "routeTypes": {route.route_type},
                "actionIds": set(route.action_ids),
                "conditions": set(route.condition_labels),
            }
            for route in mapping.services
        }
        for row in results:
            for service_id, used_service in row["candidate"][
                "services"
            ].items():
                route = services_by_route.setdefault(
                    service_id,
                    {
                        "id": service_id,
                        "label": used_service["label"],
                        "score": float(used_service["score"]),
                        "routeTypes": set(),
                        "actionIds": set(),
                        "conditions": set(),
                    },
                )
                route["score"] = max(
                    float(route["score"]),
                    float(used_service["score"]),
                )
                route["routeTypes"].update(used_service["routeTypes"])
                route["conditions"].update(
                    row["candidate"]["condition_labels"]
                )
        service_routes = [
            {
                "id": route["id"],
                "label": route["label"],
                "score": round(float(route["score"]), 4),
                "routeType": " + ".join(sorted(route["routeTypes"])),
                "actionIds": sorted(route["actionIds"]),
                "conditions": sorted(route["conditions"]),
            }
            for route in sorted(
                services_by_route.values(),
                key=lambda item: (
                    -float(item["score"]),
                    item["label"],
                ),
            )
        ][:12]
        top_service = service_routes[0] if service_routes else None
        warnings = [
            "Symptoms and diseases are mapped to services before facility ranking.",
            "Urgency is calculated from the input symptom/disease text before the service map.",
            "Related condition, treatment and clinical-tag terms are inferred retrieval hints, not a treatment plan.",
            "Procedure, equipment and capability text used as indirect evidence is labelled weak.",
            "Facilities are reranked in a second stage using text match, evidence quality and urgency-weighted distance.",
            "Condition search is limited to records categorised as hospitals; specialist clinics are excluded.",
            "This is not a diagnosis; emergent symptoms need appropriate emergency assessment.",
            "Current service availability and wait times must be confirmed with the facility.",
        ]
        if mapping.urgency == Urgency.EMERGENCY:
            warnings.insert(
                3,
                "Emergency inputs restrict weak evidence to acute-care signals or acute-response services such as emergency, ICU, imaging and vascular intervention.",
            )
            warnings.insert(
                4,
                "Emergency weak matches require a recorded 24/7 emergency signal at the facility; this does not confirm immediate capacity.",
            )
        if not results:
            warnings.insert(
                2,
                "No supported facility evidence was found within 200 km for the mapped conditions.",
            )
        return {
            "queryContext": {
                "requestId": request_id,
                "inputKind": "condition",
                "inputText": request.conditionText,
                "condition": {
                    "displayName": " + ".join(condition_names[:2]),
                    "matchedLabels": condition_names,
                    "canonicalIds": [
                        item.condition_id for item in mapping.conditions
                    ],
                    "inferredLabels": [
                        item.condition_label
                        for item in mapping.related_conditions
                    ],
                    "treatmentConcepts": list(mapping.treatment_terms[:12]),
                    "relatedTags": [
                        {
                            "id": item.tag_id,
                            "label": item.label,
                            "weight": item.weight,
                        }
                        for item in mapping.related_tags
                    ],
                    "confidence": (
                        "high"
                        if condition_confidence >= 0.9
                        else "medium"
                        if condition_confidence >= 0.7
                        else "low"
                    ),
                    "negatedMentions": list(mapping.negated_mentions),
                    "urgency": mapping.urgency.name.lower(),
                },
                "services": service_routes,
                "service": {
                    "canonicalId": (
                        f"condition:{mapping.conditions[0].condition_id}"
                        if mapping.conditions
                        else "condition:unknown"
                    ),
                    "displayName": " + ".join(condition_names),
                    "matchedSynonyms": [
                        *condition_names,
                        *[
                            item.condition_label
                            for item in mapping.related_conditions[:4]
                        ],
                    ],
                    "confidence": (
                        "high"
                        if condition_confidence >= 0.9
                        else "medium"
                        if condition_confidence >= 0.7
                        else "low"
                    ),
                },
                "location": {
                    "type": location["type"],
                    "inputValue": request.locationText or "Current location",
                    "resolvedName": location["name"],
                    "district": location["district"],
                    "state": location["state"],
                    "latitude": float(location["lat"]),
                    "longitude": float(location["lon"]),
                    "confidence": location["confidence"],
                },
                "searchParameters": {
                    "radiusKm": radius,
                    "limit": request.limit,
                },
            },
            "results": payload_results,
            "metadata": {
                "requestId": request_id,
                "rankingVersion": CONDITION_MODEL_VERSION,
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "totalCandidates": len(results),
                "returnedCount": len(payload_results),
                "isPartialResult": bool(results),
                "candidatePoolSize": max(
                    (
                        row["reranking"].scored_item_count
                        for row in results
                    ),
                    default=0,
                ),
                "rerankedCount": len(results),
                "executionTimeMs": round(
                    (time.perf_counter() - started) * 1000, 1
                ),
                "warnings": warnings,
                "funnel": {
                    "datasetProviders": current.snapshot.facilities[
                        "unique_id"
                    ].nunique(),
                    "datasetRecommendable": current.snapshot.facilities[
                        "unique_id"
                    ].nunique(),
                    "withinRadius": len(results),
                    "reviewBlockedWithinRadius": 0,
                    "radiusStepsKm": list(RADIUS_STEPS_KM),
                    "radiusKm": radius,
                    "locationNote": location["note"],
                    "serviceMatch": (
                        " + ".join(condition_names)
                        + f" ({condition_confidence:.2f})"
                    ),
                    "dataSource": "model/artifacts/cloud_snapshot",
                },
            },
        }

    if not request.serviceText:
        raise HTTPException(
            status_code=422,
            detail={
                "field": "condition",
                "message": "Enter symptoms, a disease, or a service.",
                "suggestions": [
                    item["name"]
                    for item in current.condition_suggestions("", 8)
                ],
            },
        )

    service, display_name, service_confidence = current.resolve_service(
        request.serviceText
    )
    results, radius = current.recommend(
        service,
        service_confidence,
        location,
        request.limit,
        request.serviceText,
    )
    payload_results = [
        _facility_payload(
            row=row,
            rank=index,
            service=service,
            request_id=request_id,
            radius=radius,
        )
        for index, row in enumerate(results, start=1)
    ]

    return {
        "queryContext": {
            "requestId": request_id,
            "inputKind": "service",
            "inputText": request.serviceText,
            "service": {
                "canonicalId": service["service_id"],
                "displayName": display_name,
                "matchedSynonyms": service.get("aliases") or [],
                "confidence": "high" if service_confidence >= 0.9 else "medium",
            },
                "services": [],
            "location": {
                "type": location["type"],
                "inputValue": request.locationText or "Current location",
                "resolvedName": location["name"],
                "district": location["district"],
                "state": location["state"],
                "latitude": float(location["lat"]),
                "longitude": float(location["lon"]),
                "confidence": location["confidence"],
            },
            "searchParameters": {
                "radiusKm": radius,
                "limit": request.limit,
            },
        },
        "results": payload_results,
        "metadata": {
            "requestId": request_id,
            "rankingVersion": SERVICE_MODEL_VERSION,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "totalCandidates": len(results),
            "returnedCount": len(payload_results),
            "isPartialResult": False,
            "executionTimeMs": round((time.perf_counter() - started) * 1000, 1),
            "warnings": [
                "Service matching uses the local cloud-model snapshot.",
                "Scores combine service/evidence relevance and distance; urgency controls distance weight.",
                "Current service availability must still be confirmed with the facility.",
            ],
            "funnel": {
                "datasetProviders": current.snapshot.facilities["unique_id"].nunique(),
                "datasetRecommendable": current.snapshot.facilities["unique_id"].nunique(),
                "withinRadius": len(results),
                "reviewBlockedWithinRadius": 0,
                "radiusStepsKm": list(RADIUS_STEPS_KM),
                "radiusKm": radius,
                "locationNote": location["note"],
                "serviceMatch": f"{display_name} ({service_confidence:.2f})",
                "dataSource": "model/artifacts/cloud_snapshot",
            },
        },
    }


def _condition_facility_payload(
    *,
    row: dict,
    rank: int,
    mapping: ConditionMapping,
    request_id: str,
    radius: float,
) -> dict:
    facility = row["facility"]
    facility_id = row["facility_id"]
    candidate = row["candidate"]
    rerank = row.get("reranking")
    source_urls = list(facility.get("source_urls") or [])[:4]
    sources = []
    for index, url in enumerate(source_urls, start=1):
        parsed = urlparse(str(url))
        sources.append(
            {
                "id": f"source-{index}",
                "url": str(url),
                "domain": parsed.netloc.removeprefix("www."),
                "sourceType": "unknown",
                "title": parsed.netloc.removeprefix("www."),
                "retrievedAt": datetime.now(timezone.utc).isoformat(),
                "supportsClaims": [],
            }
        )
    source_id = sources[0]["id"] if sources else "record"
    evidence = []
    evidence_source_items = list(candidate["evidence"])
    if rerank:
        evidence_source_items.sort(
            key=lambda item: item["quote"] != rerank.best_evidence_text
        )
    for index, item in enumerate(evidence_source_items[:4], start=1):
        match_type = (
            "weak_bridge"
            if item["evidence_tier"] == "weak"
            else "exact"
            if item["role"] == "direct_procedure"
            else "semantic"
        )
        evidence.append(
            {
                "id": f"{facility_id}-condition-evidence-{index}",
                "fieldName": item["field"],
                "matchedService": item["service_label"],
                "quote": item["quote"],
                "matchType": match_type,
                "polarity": "positive",
                "strength": item["strength"],
                "sourceId": source_id,
                "route": item["route_type"],
                "evidenceTier": item["evidence_tier"],
                "condition": item["condition_label"],
                "matchedPhrase": item.get("matched_phrase") or item["condition_label"],
            }
        )

    direct_relevance = float(candidate["direct_relevance"])
    weak_relevance = float(candidate["weak_relevance"])
    condition_confidence = max(
        (item.confidence for item in mapping.conditions),
        default=0.0,
    )
    services = sorted(
        candidate["services"].values(),
        key=lambda item: (-float(item["score"]), item["label"]),
    )
    service_labels = [str(item["label"]) for item in services]
    condition_labels = sorted(candidate["condition_labels"])
    has_direct = direct_relevance > 0
    has_weak = weak_relevance > 0
    confidence = (
        "high"
        if has_direct and direct_relevance >= 0.60
        else "medium"
        if has_direct or weak_relevance >= 0.40
        else "low"
    )
    reason_codes = [
        "LOCAL_MODEL_SNAPSHOT",
        "CURRENT_AVAILABILITY_UNKNOWN",
    ]
    messages = [
        (
            f"Urgency was detected from the symptom/disease input before "
            f"service mapping: {row['urgency']}; distance weight "
            f"{row['weight']:.2f}."
        )
    ]
    if has_weak and not has_direct:
        reason_codes.append("WEAK_INTERMEDIATE_EVIDENCE")
        messages.append(
            "No direct condition-to-action facility evidence was found. "
            "This result relies on procedure, capability or equipment text "
            "as a weak bridge and should be treated as lower confidence."
        )
    elif has_weak:
        reason_codes.append("MIXED_DIRECT_AND_WEAK_EVIDENCE")
        messages.append(
            "This result combines direct action evidence with weak indirect "
            "procedure, capability or equipment evidence."
        )
    messages.append(
        "This mapping is not a diagnosis or treatment recommendation; "
        "confirm current service availability before travelling."
    )

    direct_services = [
        service["label"]
        for service in services
        if "condition_action" in service["routeTypes"]
    ]
    summary_service = (
        direct_services[0] if direct_services else service_labels[0]
        if service_labels
        else "service"
    )
    evidence_type = (
        "direct and weak evidence"
        if has_direct and has_weak
        else "direct evidence"
        if has_direct
        else "weak intermediate evidence"
    )
    if rerank:
        score_breakdown = {
            "conditionMatchScore": round(condition_confidence * 100, 1),
            "directActionScore": round(direct_relevance * 100, 1),
            "weakBridgeScore": round(weak_relevance * 100, 1),
            "serviceMatchScore": round(
                rerank.text_score * rerank.weights["text"], 1
            ),
            "evidenceScore": round(
                rerank.evidence_score * rerank.weights["evidence"], 1
            ),
            "sourceScore": min(100.0, len(sources) * 25.0),
            "distanceScore": round(
                rerank.distance_score * rerank.weights["distance"], 1
            ),
            "distanceWeight": round(rerank.weights["distance"], 2),
            "serviceEvidenceWeight": round(
                1.0 - rerank.weights["distance"], 2
            ),
            "searchRadiusKm": radius,
            "urgency": row["urgency"],
            "locationQualityScore": 100.0,
            "capacityScore": 0,
            "penaltyScore": 0,
            "totalScore": rerank.total_score,
            "modelVersion": (
                f"{CONDITION_MODEL_VERSION}+{RERANKER_VERSION}"
            ),
        }
    else:
        score_breakdown = {
            "conditionMatchScore": round(condition_confidence * 100, 1),
            "directActionScore": round(direct_relevance * 100, 1),
            "weakBridgeScore": round(weak_relevance * 100, 1),
            "serviceMatchScore": round(row["relevance"] * 100, 1),
            "evidenceScore": round(row["relevance"] * 100, 1),
            "sourceScore": min(100.0, len(sources) * 25.0),
            "distanceScore": round(row["distance_score"] * 100, 1),
            "distanceWeight": round(row["weight"], 2),
            "serviceEvidenceWeight": round(1.0 - row["weight"], 2),
            "searchRadiusKm": radius,
            "urgency": row["urgency"],
            "locationQualityScore": 100.0,
            "capacityScore": 0,
            "penaltyScore": 0,
            "totalScore": row["final_score"],
            "modelVersion": CONDITION_MODEL_VERSION,
        }
    best_evidence = next(
        (
            item
            for item in evidence
            if rerank and item["quote"] == rerank.best_evidence_text
        ),
        evidence[0] if evidence else None,
    )
    return {
        "id": facility_id,
        "rank": rank,
        "name": str(facility.get("name") or "Unnamed facility"),
        "type": str(
            facility.get("facility_category") or "Healthcare facility"
        ).title(),
        "operatorType": str(
            facility.get("operator_category") or "Unknown"
        ).title(),
        "address": str(
            facility.get("address_city") or facility.get("city_raw") or ""
        ),
        "district": str(facility.get("district") or ""),
        "state": str(facility.get("state") or ""),
        "pincode": str(facility.get("pincode") or ""),
        "phone": (
            str(facility.get("contact_phone")).strip()
            if facility.get("contact_phone") is not None
            and str(facility.get("contact_phone")).strip()
            else None
        ),
        "website": (
            str(facility.get("contact_website")).strip()
            if facility.get("contact_website") is not None
            and str(facility.get("contact_website")).strip()
            else None
        ),
        "latitude": float(facility["rec_lat"]),
        "longitude": float(facility["rec_lon"]),
        "distanceKm": round(row["distance_km"], 1),
        "totalScore": row["final_score"],
        "confidence": confidence,
        "recommendationSummary": (
            f"{' + '.join(condition_labels)} mapped through "
            f"{summary_service} with {evidence_type}. "
            f"{row['distance_km']:.1f} km away."
        ),
        "scoreBreakdown": score_breakdown,
        "reranking": (
            {
                "method": "structured_evidence",
                "model": RERANKER_VERSION,
                "textScore": rerank.text_score,
                "evidenceScore": rerank.evidence_score,
                "distanceScore": rerank.distance_score,
                "totalScore": rerank.total_score,
                "weights": rerank.weights,
                "bestEvidenceRef": (
                    str(best_evidence["id"]) if best_evidence else ""
                ),
                "bestEvidenceText": rerank.best_evidence_text,
                "scoredItemCount": rerank.scored_item_count,
                "stageOneRank": row.get("stage1_rank"),
                "stageOneScore": row.get("stage1_score"),
                "scoreMeaning": (
                    "Second-stage structured evidence reranking after "
                    "high-recall candidate generation."
                ),
            }
            if rerank
            else None
        ),
        "evidence": evidence,
        "sources": sources,
        "locationQuality": {
            "label": "Medium confidence",
            "note": str(
                facility.get("location_check") or "Facility record coordinates"
            ),
        },
        "dataCompleteness": min(
            100,
            int(40 + 15 * len(evidence) + 10 * len(sources)),
        ),
        "uncertainty": {
            "level": confidence,
            "reasonCodes": list(dict.fromkeys(reason_codes)),
            "messages": messages,
            "missingFields": [
                "current_availability",
                "wait_time",
                "capacity",
            ],
            "conflicts": [],
        },
        "tags": [
            *condition_labels[:2],
            *service_labels[:2],
            row["urgency"],
            f"{row['distance_km']:.1f} km",
        ],
    }


def _facility_payload(
    *,
    row: dict,
    rank: int,
    service: dict,
    request_id: str,
    radius: float,
) -> dict:
    facility = row["facility"]
    facility_id = row["facility_id"]
    source_urls = list(facility.get("source_urls") or [])[:4]
    sources = []
    for index, url in enumerate(source_urls, start=1):
        parsed = urlparse(str(url))
        sources.append(
            {
                "id": f"source-{index}",
                "url": str(url),
                "domain": parsed.netloc.removeprefix("www."),
                "sourceType": "unknown",
                "title": parsed.netloc.removeprefix("www."),
                "retrievedAt": datetime.now(timezone.utc).isoformat(),
                "supportsClaims": [],
            }
        )
    source_id = sources[0]["id"] if sources else "record"
    candidate = row["candidate"]
    evidence = []
    for index, quote in enumerate(candidate["quotes"][:4], start=1):
        fields = candidate["fields"]
        roles = candidate["roles"]
        field = (
            fields[0]
            if len(fields) == 1
            else " + ".join(fields)
            if fields
            else "facility_record"
        )
        role = roles[0] if len(roles) == 1 else "service_match"
        evidence.append(
            {
                "id": f"{facility_id}-evidence-{index}",
                "fieldName": field,
                "matchedService": service["service_label"],
                "quote": quote,
                "matchType": "exact" if role == "direct_procedure" else "semantic",
                "polarity": "positive",
                "strength": (
                    "strong"
                    if row["relevance"] >= 0.9
                    else "medium"
                    if row["relevance"] >= 0.65
                    else "weak"
                ),
                "sourceId": source_id,
            }
        )
    return {
        "id": facility_id,
        "rank": rank,
        "name": str(facility.get("name") or "Unnamed facility"),
        "type": str(facility.get("facility_category") or "Healthcare facility").title(),
        "operatorType": str(facility.get("operator_category") or "Unknown").title(),
        "address": str(facility.get("address_city") or facility.get("city_raw") or ""),
        "district": str(facility.get("district") or ""),
        "state": str(facility.get("state") or ""),
        "pincode": str(facility.get("pincode") or ""),
        "phone": (
            str(facility.get("contact_phone")).strip()
            if facility.get("contact_phone") is not None
            and str(facility.get("contact_phone")).strip()
            else None
        ),
        "website": (
            str(facility.get("contact_website")).strip()
            if facility.get("contact_website") is not None
            and str(facility.get("contact_website")).strip()
            else None
        ),
        "latitude": float(facility["rec_lat"]),
        "longitude": float(facility["rec_lon"]),
        "distanceKm": round(row["distance_km"], 1),
        "totalScore": row["final_score"],
        "confidence": (
            "high"
            if row["relevance"] >= 0.9 and bool(evidence)
            else "medium"
            if row["relevance"] >= 0.65
            else "low"
        ),
        "recommendationSummary": (
            f"{service['service_label']} match with "
            f"{len(evidence)} evidence item(s). "
            f"{row['distance_km']:.1f} km away."
        ),
        "scoreBreakdown": {
            "serviceMatchScore": round(row["relevance"] * 100, 1),
            "evidenceScore": round(row["relevance"] * 100, 1),
            "sourceScore": min(100.0, len(sources) * 25.0),
            "distanceScore": round(row["distance_score"] * 100, 1),
            "distanceWeight": round(row["weight"], 2),
            "serviceEvidenceWeight": round(1.0 - row["weight"], 2),
            "searchRadiusKm": radius,
            "urgency": row["urgency"],
            "locationQualityScore": 100.0,
            "capacityScore": 0,
            "penaltyScore": 0,
            "totalScore": row["final_score"],
            "modelVersion": SERVICE_MODEL_VERSION,
        },
        "evidence": evidence,
        "sources": sources,
        "locationQuality": {
            "label": "Medium confidence",
            "note": str(facility.get("location_check") or "Facility record coordinates"),
        },
        "dataCompleteness": min(
            100,
            int(40 + 15 * len(evidence) + 10 * len(sources)),
        ),
        "uncertainty": {
            "level": "medium",
            "reasonCodes": ["LOCAL_MODEL_SNAPSHOT", "CURRENT_AVAILABILITY_UNKNOWN"],
            "messages": [
                f"Urgency: {row['urgency']}; distance weight: {row['weight']:.2f}.",
                "Confirm current service availability before travelling.",
            ],
            "missingFields": ["current_availability", "wait_time"],
            "conflicts": [],
        },
        "tags": [
            service["service_label"],
            row["urgency"],
            f"{row['distance_km']:.1f} km",
        ],
    }
