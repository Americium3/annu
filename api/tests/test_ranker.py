from __future__ import annotations

import math

import pytest

from app.ranking import DEFAULT_CONFIG, Ranker, RankQuery, UnknownServiceError
from app.ranking.config import urgency_for

from .conftest import AS_OF, ORIGIN, evidence, facility


def rank(facilities, ev, tags, tag="kidney-dialysis", **kw):
    index = {(e.unique_id, e.tag_id): e for e in ev}
    kw.setdefault("as_of", AS_OF)
    return Ranker(facilities, index, tags).rank(RankQuery(tag, *ORIGIN, **kw))


def ids(result):
    return [r.facility.unique_id for r in result.results]


# ── retrieval ────────────────────────────────────────────────────────────

def test_facility_without_evidence_or_specialty_is_never_returned(tags):
    res = rank([facility("has", 5), facility("none", 0.1)], [evidence("has")], tags)
    assert ids(res) == ["has"]


def test_specialty_fallback_makes_a_low_gated_candidate(tags):
    res = rank([facility("spec", 1, specialties=frozenset({"nephrology"}))], [], tags, tag="kidney-failure")
    (r,) = res.results
    assert r.score.match.gate_key == "specialty_only"
    assert r.score.confidence == "low"
    assert "SPECIALTY_ONLY_MATCH" in r.score.uncertainty.reason_codes


def test_service_without_fallback_ignores_specialties(tags):
    # Dialysis is a unit/equipment service: listing nephrology is not evidence of it.
    res = rank([facility("spec", 1, specialties=frozenset({"nephrology"}))], [], tags)
    assert res.results == []
    assert "NO_RESULTS" in res.warnings


def test_dentists_only_for_dental_services(tags):
    fs = [facility("dent", 1, facility_category="dentist"), facility("hosp", 2)]
    assert ids(rank(fs, [evidence("dent"), evidence("hosp")], tags)) == ["hosp"]
    ev = [evidence("dent", tag="root-canal"), evidence("hosp", tag="root-canal")]
    assert set(ids(rank(fs, ev, tags, tag="root-canal"))) == {"dent", "hosp"}


def test_unknown_service_raises(tags):
    with pytest.raises(UnknownServiceError):
        rank([], [], tags, tag="not-a-tag")


def test_missing_coordinates_and_unknown_facilities_are_skipped_and_counted(tags):
    no_coords = facility("nc", 1)
    no_coords = type(no_coords)(**{**no_coords.__dict__, "latitude": None, "longitude": None})
    res = rank([no_coords, facility("ok", 1)], [evidence("nc"), evidence("ok"), evidence("ghost")], tags)
    assert ids(res) == ["ok"]
    assert res.stats["skipped_no_coordinates"] == 1
    assert res.stats["skipped_unknown_facility"] == 1


# ── radius ───────────────────────────────────────────────────────────────

def test_radius_widens_until_enough_results(tags):
    near = [facility(f"n{i}", 5) for i in range(3)]
    mid = [facility(f"m{i}", 40) for i in range(8)]
    res = rank(near + mid, [evidence(f.unique_id) for f in near + mid], tags)
    assert res.radius_km == 50
    assert "RADIUS_WIDENED" in res.warnings
    assert res.total_candidates == 11


def test_radius_is_kept_when_widening_disabled(tags):
    fs = [facility("near", 5), facility("far", 40)]
    res = rank(fs, [evidence("near"), evidence("far")], tags, allow_widen=False)
    assert ids(res) == ["near"]
    assert res.radius_km == DEFAULT_CONFIG.default_radius_km
    assert "FEW_RESULTS" in res.warnings


# ── scoring properties ───────────────────────────────────────────────────

def test_strong_evidence_beats_specialty_only_even_when_further(tags):
    fs = [facility("strong", 20), facility("spec", 0.1, specialties=frozenset({"nephrology"}),
                                           n_beds=500, n_doctors=200)]
    res = rank(fs, [evidence("strong", tag="kidney-failure")], tags, tag="kidney-failure")
    assert ids(res) == ["strong", "spec"]


def test_gate_caps_the_total(tags):
    res = rank([facility("spec", 0, specialties=frozenset({"nephrology"}), n_beds=500, n_doctors=200,
                         n_specialties=40)], [], tags, tag="kidney-failure")
    assert res.results[0].score.total <= 100 * DEFAULT_CONFIG.gate["specialty_only"]


def test_closer_wins_when_evidence_is_equal(tags):
    res = rank([facility("far", 20), facility("near", 2)], [evidence("far"), evidence("near")], tags)
    assert ids(res) == ["near", "far"]


def test_missing_capacity_is_neutral_not_zero(tags):
    res = rank([facility("unknown")], [evidence("unknown")], tags)
    assert res.results[0].score.components["capacity"] == pytest.approx(DEFAULT_CONFIG.capacity_neutral)
    assert {"n_beds", "n_doctors"} <= set(res.results[0].score.uncertainty.missing_fields)


def test_implausible_capacity_is_ignored(tags):
    res = rank([facility("big", n_beds=90000, flags=frozenset({"impossible_beds"}))], [evidence("big")], tags)
    s = res.results[0].score
    assert s.components["capacity"] == pytest.approx(DEFAULT_CONFIG.capacity_neutral)
    assert "CAPACITY_UNPARSEABLE" in s.uncertainty.reason_codes


def test_data_quality_flags_penalise_and_explain(tags):
    fs = [facility("clean", 3), facility("conflict", 3, flags=frozenset({"coord_pin_conflict"}))]
    res = rank(fs, [evidence("clean"), evidence("conflict")], tags)
    by_id = {r.facility.unique_id: r.score for r in res.results}
    assert by_id["conflict"].penalty == DEFAULT_CONFIG.penalties["coord_pin_conflict"]
    assert by_id["clean"].total - by_id["conflict"].total == pytest.approx(5.0)
    assert "LOCATION_PIN_CONFLICT" in by_id["conflict"].uncertainty.reason_codes
    assert by_id["conflict"].confidence == "medium"


def test_negated_claim_penalised(tags):
    res = rank([facility("neg")], [evidence("neg", negated=2)], tags)
    s = res.results[0].score
    assert s.penalty == DEFAULT_CONFIG.penalties["negated_claim"]
    assert "NEGATED_SERVICE_CLAIM" in s.uncertainty.reason_codes


def test_mention_ranks_below_strong(tags):
    fs = [facility("strong", 5), facility("mention", 5)]
    res = rank(fs, [evidence("strong"), evidence("mention", cls="mention", prob=0.2)], tags)
    assert ids(res) == ["strong", "mention"]
    assert "SERVICE_MENTION_ONLY" in res.results[1].score.uncertainty.reason_codes


def test_unknown_evidence_class_from_a_future_pipeline_is_treated_as_mention(tags):
    res = rank([facility("x")], [evidence("x", cls="graded_v2", prob=None)], tags)
    assert res.results[0].score.match.gate_key == "mention"


def test_confidence_levels(tags):
    fs = [facility("high", 2), facility("one_field", 2), facility("lowloc", 2, location_confidence="low")]
    ev = [evidence("high"), evidence("one_field", fields=("procedure",)), evidence("lowloc")]
    by_id = {r.facility.unique_id: r.score for r in rank(fs, ev, tags).results}
    assert by_id["high"].confidence == "high" and by_id["high"].uncertainty.level == "low"
    assert by_id["one_field"].confidence == "medium"
    assert by_id["lowloc"].confidence == "low" and by_id["lowloc"].uncertainty.level == "high"


def test_stale_sources_flagged(tags):
    from datetime import date
    res = rank([facility("old", page_last_updated=date(2022, 1, 1))], [evidence("old")], tags)
    assert "STALE_SOURCE" in res.results[0].score.uncertainty.reason_codes


# ── clusters, modes, urgency ─────────────────────────────────────────────

def test_duplicate_cluster_collapses_to_best_record(tags):
    fs = [facility("a", 2, cluster_id="c1"), facility("b", 2, cluster_id="c1", official_website=None),
          facility("c", 4)]
    res = rank(fs, [evidence("a"), evidence("b"), evidence("c")], tags)
    assert ids(res) == ["a", "c"]
    assert res.stats["collapsed_duplicates"] == 1
    assert "DUPLICATE_FACILITY_CLUSTER" in res.results[0].score.uncertainty.reason_codes


def test_nearest_mode_sorts_by_distance_and_drops_weak_matches(tags):
    fs = [facility("far_strong", 10), facility("near_strong", 3),
          facility("nearest_suggested", 0.5)]
    ev = [evidence("far_strong"), evidence("near_strong"), evidence("nearest_suggested", cls="suggested")]
    assert ids(rank(fs, ev, tags, mode="nearest")) == ["near_strong", "far_strong"]


def test_most_evidence_mode(tags):
    fs = [facility("thin", 1), facility("rich", 15)]
    ev = [evidence("thin", prob=0.55, n=1, fields=("capability",)),
          evidence("rich", prob=0.99, n=12, fields=("procedure", "equipment", "capability"))]
    assert ids(rank(fs, ev, tags, mode="most_evidence")) == ["rich", "thin"]
    assert ids(rank(fs, ev, tags, mode="best_match"))[0] == "thin"


def test_emergency_services_decay_faster(tags):
    fs = [facility("x", 15)]
    dialysis = rank(fs, [evidence("x")], tags).results[0].score
    csec = rank(fs, [evidence("x", tag="c-section")], tags, tag="c-section").results[0].score
    assert csec.components["distance"] < dialysis.components["distance"]
    assert csec.components["distance"] == pytest.approx(math.exp(-15 * 1.3 / 10), rel=1e-3)


def test_new_tags_get_a_default_urgency():
    assert urgency_for("brand-new-tag", "Some new group") == "routine"
    assert urgency_for("brand-new-icu-thing", "Emergency & critical care") == "emergency"


def test_specialty_query(tags):
    fs = [facility("card", 2, specialties=frozenset({"cardiology"})), facility("other", 1)]
    res = rank(fs, [], tags, tag="specialty:cardiology")
    assert ids(res) == ["card"]
    assert res.results[0].score.match.gate_key == "specialty_query"


def test_breakdown_matches_api_contract(tags):
    b = rank([facility("x")], [evidence("x")], tags).results[0].score.breakdown()
    for key in ("service_match_score", "evidence_score", "source_score", "distance_score",
                "location_quality_score", "capacity_score", "penalty_score", "total_score", "model_version"):
        assert key in b
    assert sum(b["weights"].values()) == pytest.approx(1.0)
    assert 0 <= b["total_score"] <= 100


def test_results_are_deterministic(tags):
    fs = [facility(f"f{i}", 5) for i in range(5)]
    ev = [evidence(f.unique_id) for f in fs]
    assert ids(rank(fs, ev, tags)) == ids(rank(list(reversed(fs)), list(reversed(ev)), tags))
