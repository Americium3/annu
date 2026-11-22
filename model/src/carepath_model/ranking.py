from __future__ import annotations

from dataclasses import dataclass

from .query import Urgency, distance_weight


@dataclass(frozen=True)
class FacilityCandidate:
    unique_id: str
    name: str
    relevance_score: float
    distance_km: float
    radius_km: float
    has_direct_service_evidence: bool


@dataclass(frozen=True)
class RankedFacility:
    unique_id: str
    name: str
    rank: int
    relevance_score: float
    distance_score: float
    final_score: float
    distance_weight: float
    distance_km: float


MIN_RELEVANCE = {
    Urgency.ROUTINE: 0.35,
    Urgency.URGENT: 0.50,
    Urgency.EMERGENCY: 0.65,
}


def rank_candidates(
    candidates: list[FacilityCandidate],
    urgency: Urgency,
) -> list[RankedFacility]:
    weight = distance_weight(urgency)
    minimum_relevance = MIN_RELEVANCE[urgency]
    ranked = []
    for candidate in candidates:
        if not candidate.has_direct_service_evidence:
            continue
        if candidate.relevance_score < minimum_relevance:
            continue
        if candidate.radius_km <= 0 or candidate.distance_km > candidate.radius_km:
            continue
        distance_score = 100.0 * (
            1.0 - max(0.0, min(candidate.distance_km / candidate.radius_km, 1.0))
        )
        relevance_100 = 100.0 * max(0.0, min(candidate.relevance_score, 1.0))
        final_score = (
            (1.0 - weight) * relevance_100
            + weight * distance_score
        )
        ranked.append(
            RankedFacility(
                unique_id=candidate.unique_id,
                name=candidate.name,
                rank=0,
                relevance_score=round(relevance_100, 1),
                distance_score=round(distance_score, 1),
                final_score=round(final_score, 1),
                distance_weight=weight,
                distance_km=round(candidate.distance_km, 1),
            )
        )
    ranked.sort(
        key=lambda item: (
            -item.final_score,
            item.distance_km,
            item.name,
        )
    )
    return [
        RankedFacility(
            unique_id=item.unique_id,
            name=item.name,
            rank=index,
            relevance_score=item.relevance_score,
            distance_score=item.distance_score,
            final_score=item.final_score,
            distance_weight=item.distance_weight,
            distance_km=item.distance_km,
        )
        for index, item in enumerate(ranked, start=1)
    ]
