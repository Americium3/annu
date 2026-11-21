"""Two-stage ranking: retrieve candidates with service evidence, then score them.

Stage 1 (retrieval, hard filters)
  1. The facility has evidence for the service tag (any TF-IDF class), or lists a
     fallback specialty for it. No evidence → never shown, however close.
  2. The facility type suits the service (no dentists for non-dental services,
     no pharmacies).
  3. It lies within the radius. With too few results the radius widens step by
     step, and a warning says so.
  4. Records of the same ``cluster_id`` collapse to the best-scoring one.

Stage 2 (scoring) is in ``scoring.py``.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Literal

from . import config as cfg
from .config import DEFAULT_CONFIG, RANKING_VERSION, RankingConfig
from .features import EvidenceIndex, FacilityRecord, TagEvidence, TagInfo
from .geo import haversine_km
from .scoring import USER_MESSAGES, Match, ScoreResult, classify_match, score_candidate

RankingMode = Literal["best_match", "nearest", "most_evidence"]


class UnknownServiceError(KeyError):
    pass


@dataclass(frozen=True)
class RankQuery:
    tag_id: str
    latitude: float
    longitude: float
    radius_km: float | None = None
    limit: int | None = None
    mode: RankingMode = "best_match"
    allow_widen: bool = True
    as_of: date | None = None  # "today" for recency; fixed in tests


@dataclass
class RankedFacility:
    rank: int
    score: ScoreResult

    @property
    def facility(self) -> FacilityRecord:
        return self.score.facility


@dataclass
class RankingResult:
    tag: TagInfo
    results: list[RankedFacility]
    radius_km: float
    total_candidates: int
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    urgency: str = cfg.DEFAULT_URGENCY
    decay_km: float = 0.0
    ranking_version: str = RANKING_VERSION


@dataclass
class _Candidate:
    facility: FacilityRecord
    match: Match
    distance_km: float


class Ranker:
    def __init__(self, facilities: Iterable[FacilityRecord], evidence: EvidenceIndex,
                 tags: Iterable[TagInfo], config: RankingConfig = DEFAULT_CONFIG,
                 version: str = RANKING_VERSION):
        self.config = config
        self.version = version
        self.facilities: dict[str, FacilityRecord] = {f.unique_id: f for f in facilities}
        self.tags: dict[str, TagInfo] = {t.id: t for t in tags}
        self._evidence_by_tag: dict[str, dict[str, TagEvidence]] = defaultdict(dict)
        for (uid, tag_id), ev in evidence.items():
            self._evidence_by_tag[tag_id][uid] = ev
        self._by_specialty: dict[str, set[str]] = defaultdict(set)
        for f in self.facilities.values():
            for code in f.specialties:
                self._by_specialty[code].add(f.unique_id)

    # ── public ───────────────────────────────────────────────────────────

    def rank(self, q: RankQuery) -> RankingResult:
        tag = self.tags.get(q.tag_id)
        if tag is None:
            raise UnknownServiceError(q.tag_id)
        c = self.config
        as_of = q.as_of or date.today()
        urgency = cfg.urgency_for(tag.id, tag.group)
        decay_km = c.decay_km(urgency)
        stats: dict[str, int] = defaultdict(int)

        candidates = self._retrieve(tag, q, stats)
        radius, widened = self._choose_radius(candidates, q)
        within = [cand for cand in candidates if cand.distance_km <= radius]

        scored = [score_candidate(cand.facility, cand.match, cand.distance_km, decay_km, as_of, c,
                                  cfg.ROAD_DETOUR_FACTOR, self.version) for cand in within]
        scored = self._collapse_clusters(scored, stats)
        ordered = self._order(scored, q.mode)
        limit = q.limit or c.default_limit

        warnings: list[str] = []
        if widened:
            warnings.append("RADIUS_WIDENED")
        if not ordered:
            warnings.append("NO_RESULTS")
        elif len(ordered) < c.min_results:
            warnings.append("FEW_RESULTS")
        return RankingResult(
            tag=tag,
            results=[RankedFacility(i + 1, s) for i, s in enumerate(ordered[:limit])],
            radius_km=radius, total_candidates=len(ordered), warnings=warnings,
            stats=dict(stats), urgency=urgency, decay_km=decay_km, ranking_version=self.version,
        )

    # ── stage 1 ──────────────────────────────────────────────────────────

    def _retrieve(self, tag: TagInfo, q: RankQuery, stats: dict[str, int]) -> list[_Candidate]:
        if tag.is_specialty:
            target_specialties = {tag.id.removeprefix("specialty:")}
        else:
            target_specialties = set(cfg.SPECIALTY_FALLBACK.get(tag.id, ()))
        tag_evidence = {} if tag.is_specialty else self._evidence_by_tag.get(tag.id, {})
        specialty_uids = set().union(*(self._by_specialty.get(s, set()) for s in target_specialties))
        excluded = (cfg.EXCLUDED_CATEGORIES_DENTAL if tag.group == cfg.DENTAL_GROUP
                    else cfg.EXCLUDED_CATEGORIES_NON_DENTAL)

        out: list[_Candidate] = []
        for uid in tag_evidence.keys() | specialty_uids:
            f = self.facilities.get(uid)
            if f is None:  # evidence for a facility not (yet) in the facility table
                stats["skipped_unknown_facility"] += 1
                continue
            if not f.has_coordinates:
                stats["skipped_no_coordinates"] += 1
                continue
            if f.facility_category in excluded:
                stats["skipped_facility_type"] += 1
                continue
            m = classify_match(tag_evidence.get(uid), uid in specialty_uids, tag.is_specialty, self.config)
            if m is None:
                continue
            out.append(_Candidate(f, m, haversine_km(q.latitude, q.longitude, f.latitude, f.longitude)))
        return out

    def _choose_radius(self, candidates: list[_Candidate], q: RankQuery) -> tuple[float, bool]:
        c = self.config
        first = q.radius_km or c.default_radius_km
        radii = [first]
        if q.allow_widen:
            radii += [r for r in c.widen_radii_km if r > first]
        distances = sorted(cand.distance_km for cand in candidates)
        for r in radii:
            if sum(1 for d in distances if d <= r) >= c.min_results:
                return r, r != first
        return radii[-1], radii[-1] != first

    @staticmethod
    def _collapse_clusters(scored: list[ScoreResult], stats: dict[str, int]) -> list[ScoreResult]:
        best: dict[str, ScoreResult] = {}
        sizes: dict[str, int] = defaultdict(int)
        for s in scored:
            key = s.facility.cluster_id or f"uid:{s.facility.unique_id}"
            sizes[key] += 1
            if key not in best or (s.total, -s.distance_km) > (best[key].total, -best[key].distance_km):
                best[key] = s
        for key, s in best.items():
            if sizes[key] > 1:
                stats["collapsed_duplicates"] += sizes[key] - 1
                s.uncertainty.reason_codes.append("DUPLICATE_FACILITY_CLUSTER")
                s.uncertainty.messages.append(USER_MESSAGES["DUPLICATE_FACILITY_CLUSTER"])
        return list(best.values())

    # ── ordering ─────────────────────────────────────────────────────────

    def _order(self, scored: list[ScoreResult], mode: RankingMode) -> list[ScoreResult]:
        if mode == "nearest":
            pool = [s for s in scored if s.gate >= self.config.nearest_min_gate]
            return sorted(pool, key=lambda s: (s.distance_km, -s.total, s.facility.unique_id))
        if mode == "most_evidence":
            return sorted(scored, key=lambda s: (-(s.gate * s.components["evidence"]), -s.total,
                                                 s.facility.unique_id))
        if mode != "best_match":
            raise ValueError(f"unknown ranking mode: {mode}")
        return sorted(scored, key=lambda s: (-s.total, s.distance_km, s.facility.unique_id))
