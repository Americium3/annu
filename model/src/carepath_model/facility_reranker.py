from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .query import Urgency


MODEL_VERSION = "structured-evidence-reranker-v1"

RERANK_WEIGHTS = {
    Urgency.ROUTINE: {
        "text": 0.35,
        "evidence": 0.15,
        "distance": 0.50,
    },
    Urgency.URGENT: {
        "text": 0.20,
        "evidence": 0.05,
        "distance": 0.75,
    },
    Urgency.EMERGENCY: {
        "text": 0.08,
        "evidence": 0.02,
        "distance": 0.90,
    },
}

ROUTE_SPECIFICITY = {
    "condition_action": 1.00,
    "condition_action_service": 1.00,
    "related_condition_action": 0.82,
    "related_condition_action_service": 0.82,
    "condition_text_tag": 0.72,
    "related_condition_text_tag": 0.62,
    "related_treatment_text": 0.55,
    "condition_related_tag": 0.48,
}

FIELD_SPECIFICITY = {
    "procedure_arr": 1.00,
    "capability_arr": 0.85,
    "equipment_arr": 0.58,
    "facility_record": 0.35,
}

STRENGTH_SPECIFICITY = {
    "strong": 1.00,
    "medium": 0.70,
    "weak": 0.40,
}


@dataclass(frozen=True)
class RerankResult:
    text_score: float
    evidence_score: float
    distance_score: float
    total_score: float
    weights: dict[str, float]
    best_evidence_text: str
    scored_item_count: int


def rerank_condition_candidate(
    candidate: dict[str, Any],
    *,
    distance_score: float,
    urgency: Urgency,
    facility_source_count: int,
    candidate_pool_size: int,
) -> RerankResult:
    """Second-stage structured reranker for an already-retrieved facility."""

    evidence = list(candidate.get("evidence") or [])
    direct = float(candidate.get("direct_relevance") or 0.0)
    weak = float(candidate.get("weak_relevance") or 0.0)
    relevance = float(candidate.get("relevance") or max(direct, weak))
    text_score = 100.0 * max(0.0, min(relevance, 1.0))

    if evidence:
        route_specificity = sum(
            ROUTE_SPECIFICITY.get(str(item.get("route_type") or ""), 0.35)
            for item in evidence
        ) / len(evidence)
        field_specificity = sum(
            FIELD_SPECIFICITY.get(str(item.get("field") or ""), 0.35)
            for item in evidence
        ) / len(evidence)
        strength_specificity = sum(
            STRENGTH_SPECIFICITY.get(str(item.get("strength") or ""), 0.35)
            for item in evidence
        ) / len(evidence)
    else:
        route_specificity = field_specificity = strength_specificity = 0.0

    count_score = min(len(evidence), 4) / 4.0
    source_score = min(max(facility_source_count, 0), 4) / 4.0

    if direct > 0:
        evidence_score = min(
            100.0,
            100.0
            * (
                0.55
                + 0.24 * route_specificity
                + 0.08 * field_specificity
                + 0.05 * strength_specificity
                + 0.05 * count_score
                + 0.03 * source_score
            ),
        )
    else:
        evidence_score = min(
            75.0,
            100.0
            * (
                0.08
                + 0.24 * route_specificity
                + 0.14 * field_specificity
                + 0.10 * strength_specificity
                + 0.18 * count_score
                + 0.08 * source_score
            ),
        )

    distance_100 = 100.0 * max(0.0, min(distance_score, 1.0))
    weights = RERANK_WEIGHTS[urgency]
    total = (
        weights["text"] * text_score
        + weights["evidence"] * evidence_score
        + weights["distance"] * distance_100
    )
    best = max(
        evidence,
        key=lambda item: (
            ROUTE_SPECIFICITY.get(str(item.get("route_type") or ""), 0.35),
            FIELD_SPECIFICITY.get(str(item.get("field") or ""), 0.35),
            STRENGTH_SPECIFICITY.get(str(item.get("strength") or ""), 0.35),
        ),
        default={},
    )
    return RerankResult(
        text_score=round(text_score, 1),
        evidence_score=round(evidence_score, 1),
        distance_score=round(distance_100, 1),
        total_score=round(total, 1),
        weights=weights,
        best_evidence_text=str(best.get("quote") or ""),
        scored_item_count=candidate_pool_size,
    )
