"""Explainable rule-based facility ranker (phase 1 of the recommendation model).

See docs/ranking_model.md for the model and app/ranking/config.py for every weight.
"""
from .config import DEFAULT_CONFIG, RANKING_VERSION, RankingConfig
from .features import FacilityRecord, TagEvidence, TagInfo, check_schema, facility_from_row
from .ranker import RankedFacility, Ranker, RankingResult, RankQuery, UnknownServiceError

__all__ = [
    "DEFAULT_CONFIG", "RANKING_VERSION", "RankingConfig",
    "FacilityRecord", "TagEvidence", "TagInfo", "check_schema", "facility_from_row",
    "RankedFacility", "Ranker", "RankingResult", "RankQuery", "UnknownServiceError",
]
