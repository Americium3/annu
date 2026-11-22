from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from collections import defaultdict
import re

from .query import Urgency, detect_urgency
from .taxonomy import normalize_text


RELATION_WEIGHTS = {
    "treats": 1.00,
    "investigates": 0.90,
    "is_observable_through": 0.65,
    "is_prenatally_observable_through": 0.50,
    "prevents": 0.40,
}

EXCLUDED_RELATIONS = {
    "contraindicated",
    "lack of observed response",
    "no_observed_benefit",
    "unknown",
}

CONDITION_ALIAS_OVERRIDES = {
    "heart attack": ("Myocardial infarction",),
    "myocardial infarct": ("Myocardial infarction",),
    "shortness of breath": ("Dyspnea",),
    "difficulty breathing": ("Dyspnea",),
    "trouble breathing": ("Dyspnea",),
    "cannot breathe": ("Dyspnea",),
    "can t breathe": ("Dyspnea",),
    "breathlessness": ("Dyspnea",),
    "belly pain": ("Abdominal pain",),
    "stomach pain": ("Abdominal pain",),
    "stomach ache": ("Abdominal pain",),
    "high temperature": ("Fever",),
    "high fever": ("Fever",),
    "brain attack": ("Stroke",),
    "cerebrovascular accident": ("Stroke",),
    "chest discomfort": ("Chest pain",),
}

RELATED_TERMS = {
    "chest pain": (
        "chest pain",
        "chest discomfort",
        "angina",
    ),
    "dyspnea": (
        "dyspnea",
        "dyspnoea",
        "shortness of breath",
        "difficulty breathing",
        "breathlessness",
    ),
    "stroke": (
        "stroke",
        "brain attack",
        "cerebrovascular accident",
    ),
    "myocardial infarction": (
        "myocardial infarction",
        "heart attack",
        "myocardial infarct",
    ),
    "fever": (
        "fever",
        "pyrexia",
        "high temperature",
    ),
    "abdominal pain": (
        "abdominal pain",
        "stomach pain",
        "belly pain",
        "abdominal discomfort",
    ),
    "pneumonia": ("pneumonia",),
    "diabetes mellitus": ("diabetes mellitus", "diabetes", "diabetic"),
    "asthma": ("asthma", "asthmatic"),
    "headache": ("headache", "head pain"),
}

RELATED_TREATMENT_PROFILES = {
    "fever": {
        "terms": (
            "fever",
            "pyrexia",
            "infection",
            "infectious",
            "general physician",
            "internal medicine",
            "blood test",
            "pathology",
        ),
        "tags": (
            ("fever-infections", 0.80),
            ("pathology-lab", 0.40),
            ("emergency-24x7", 0.30),
        ),
    },
    "pneumonia": {
        "terms": (
            "pneumonia",
            "pneumonitis",
            "respiratory infection",
            "chest infection",
            "chest x-ray",
            "chest radiograph",
            "chest ct",
            "spirometry",
            "pulmonary function",
            "pulmonology",
            "respiratory medicine",
        ),
        "tags": (
            ("x-ray", 0.45),
            ("ct-scan", 0.40),
            ("pulmonary-function", 0.40),
            ("asthma-copd", 0.30),
            ("emergency-24x7", 0.25),
        ),
    },
    "chest pain": {
        "terms": (
            "chest pain",
            "angina",
            "ecg",
            "electrocardiography",
            "echocardiography",
            "coronary angiograph",
            "angioplasty",
            "cardiac catheter",
            "pci",
        ),
        "tags": (
            ("heart-disease", 0.60),
            ("ecg", 0.55),
            ("echocardiography", 0.50),
            ("angiography", 0.50),
            ("angioplasty", 0.50),
            ("emergency-24x7", 0.45),
        ),
    },
    "abdominal pain": {
        "terms": (
            "abdominal pain",
            "stomach pain",
            "abdominal discomfort",
            "abdominal ultrasound",
            "abdominal ct",
            "endoscopy",
            "gastroscopy",
            "appendectomy",
            "gallbladder",
            "gastroenterology",
        ),
        "tags": (
            ("ultrasound", 0.45),
            ("ct-scan", 0.40),
            ("endoscopy", 0.40),
            ("appendicitis", 0.35),
            ("gallstones", 0.30),
        ),
    },
    "stroke": {
        "terms": (
            "stroke",
            "thrombolysis",
            "thrombectomy",
            "stroke unit",
            "neuro intensive",
            "neurointensive",
            "ct brain",
            "mri brain",
            "neurointervention",
        ),
        "tags": (
            ("stroke", 0.80),
            ("icu", 0.55),
            ("ct-scan", 0.50),
            ("mri", 0.45),
            ("neurosurgery", 0.40),
            ("emergency-24x7", 0.45),
        ),
    },
    "asthma": {
        "terms": (
            "asthma",
            "spirometry",
            "pulmonary function",
            "bronchodilator",
            "wheezing",
            "nebulization",
            "respiratory medicine",
        ),
        "tags": (
            ("asthma-copd", 0.80),
            ("pulmonary-function", 0.50),
            ("emergency-24x7", 0.30),
        ),
    },
    "diabetes mellitus": {
        "terms": (
            "diabetes",
            "diabetic",
            "hba1c",
            "insulin",
            "blood sugar",
            "endocrinology",
            "diabetic retinopathy",
        ),
        "tags": (
            ("diabetes", 0.80),
            ("pathology-lab", 0.40),
            ("retina", 0.30),
        ),
    },
    "falls": {
        "terms": (
            "falls",
            "fall injury",
            "fall-related",
            "fracture",
            "trauma",
            "head injury",
            "x-ray",
            "ct scan",
            "mobility assessment",
            "physiotherapy",
        ),
        "tags": (
            ("fracture-trauma", 0.70),
            ("x-ray", 0.50),
            ("ct-scan", 0.40),
            ("emergency-24x7", 0.40),
            ("physiotherapy", 0.25),
        ),
    },
    "headache": {
        "terms": (
            "headache",
            "migraine",
            "neurology",
            "neurologist",
            "brain ct",
            "brain mri",
        ),
        "tags": (
            ("headache-migraine", 0.80),
            ("ct-scan", 0.35),
            ("mri", 0.30),
        ),
    },
    "back pain": {
        "terms": (
            "back pain",
            "neck pain",
            "spinal pain",
            "physiotherapy",
            "spine",
            "x-ray",
            "mri",
        ),
        "tags": (
            ("back-pain", 0.80),
            ("physiotherapy", 0.40),
            ("spine-surgery", 0.30),
            ("mri", 0.30),
            ("x-ray", 0.30),
        ),
    },
}

RELATED_FAMILY_TERMS = {
    "fever": ("fever", "pyrexia", "febrile"),
    "pneumonia": ("pneumonia", "pneumonitis"),
    "chest pain": ("chest pain",),
    "abdominal pain": ("abdominal pain",),
    "stroke": ("stroke", "cerebrovascular"),
    "asthma": ("asthma", "asthmatic"),
    "diabetes mellitus": ("diabetes", "diabetic"),
    "falls": ("falls", "frequent falls"),
    "headache": ("headache", "migraine"),
    "back pain": ("back pain", "neck pain"),
}

COMMON_CONDITIONS = (
    "Chest pain",
    "Dyspnea",
    "Fever",
    "Stroke",
    "Abdominal pain",
    "Pneumonia",
    "Diabetes mellitus",
    "Asthma",
    "Headache",
)

NEGATION_RE = re.compile(
    r"\b(no|not|without|denies|denied|never|ruled out)\b|没有|无|否认|并非",
    re.IGNORECASE,
)

TOKEN_RE = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]+")


@dataclass(frozen=True)
class ConditionMatch:
    condition_id: str
    condition_label: str
    matched_text: str
    confidence: float
    match_method: str
    source_kind: str


@dataclass(frozen=True)
class ConditionServiceRoute:
    service_id: str
    service_label: str
    action_ids: tuple[str, ...]
    action_labels: tuple[str, ...]
    condition_ids: tuple[str, ...]
    condition_labels: tuple[str, ...]
    score: float
    route_type: str


@dataclass(frozen=True)
class RelatedConditionTag:
    tag_id: str
    label: str
    weight: float


@dataclass(frozen=True)
class ConditionMapping:
    input_text: str
    urgency: Urgency
    conditions: tuple[ConditionMatch, ...]
    related_conditions: tuple[ConditionMatch, ...]
    services: tuple[ConditionServiceRoute, ...]
    treatment_terms: tuple[str, ...]
    related_tags: tuple[RelatedConditionTag, ...]
    negated_mentions: tuple[str, ...]


@dataclass(frozen=True)
class _AliasMatch:
    start: int
    end: int
    alias: str
    target: str
    confidence: float
    method: str


class ConditionServiceMapper:
    """Deterministic baseline from symptom/disease text to service candidates."""

    def __init__(
        self,
        condition_edges: list[dict],
        service_actions: list[dict],
        clinical_tags: list[dict] | None = None,
    ) -> None:
        self._edges_by_condition: dict[str, list[dict]] = defaultdict(list)
        self._condition_ids_by_label: dict[str, set[str]] = defaultdict(set)
        self._label_by_normalized: dict[str, str] = {}
        self._source_kind_by_id: dict[str, str] = {}
        self._service_links_by_action: dict[str, list[dict]] = defaultdict(list)
        self._clinical_tags = tuple(clinical_tags or ())

        for edge in condition_edges:
            condition_id = str(edge["condition_id"])
            label = str(edge["condition_label"])
            normalized = normalize_text(label)
            if not normalized:
                continue
            self._edges_by_condition[condition_id].append(edge)
            self._condition_ids_by_label[normalized].add(condition_id)
            self._label_by_normalized[normalized] = label
            self._source_kind_by_id[condition_id] = str(
                edge.get("source_kind") or "condition"
            )

        for link in service_actions:
            self._service_links_by_action[str(link["action_id"])].append(link)

        aliases: dict[tuple[str, str], tuple[float, str]] = {}
        for normalized, label in self._label_by_normalized.items():
            aliases[(normalized, normalized)] = (1.0, "canonical")

        for alias, targets in CONDITION_ALIAS_OVERRIDES.items():
            normalized_alias = normalize_text(alias)
            for target in targets:
                normalized_target = normalize_text(target)
                if normalized_target not in self._label_by_normalized:
                    continue
                aliases[(normalized_alias, normalized_target)] = (
                    0.92,
                    "curated_alias",
                )

        self._aliases = tuple(
            (alias, target, confidence, method)
            for (alias, target), (confidence, method) in aliases.items()
            if len(alias) >= 3 or (
                len(alias) >= 2 and re.search(r"[^\x00-\x7f]", alias)
            )
        )

    @property
    def condition_count(self) -> int:
        return len(self._condition_ids_by_label)

    def resolve(self, text: str) -> ConditionMapping:
        normalized = self._normalize_clauses(text)
        urgency = detect_urgency(text)
        raw_matches: list[_AliasMatch] = []
        negated: list[str] = []

        for alias, target, confidence, method in self._aliases:
            for start, end in self._find_alias(normalized, alias):
                if self._is_negated(normalized, start):
                    negated.append(alias)
                    continue
                raw_matches.append(
                    _AliasMatch(
                        start=start,
                        end=end,
                        alias=alias,
                        target=target,
                        confidence=confidence,
                        method=method,
                    )
                )

        selected = self._select_non_overlapping(raw_matches)
        matches: list[ConditionMatch] = []
        for alias_match in selected:
            for condition_id in sorted(
                self._condition_ids_by_label[alias_match.target]
            ):
                matches.append(
                    ConditionMatch(
                        condition_id=condition_id,
                        condition_label=self._label_by_normalized[alias_match.target],
                        matched_text=normalized[alias_match.start : alias_match.end],
                        confidence=alias_match.confidence,
                        match_method=alias_match.method,
                        source_kind=self._source_kind_by_id.get(
                            condition_id, "condition"
                        ),
                    )
                )

        if not matches:
            matches.extend(self._fuzzy_matches(normalized.replace(" | ", " ")))

        matches.sort(
            key=lambda item: (
                -item.confidence,
                -len(item.matched_text),
                item.condition_label.casefold(),
            )
        )
        matches = matches[:4]
        related_conditions = self._related_conditions(matches)
        services = self._expand_services(matches, related_conditions)
        treatment_terms = self._treatment_terms(matches, related_conditions)
        related_tags = self._related_tags(matches, related_conditions)
        return ConditionMapping(
            input_text=text,
            urgency=urgency,
            conditions=tuple(matches),
            related_conditions=tuple(related_conditions),
            services=tuple(services),
            treatment_terms=tuple(treatment_terms),
            related_tags=tuple(related_tags),
            negated_mentions=tuple(dict.fromkeys(negated)),
        )

    def search_terms(self, condition_label: str) -> tuple[str, ...]:
        normalized = normalize_text(condition_label)
        related = RELATED_TERMS.get(normalized, ())
        return tuple(
            dict.fromkeys(
                normalize_text(term)
                for term in (condition_label, *related)
                if normalize_text(term)
            )
        )

    def suggest_conditions(self, query: str, limit: int = 8) -> list[dict]:
        normalized_query = normalize_text(query)
        query_tokens = set(self._tokens(normalized_query))
        suggestions = []

        for normalized_label, label in self._label_by_normalized.items():
            if not normalized_query and label not in COMMON_CONDITIONS:
                continue
            label_tokens = set(self._tokens(normalized_label))
            if normalized_query:
                substring = (
                    normalized_query in normalized_label
                    or normalized_label in normalized_query
                )
                overlap = len(query_tokens & label_tokens) / max(
                    len(query_tokens | label_tokens), 1
                )
                ratio = SequenceMatcher(
                    None, normalized_query, normalized_label
                ).ratio()
                if not substring and overlap < 0.34 and ratio < 0.55:
                    continue
                score = max(
                    1.0 if substring else 0.0,
                    0.75 * overlap,
                    0.65 * ratio,
                )
            else:
                score = 1.0 - COMMON_CONDITIONS.index(label) * 0.01

            condition_ids = sorted(self._condition_ids_by_label[normalized_label])
            first_id = condition_ids[0]
            suggestions.append(
                {
                    "id": first_id,
                    "name": label,
                    "synonyms": list(self.search_terms(label))[:6],
                    "category": self._source_kind_by_id.get(first_id, "condition"),
                    "actionCount": len(self._edges_by_condition[first_id]),
                    "_score": score,
                }
            )

        suggestions.sort(
            key=lambda item: (
                -float(item["_score"]),
                len(item["name"]),
                item["name"].casefold(),
            )
        )
        return [
            {key: value for key, value in item.items() if key != "_score"}
            for item in suggestions[:limit]
        ]

    def _related_conditions(
        self,
        matches: list[ConditionMatch],
    ) -> list[ConditionMatch]:
        matched_ids = {item.condition_id for item in matches}
        matched_labels = {
            normalize_text(item.condition_label) for item in matches
        }
        excluded = re.compile(
            r"\b(family history|history of|post[-\s]?vaccination|"
            r"inappropriate absence|exposure|screening)\b",
            re.IGNORECASE,
        )
        inferred: dict[str, ConditionMatch] = {}
        for base in matches:
            normalized = normalize_text(base.condition_label)
            family_terms = RELATED_FAMILY_TERMS.get(normalized)
            if not family_terms:
                family_terms = tuple(
                    token
                    for token in self._tokens(normalized)
                    if len(token) >= 5
                )
            for label_norm, label in self._label_by_normalized.items():
                if label_norm in matched_labels or excluded.search(label):
                    continue
                if normalized == "diabetes mellitus" and "insipidus" in label_norm:
                    continue
                if not any(
                    self._contains_term(label_norm, term)
                    for term in family_terms
                ):
                    continue
                for condition_id in self._condition_ids_by_label[label_norm]:
                    if condition_id in matched_ids:
                        continue
                    inferred[condition_id] = ConditionMatch(
                        condition_id=condition_id,
                        condition_label=label,
                        matched_text=next(
                            (
                                term
                                for term in family_terms
                                if self._contains_term(label_norm, term)
                            ),
                            label_norm,
                        ),
                        confidence=round(base.confidence * 0.55, 3),
                        match_method="related_condition",
                        source_kind=self._source_kind_by_id.get(
                            condition_id, "condition"
                        ),
                    )
        return sorted(
            inferred.values(),
            key=lambda item: (
                -item.confidence,
                len(item.condition_label),
                item.condition_label.casefold(),
            ),
        )[:16]

    @staticmethod
    def _contains_term(text: str, term: str) -> bool:
        if re.search(r"[^\x00-\x7f]", term):
            return term in text
        return bool(
            re.search(
                rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])",
                text,
            )
        )

    def _treatment_terms(
        self,
        matches: list[ConditionMatch],
        related_conditions: list[ConditionMatch],
    ) -> list[str]:
        terms: list[str] = []
        for condition in (*matches, *related_conditions):
            terms.extend(self.search_terms(condition.condition_label))
            normalized = normalize_text(condition.condition_label)
            for profile_key, profile in RELATED_TREATMENT_PROFILES.items():
                if profile_key in normalized or normalized in profile_key:
                    terms.extend(
                        normalize_text(term)
                        for term in profile["terms"]
                    )
        return list(dict.fromkeys(term for term in terms if term))

    def _related_tags(
        self,
        matches: list[ConditionMatch],
        related_conditions: list[ConditionMatch],
    ) -> list[RelatedConditionTag]:
        if not self._clinical_tags:
            return []
        tag_by_id = {
            str(tag.get("tag_id")): tag for tag in self._clinical_tags
        }
        weights: dict[str, float] = {}
        for condition in (*matches, *related_conditions):
            normalized = normalize_text(condition.condition_label)
            for profile_key, profile in RELATED_TREATMENT_PROFILES.items():
                if profile_key in normalized or normalized in profile_key:
                    for tag_id, weight in profile["tags"]:
                        weights[tag_id] = max(
                            weights.get(tag_id, 0.0),
                            weight * condition.confidence,
                        )
            condition_tokens = {
                token
                for token in self._tokens(normalized)
                if len(token) >= 4
                and token
                not in {
                    "disease",
                    "disorder",
                    "pain",
                    "syndrome",
                    "mellitus",
                }
            }
            for tag_id, tag in tag_by_id.items():
                tag_norm = normalize_text(str(tag.get("label") or ""))
                if not tag_norm:
                    continue
                tag_tokens = set(self._tokens(tag_norm))
                overlap = condition_tokens & tag_tokens
                if not overlap:
                    continue
                coverage = len(overlap) / max(len(condition_tokens), 1)
                weights[tag_id] = max(
                    weights.get(tag_id, 0.0),
                    condition.confidence * 0.50 * coverage,
                )
        tags = [
            RelatedConditionTag(
                tag_id=tag_id,
                label=str(tag_by_id[tag_id].get("label") or tag_id),
                weight=round(weight, 4),
            )
            for tag_id, weight in weights.items()
            if tag_id in tag_by_id and weight >= 0.15
        ]
        return sorted(
            tags,
            key=lambda item: (-item.weight, item.label.casefold()),
        )[:12]

    def _expand_services(
        self,
        matches: list[ConditionMatch],
        related_conditions: list[ConditionMatch],
    ) -> list[ConditionServiceRoute]:
        merged: dict[str, dict] = {}
        conditions = [
            *((condition, False) for condition in matches),
            *((condition, True) for condition in related_conditions),
        ]
        for condition, inferred in conditions:
            inference_factor = 0.55 if inferred else 1.0
            for edge in self._edges_by_condition[condition.condition_id]:
                relation = str(edge.get("relation") or "")
                relation_weight = RELATION_WEIGHTS.get(relation, 0.0)
                if relation in EXCLUDED_RELATIONS or relation_weight <= 0:
                    continue
                action_id = str(edge["action_id"])
                action_label = str(edge.get("action_label") or action_id)
                links = self._service_links_by_action.get(action_id, [])
                if not links:
                    self._merge_service(
                        merged,
                        service_id=f"action:{action_id}",
                        service_label=action_label,
                        score=(
                            condition.confidence
                            * relation_weight
                            * 0.70
                            * inference_factor
                        ),
                        route_type=(
                            "related_condition_action"
                            if inferred
                            else "condition_action"
                        ),
                        action_id=action_id,
                        action_label=action_label,
                        condition=condition,
                    )
                    continue
                for link in links:
                    self._merge_service(
                        merged,
                        service_id=str(link["service_id"]),
                        service_label=str(link.get("action_label") or action_label),
                        score=(
                            condition.confidence
                            * relation_weight
                            * float(link.get("confidence") or 0.7)
                            * inference_factor
                        ),
                        route_type=(
                            "related_condition_action_service"
                            if inferred
                            else "condition_action_service"
                        ),
                        action_id=action_id,
                        action_label=action_label,
                        condition=condition,
                    )

        services = sorted(
            merged.values(),
            key=lambda item: (
                -float(item["score"]),
                item["service_label"].casefold(),
            ),
        )[:12]
        return [
            ConditionServiceRoute(
                service_id=item["service_id"],
                service_label=item["service_label"],
                action_ids=tuple(sorted(item["action_ids"])),
                action_labels=tuple(sorted(item["action_labels"])),
                condition_ids=tuple(sorted(item["condition_ids"])),
                condition_labels=tuple(sorted(item["condition_labels"])),
                score=round(float(item["score"]), 4),
                route_type=item["route_type"],
            )
            for item in services
        ]

    @staticmethod
    def _merge_service(
        merged: dict[str, dict],
        *,
        service_id: str,
        service_label: str,
        score: float,
        route_type: str,
        action_id: str,
        action_label: str,
        condition: ConditionMatch,
    ) -> None:
        item = merged.setdefault(
            service_id,
            {
                "service_id": service_id,
                "service_label": service_label,
                "score": 0.0,
                "route_type": route_type,
                "action_ids": set(),
                "action_labels": set(),
                "condition_ids": set(),
                "condition_labels": set(),
            },
        )
        item["score"] = max(float(item["score"]), score)
        item["action_ids"].add(action_id)
        item["action_labels"].add(action_label)
        item["condition_ids"].add(condition.condition_id)
        item["condition_labels"].add(condition.condition_label)

    def _fuzzy_matches(self, normalized: str) -> list[ConditionMatch]:
        if not normalized or len(normalized) > 120:
            return []
        labels = sorted(self._label_by_normalized)
        best = sorted(
            (
                (
                    SequenceMatcher(None, normalized, label).ratio(),
                    label,
                )
                for label in labels
            ),
            reverse=True,
        )[:3]
        matches = []
        for score, label in best:
            if score < 0.82:
                continue
            for condition_id in sorted(self._condition_ids_by_label[label]):
                matches.append(
                    ConditionMatch(
                        condition_id=condition_id,
                        condition_label=self._label_by_normalized[label],
                        matched_text=normalized,
                        confidence=round(min(score, 0.80), 3),
                        match_method="fuzzy",
                        source_kind=self._source_kind_by_id.get(
                            condition_id, "condition"
                        ),
                    )
                )
        return matches

    @staticmethod
    def _find_alias(text: str, alias: str) -> list[tuple[int, int]]:
        if not text or not alias:
            return []
        if re.search(r"[^\x00-\x7f]", alias):
            positions = []
            start = text.find(alias)
            while start >= 0:
                positions.append((start, start + len(alias)))
                start = text.find(alias, start + 1)
            return positions

        padded = f" {text} "
        needle = f" {alias} "
        positions = []
        start = padded.find(needle)
        while start >= 0:
            positions.append((start, start + len(alias)))
            start = padded.find(needle, start + 1)
        return positions

    @staticmethod
    def _select_non_overlapping(matches: list[_AliasMatch]) -> list[_AliasMatch]:
        selected: list[_AliasMatch] = []
        for match in sorted(
            matches,
            key=lambda item: (
                -(item.end - item.start),
                -item.confidence,
                item.alias,
            ),
        ):
            if any(
                match.start < existing.end and match.end > existing.start
                for existing in selected
            ):
                continue
            selected.append(match)
        return selected

    @staticmethod
    def _is_negated(text: str, start: int) -> bool:
        prefix = text[max(0, start - 35) : start].rsplit("|", 1)[-1]
        return bool(NEGATION_RE.search(prefix))

    @staticmethod
    def _tokens(text: str) -> tuple[str, ...]:
        return tuple(TOKEN_RE.findall(text))

    @staticmethod
    def _normalize_clauses(text: str) -> str:
        clauses = re.split(
            r"[,;.!?\n，；。、]|\b(?:and|but|or|while|also|with|plus)\b|并|和|以及|伴有",
            text,
            flags=re.IGNORECASE,
        )
        return " | ".join(
            normalized
            for clause in clauses
            if (normalized := normalize_text(clause))
        )
