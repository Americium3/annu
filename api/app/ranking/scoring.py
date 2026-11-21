"""Score one candidate facility for one service query.

    total = clamp(100 × G × F − P, 0, 100)

    G  evidence gate, from how the facility matched the service (config.gate)
    F  weighted sum of six 0–1 components (config.weights)
    P  penalty points for data-quality flags, capped at config.max_penalty

Because G multiplies everything, being close or large can never make up for weak
evidence. Missing data scores neutral, not zero: the dataset is incomplete and
still being cleaned, so absence of a value is not evidence of absence.

Confidence is computed separately from the score. A facility can rank first
among few candidates and still be low-confidence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from .config import RankingConfig
from .features import EVIDENCE_FIELDS, FacilityRecord, TagEvidence

# Probability assumed when a class is known but its probability is not.
_CLASS_DEFAULT_PROBABILITY = {"strong": 0.75, "mention": 0.3, "suggested": 0.8}
_SPECIALTY_ONLY_EVIDENCE = 0.25

USER_MESSAGES = {
    "SPECIALTY_ONLY_MATCH": "Matched on a listed specialty only; no sentence describes this service.",
    "MODEL_SUGGESTED_MATCH": "Matched by the text classifier, not by an exact service term; check the evidence.",
    "SERVICE_MENTION_ONLY": "The service is only named in passing (for example inside a long list).",
    "NEGATED_SERVICE_CLAIM": "Some sources say this service is not available or only planned.",
    "LOCATION_PIN_CONFLICT": "The map position and the PIN code disagree; the location may be off.",
    "LOW_PIN_CONFIDENCE": "The location of this facility is uncertain.",
    "ADDRESS_INCONSISTENT": "The written address, PIN code and map position do not agree.",
    "NO_OFFICIAL_SOURCE": "No official website was found for this facility.",
    "STALE_SOURCE": "The facility's own pages have not been updated recently.",
    "CAPACITY_UNPARSEABLE": "Published bed or doctor counts look implausible and were ignored.",
    "DUPLICATE_FACILITY_CLUSTER": "This facility appears more than once in the sources; the best record is shown.",
}


@dataclass(frozen=True)
class Match:
    """How a facility matched the requested service."""
    gate_key: str  # key into config.gate
    evidence: TagEvidence | None
    specialty_hit: bool


def classify_match(evidence: TagEvidence | None, specialty_hit: bool, specialty_query: bool,
                   config: RankingConfig) -> Match | None:
    """Return the match type, or None if the facility is not a candidate at all."""
    if specialty_query:
        return Match("specialty_query", None, True) if specialty_hit else None
    if evidence is None:
        return Match("specialty_only", None, True) if specialty_hit else None
    cls = evidence.tag_class
    if cls == "strong":
        key = "strong"
    elif cls == "suggested":
        key = "suggested"
        if specialty_hit and config.gate["specialty_only"] > config.gate["suggested"]:
            key = "specialty_only"
    else:  # "mention", or a class value added to the pipeline later
        key = "mention_with_specialty" if specialty_hit else "mention"
    return Match(key, evidence, specialty_hit)


# ── components (each 0–1) ────────────────────────────────────────────────

def service_match_component(m: Match) -> float:
    if m.gate_key == "specialty_query":
        return 1.0
    if m.gate_key == "specialty_only":
        return 0.5
    if m.gate_key == "suggested":
        return 0.6
    return 1.0 if m.specialty_hit else 0.85


def _corroborating_fields(m: Match) -> int:
    if m.evidence is None:
        return int(m.specialty_hit)
    # At least one field matched even when the field list wasn't loaded.
    n_fields = max(1, len(m.evidence.fields & set(EVIDENCE_FIELDS)))
    return n_fields + int(m.specialty_hit)


def evidence_component(m: Match) -> float:
    ev = m.evidence
    if ev is None:
        return _SPECIALTY_ONLY_EVIDENCE
    prob = ev.best_probability
    if prob is None:
        prob = _CLASS_DEFAULT_PROBABILITY.get(ev.tag_class, 0.3)
    n = _corroborating_fields(m)
    corroboration = {0: 0.0, 1: 0.4, 2: 0.75}.get(n, 1.0)
    volume = min(1.0, math.log1p(max(ev.sentence_count, 1)) / math.log1p(5))
    return 0.5 * min(max(prob, 0.0), 1.0) + 0.3 * corroboration + 0.2 * volume


def distance_component(road_km: float, decay_km: float) -> float:
    return math.exp(-max(road_km, 0.0) / decay_km)


def _log_scaled(value: int | None, full: int, neutral: float) -> float:
    if value is None or value < 0:
        return neutral
    return min(1.0, math.log1p(value) / math.log1p(full))


def capacity_component(f: FacilityRecord, config: RankingConfig) -> tuple[float, bool]:
    """(score, ignored_implausible). Missing or implausible values count as neutral."""
    beds_bad = bool({"impossible_beds", "implausible_scale"} & f.flags)
    docs_bad = bool({"impossible_doctors", "suspect_doctor_count", "implausible_scale"} & f.flags)
    neutral = config.capacity_neutral
    parts = (
        _log_scaled(None if beds_bad else f.n_beds, config.capacity_full_beds, neutral),
        _log_scaled(None if docs_bad else f.n_doctors, config.capacity_full_doctors, neutral),
        _log_scaled(f.n_specialties, config.capacity_full_specialties, neutral),
    )
    ignored = (beds_bad and f.n_beds is not None) or (docs_bad and f.n_doctors is not None)
    return sum(parts) / len(parts), ignored


def _days_since_activity(f: FacilityRecord, as_of: date) -> int | None:
    dates = [d for d in (f.page_last_updated, f.last_social_post) if d is not None]
    return (as_of - max(dates)).days if dates else None


def source_component(f: FacilityRecord, as_of: date, config: RankingConfig) -> float:
    website = 1.0 if f.official_website else 0.0
    urls = 0.5 if f.n_source_urls is None else min(1.0, f.n_source_urls / config.full_source_urls)
    age = _days_since_activity(f, as_of)
    recency = config.recency_missing_score if age is None else 0.5 ** (max(age, 0) / config.recency_half_life_days)
    return 0.3 * website + 0.2 * urls + 0.5 * recency


def location_quality_component(f: FacilityRecord, config: RankingConfig) -> float:
    return config.location_confidence_score.get(f.location_confidence or "", config.unknown_location_confidence_score)


# ── result ───────────────────────────────────────────────────────────────

@dataclass
class Uncertainty:
    level: str
    reason_codes: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "reason_codes": list(self.reason_codes),
            "messages": list(self.messages),
            "missing_fields": list(self.missing_fields),
            "conflicts": list(self.conflicts),
        }


@dataclass
class ScoreResult:
    facility: FacilityRecord
    match: Match
    distance_km: float
    components: dict[str, float]  # 0–1, keyed like config.weights
    gate: float
    penalty: float
    total: float  # 0–100
    confidence: str
    uncertainty: Uncertainty
    weights: dict[str, float]
    ranking_version: str

    def breakdown(self) -> dict:
        """ScoreBreakdown in the API contract's shape (0–100 values)."""
        c = {k: round(100 * v, 1) for k, v in self.components.items()}
        return {
            "service_match_score": c["service_match"],
            "evidence_score": c["evidence"],
            "source_score": c["source"],
            "distance_score": c["distance"],
            "location_quality_score": c["location_quality"],
            "capacity_score": c["capacity"],
            "penalty_score": round(self.penalty, 1),
            "evidence_gate": round(self.gate, 2),
            "match_type": self.match.gate_key,
            "weights": dict(self.weights),
            "total_score": round(self.total, 1),
            "model_version": self.ranking_version,
        }


def score_candidate(f: FacilityRecord, m: Match, distance_km: float, decay_km: float,
                    as_of: date, config: RankingConfig, road_detour_factor: float,
                    version: str) -> ScoreResult:
    capacity, capacity_ignored = capacity_component(f, config)
    components = {
        "service_match": service_match_component(m),
        "evidence": evidence_component(m),
        "distance": distance_component(distance_km * road_detour_factor, decay_km),
        "capacity": capacity,
        "source": source_component(f, as_of, config),
        "location_quality": location_quality_component(f, config),
    }
    weight_sum = sum(config.weights.values()) or 1.0
    fit = sum(config.weights[k] * components[k] for k in config.weights) / weight_sum
    gate = config.gate[m.gate_key]

    penalty = 0.0
    p = config.penalties
    if "coord_pin_conflict" in f.flags:
        penalty += p["coord_pin_conflict"]
    if "implausible_scale" in f.flags:
        penalty += p["implausible_scale"]
    if "address_nothing_agrees" in f.flags:
        penalty += p["address_nothing_agrees"]
    if m.evidence is not None and m.evidence.negated_count > 0:
        penalty += p["negated_claim"]
    penalty = min(penalty, config.max_penalty)

    total = min(100.0, max(0.0, 100.0 * gate * fit - penalty))
    uncertainty = _uncertainty(f, m, as_of, config, capacity_ignored)
    return ScoreResult(
        facility=f, match=m, distance_km=distance_km, components=components, gate=gate,
        penalty=penalty, total=total, confidence=_confidence(f, m), uncertainty=uncertainty,
        weights=dict(config.weights), ranking_version=version,
    )


def _confidence(f: FacilityRecord, m: Match) -> str:
    if m.gate_key in ("specialty_only", "suggested") or f.location_confidence == "low":
        return "low"
    negated = m.evidence is not None and m.evidence.negated_count > 0
    if (m.gate_key == "strong" and _corroborating_fields(m) >= 2 and f.location_confidence == "high"
            and "coord_pin_conflict" not in f.flags and not negated):
        return "high"
    return "medium"


def _uncertainty(f: FacilityRecord, m: Match, as_of: date, config: RankingConfig,
                 capacity_ignored: bool) -> Uncertainty:
    codes: list[str] = []
    conflicts: list[str] = []
    if m.gate_key == "specialty_only":
        codes.append("SPECIALTY_ONLY_MATCH")
    elif m.gate_key == "suggested":
        codes.append("MODEL_SUGGESTED_MATCH")
    elif m.gate_key in ("mention", "mention_with_specialty"):
        codes.append("SERVICE_MENTION_ONLY")
    if m.evidence is not None and m.evidence.negated_count > 0:
        codes.append("NEGATED_SERVICE_CLAIM")
        conflicts.append("service_availability")
    if "coord_pin_conflict" in f.flags:
        codes.append("LOCATION_PIN_CONFLICT")
        conflicts.append("coordinates_vs_pincode")
    if f.location_confidence == "low":
        codes.append("LOW_PIN_CONFIDENCE")
    if "address_nothing_agrees" in f.flags:
        codes.append("ADDRESS_INCONSISTENT")
        conflicts.append("address_vs_pincode_vs_coordinates")
    if not f.official_website:
        codes.append("NO_OFFICIAL_SOURCE")
    age = _days_since_activity(f, as_of)
    if age is not None and age > config.stale_after_days:
        codes.append("STALE_SOURCE")
    if capacity_ignored:
        codes.append("CAPACITY_UNPARSEABLE")

    missing = [name for name, value in (
        ("n_beds", f.n_beds), ("n_doctors", f.n_doctors), ("official_website", f.official_website),
        ("location_confidence", f.location_confidence),
    ) if value is None]
    if age is None:
        missing.append("recent_activity")

    level = {"high": "low", "medium": "medium", "low": "high"}[_confidence(f, m)]
    return Uncertainty(level=level, reason_codes=codes, messages=[USER_MESSAGES[c] for c in codes],
                       missing_fields=missing, conflicts=conflicts)
