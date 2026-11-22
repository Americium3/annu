"""Ranking tests: rank score = proof strength x closeness, with weak proof always after solid proof.

Run from backend/:  python test_ranking.py     (no Databricks access needed; uses synthetic data)
"""
from __future__ import annotations

import json

import pandas as pd

from data_store import Snapshot
from recommender import Recommender, closeness, proof_strength, rank_candidates, travel_km


def fac(name, tier, km, only_eq=False, other=0, loc="point_verified", n=3):
    return dict(unique_id=name, evidence_tier=tier, distance_km=km, only_equipment=only_eq, n_explicit_elsewhere=other,
                location_tier=loc, n_explicit_usable=n)


def order(rows, tag):
    return list(rank_candidates(pd.DataFrame(rows), tag)["unique_id"])


def test_factors():
    assert abs(closeness(15, 15) - 0.5) < 1e-9
    assert (travel_km("emergency-24x7"), travel_km("kidney-dialysis"), travel_km("mri"),
            travel_km("cardiac-surgery"), travel_km("unlisted")) == (10, 15, 30, 60, 25)
    p = proof_strength(pd.DataFrame([fac("x", 1, 1), fac("y", 1, 1, other=2, loc="pin_area")]))
    assert abs(p.iloc[1] - 0.85 * 0.75) < 1e-9


def test_trade_offs():
    near_far = [fac("strong-far", 1, 24), fac("good-near", 2, 1.5)]
    assert order(near_far, "kidney-dialysis") == ["good-near", "strong-far"]      # dialysis: near wins
    assert order(near_far, "cardiac-surgery") == ["strong-far", "good-near"]      # planned surgery: worth the trip
    assert order([fac("b", 1, 9), fac("a", 1, 3)], "mri") == ["a", "b"]           # equal proof: nearer first


def test_weak_proof_never_beats_solid():
    rows = [fac("equipment-next-door", 3, 0.5, only_eq=True), fac("solid-24km", 1, 24), fac("weak-pin", 3, 1, loc="pin_area")]
    # default gate ("evidence"): any explicit, non-equipment claim is solid; equipment-only next door is still last,
    # and a one-statement claim 1 km away competes on proof x closeness with a strong claim 24 km away
    assert order(rows, "kidney-dialysis") == ["weak-pin", "solid-24km", "equipment-next-door"]


def test_legacy_proof_gate():
    import config
    old, config.SOLID_GATE = config.SOLID_GATE, "proof"
    try:
        rows = [fac("equipment-next-door", 3, 0.5, only_eq=True), fac("solid-24km", 1, 24), fac("weak-pin", 3, 1, loc="pin_area")]
        assert order(rows, "kidney-dialysis") == ["solid-24km", "weak-pin", "equipment-next-door"]
    finally:
        config.SOLID_GATE = old


def test_end_to_end():
    lat0, lon0 = 20.2961, 85.8245
    tags = pd.DataFrame([{"tag_id": "kidney-dialysis", "label": "Dialysis", "kind": "service",
                          "group_name": "Kidney & urinary", "synonyms": ["haemodialysis"], "facility_count": 4}])
    facs, idx = [], []
    for uid, name, km, tier, only_eq, elig, phone in [
        ("f1", "Strong Far Hospital", 24, 1, False, "formal", "0674-2300570"),
        ("f2", "Good Near Hospital", 1.5, 2, False, "formal", None),
        ("f3", "Equipment Only Clinic", 0.5, 3, True, "formal", None),
        ("f4", "Blocked Hospital", 2, 1, False, "review_blocked", None),
    ]:
        la, lo = lat0 + km / 111.0, lon0
        facs.append(dict(unique_id=uid, name=name, facility_category="hospital", operator_category="private",
                         city_raw="Bhubaneswar", district="Khordha", state="Odisha", pincode="751001",
                         address_city="Bhubaneswar", location_tier="point_verified", loc_lat=la, loc_lon=lo, latitude=la,
                         longitude=lo, location_source="geo", location_confidence="high", location_check="ok",
                         coord_to_pin_km=1.0, core_identity_conflict=False, contact_phone=phone,
                         contact_website="www.example.org" if uid == "f2" else None, source_urls=["https://example.org/a"],
                         recency_of_page_update=None, capability_maybe_truncated=False, procedure_maybe_truncated=False,
                         same_name_city_records=1, n_beds=float("nan"), n_doctors=float("nan"), year_est=float("nan"),
                         n_source_urls=1, flag_shared_point=False))
        idx.append(dict(unique_id=uid, tag_id="kidney-dialysis", eligibility=elig, reason_codes=[], evidence_tier=tier,
                        n_explicit_usable=2, n_explicit_elsewhere=0, n_time_bound=0, n_equipment_usable=1,
                        n_explicit_fields=1, n_cited=1, only_equipment=only_eq, lists_emergency_24x7=False,
                        evidence=[{"field": "procedure", "pos": 0, "text": "Haemodialysis available.",
                                   "evidence_status": "usable"}]))
    pins = pd.DataFrame([{"pincode": "751001", "states": ["ODISHA"], "districts": ["KHORDHA"], "lat": lat0,
                          "lon": lon0, "is_precise": True}])
    rec = Recommender(Snapshot(tags, pd.DataFrame(idx), pd.DataFrame(facs), pins, "now", "synthetic"), ranking_method="rules")
    out = rec.recommend("dialysis", "", {"latitude": lat0, "longitude": lon0})
    names = [f["name"] for f in out["results"]]
    assert names == ["Good Near Hospital", "Strong Far Hospital", "Equipment Only Clinic"], names
    for f in out["results"]:
        assert abs(f["totalScore"] - 100 * f["rankFactors"]["score"]) <= 1          # number shown == rank score
    assert out["results"][1]["phone"] == "06742300570" and out["results"][0]["website"] == "https://www.example.org"
    assert out["results"][2]["rankFactors"]["solidProof"] is False
    json.dumps(out)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok  ", name)
    print("all ranking tests passed")
