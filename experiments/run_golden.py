"""Run every recommender variant on the golden_eval DEV queries and record the results.

  python -m experiments.run_golden                 # all experiments
  python -m experiments.run_golden E0_live_ce E3   # selected experiments (prefix match)

Writes experiments/results/golden_dev_summary.csv, golden_dev_per_query.csv and RESULTS.md.
Each experiment is a function that returns {query_id: [unique_id, ...]} plus errors, given the user's
service text and location text only.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO / "backend"))
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

from experiments.golden_eval import load_golden, score_run, summarize  # noqa: E402

RESULTS = ROOT / "results"
EXPERIMENTS: dict[str, tuple[str, callable]] = {}


def experiment(name: str, description: str):
    def wrap(fn):
        EXPERIMENTS[name] = (description, fn)
        return fn
    return wrap


def run_backend_like(rec, golden, service_fn=lambda q: q.service_label, location_fn=lambda q: q.location_text):
    """Call a backend-compatible recommender exactly like the app (service text + location text)."""
    from recommender import LocationNotFound, ServiceNotFound
    ranked, errors = {}, {}
    for q in golden.queries.itertuples():
        try:
            out = rec.recommend(service_fn(q), location_fn(q), None)
            ranked[q.query_id] = [r["id"] for r in out["results"]]
        except (ServiceNotFound, LocationNotFound) as e:
            ranked[q.query_id] = []
            errors[q.query_id] = f"{type(e).__name__}: {e}"
    return ranked, errors


import contextlib


@contextlib.contextmanager
def cfg(**overrides):
    """Temporarily override backend/config.py values for one experiment (restored afterwards)."""
    import config
    old = {k: getattr(config, k) for k in overrides}
    for k, v in overrides.items():
        setattr(config, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(config, k, v)


def legacy_service_cfg():
    """Search behaviour before E5: stop widening at the first provider, one service per query, no urgency."""
    import config
    syn = {k: v for k, v in config.SERVICE_INPUT_SYNONYMS.items() if k != "emergency-24x7"}
    return cfg(MIN_POOL_SIZE=1, MULTI_INTENT=False, EMERGENCY_MISSING_FACTOR=1.0, SERVICE_INPUT_SYNONYMS=syn, SOLID_GATE="proof",
               CROSS_ENCODER_QUERY_STYLE="keywords", RERANK_WEIGHTS={"text": 4 / 7, "proof": 3 / 7})


def _snapshot():
    """The cached live snapshot. E0/E1 need the v1 serving index in it (the baseline); E3+ swap in v2 themselves."""
    import data_store
    snap = data_store.get_snapshot()
    if "grade" in snap.index.columns:
        raise RuntimeError("backend/.cache/snapshot.pkl holds a v2 index; rebuild it with CAREPATH_SERVICE_INDEX=v1 "
                           "CAREPATH_REFRESH=1 so the baselines use the v1 serving index")
    return snap


# ---------------------------------------------------------------- E0: the live backend as merged on main
BASELINE_REF = os.environ.get("CAREPATH_BASELINE_REF", "4401fe1")   # main before this experiment branch


def run_baseline_backend(golden, ranking_method):
    """Run the UNMODIFIED backend from BASELINE_REF in a subprocess (git archive), with the current snapshot cache."""
    import json, shutil, subprocess, tempfile
    tmp = Path(tempfile.mkdtemp(prefix="baseline_backend_"))
    subprocess.run(f"git -C {REPO} archive {BASELINE_REF} backend | tar -x -C {tmp}", shell=True, check=True)
    shutil.copytree(REPO / "backend" / ".cache", tmp / "backend" / ".cache", dirs_exist_ok=True)
    qs = [{"query_id": q.query_id, "service": q.service_label, "location": q.location_text} for q in golden.queries.itertuples()]
    code = f"""
import json, sys
sys.path.insert(0, {str(tmp / 'backend')!r})
import data_store
from recommender import Recommender, LocationNotFound, ServiceNotFound
rec = Recommender(data_store.get_snapshot(), ranking_method={ranking_method!r})
out = {{}}
for q in json.loads(sys.stdin.read()):
    try:
        out[q['query_id']] = {{'ids': [r['id'] for r in rec.recommend(q['service'], q['location'], None)['results']], 'error': ''}}
    except (LocationNotFound, ServiceNotFound) as e:
        out[q['query_id']] = {{'ids': [], 'error': type(e).__name__ + ': ' + str(e)}}
print('@@' + json.dumps(out))
"""
    res = subprocess.run([sys.executable, "-c", code], input=json.dumps(qs), capture_output=True, text=True, cwd=tmp / "backend")
    line = [l for l in res.stdout.splitlines() if l.startswith("@@")]
    if not line:
        raise RuntimeError(res.stderr[-2000:])
    out = json.loads(line[0][2:])
    shutil.rmtree(tmp, ignore_errors=True)
    return {k: v["ids"] for k, v in out.items()}, {k: v["error"] for k, v in out.items() if v["error"]}


@experiment("E0_live_rules", f"Baseline: backend at {BASELINE_REF} (main), rules ranking (proof x closeness)")
def e0_rules(golden):
    return run_baseline_backend(golden, "rules")


@experiment("E0_live_ce", f"Baseline: backend at {BASELINE_REF} (main), default cross-encoder (4/7 text + 3/7 proof) x closeness")
def e0_ce(golden):
    return run_baseline_backend(golden, "cross_encoder")


# ---------------------------------------------------------------- E1: location resolver fixes (generic)
@experiment("E1_location_rules", "E0 rules + location resolver: PIN anywhere in text, ref_address_alias spellings, facility named as location")
def e1_rules(golden):
    with legacy_service_cfg():
        from recommender import Recommender
        return run_backend_like(Recommender(_snapshot(), ranking_method="rules"), golden)


@experiment("E1_location_ce", "E0 cross-encoder + the same location resolver fixes")
def e1_ce(golden):
    with legacy_service_cfg():
        from recommender import Recommender
        return run_backend_like(Recommender(_snapshot(), ranking_method="cross_encoder"), golden)


# ---------------------------------------------------------------- E3+: v2 stage-1 candidates (pipeline/service_index_v2.py)
def snapshot_v2(location_policy="review", related_as_formal=False, use_plausibility=False, index_file="service_index_v2.parquet"):
    """Live snapshot with the serving index replaced by the v2 candidates.
    location_policy: 'review' = block coordinate/PIN conflicts (as v1);
                     'osm'    = use workspace.cardinal_virtues.location_trust for conflicts (address/name supported -> keep,
                                with the OSM-chosen point; untrusted -> block)."""
    import copy
    snap = copy.copy(_snapshot())
    v2 = pd.read_parquet(ROOT / "data" / index_file)
    fac = snap.facilities.copy()
    if location_policy == "osm":
        lt = pd.read_parquet(ROOT / "data" / "facilities.parquet")[["unique_id", "location_trust_tier", "use_lat", "use_lon"]]
        fac = fac.merge(lt, on="unique_id", how="left")
        ok = (fac.location_tier == "conflict") & fac.location_trust_tier.isin(["address_supported", "trusted_name_match"])
        fac.loc[ok, "loc_lat"] = pd.to_numeric(fac.loc[ok, "use_lat"]); fac.loc[ok, "loc_lon"] = pd.to_numeric(fac.loc[ok, "use_lon"])
        fac.loc[ok, "location_tier"] = "point_unverified"
        fac = fac.drop(columns=["location_trust_tier", "use_lat", "use_lon"])
    snap.facilities = fac
    import data_store
    v2 = data_store.adapt_index_v2(v2, fac, use_plausibility)
    if related_as_formal:
        raise NotImplementedError
    snap.index = v2
    return snap


@experiment("E3_v2index_rules", "E1 + v2 stage-1 candidates (higher recall, sense/negation/attribution fixes); rules ranking")
def e3_rules(golden):
    with legacy_service_cfg():
        from recommender import Recommender
        return run_backend_like(Recommender(snapshot_v2(), ranking_method="rules"), golden)


@experiment("E3_v2index_ce", "E1 + v2 stage-1 candidates; live cross-encoder ranking")
def e3_ce(golden):
    with legacy_service_cfg():
        from recommender import Recommender
        return run_backend_like(Recommender(snapshot_v2(), ranking_method="cross_encoder"), golden)


@experiment("E4_v2_osm_rules", "E3 + OSM location trust for coordinate/PIN conflicts; rules ranking")
def e4_rules(golden):
    with legacy_service_cfg():
        from recommender import Recommender
        return run_backend_like(Recommender(snapshot_v2("osm"), ranking_method="rules"), golden)


# ---------------------------------------------------------------- E5: search policy and service intent
@experiment("E5a_minpool3_rules", "E3 + widen the search until >= 3 recommendable facilities (not until the first one)")
def e5a(golden):
    from recommender import Recommender
    with legacy_service_cfg(), cfg(MIN_POOL_SIZE=3):
        return run_backend_like(Recommender(snapshot_v2(), ranking_method="rules"), golden)


@experiment("E5b_intent_rules", "E5a + service text naming several services is searched as all of them ('Trauma / emergency care')")
def e5b(golden):
    from recommender import Recommender
    with cfg(MIN_POOL_SIZE=3, MULTI_INTENT=True, EMERGENCY_MISSING_FACTOR=1.0, SOLID_GATE="proof"):
        return run_backend_like(Recommender(snapshot_v2(), ranking_method="rules"), golden)


@experiment("E5c_urgent_rules", "E5b + urgent wording ranks facilities with emergency / 24x7 evidence first (x0.6 otherwise)")
def e5c(golden):
    from recommender import Recommender
    with cfg(MIN_POOL_SIZE=3, MULTI_INTENT=True, EMERGENCY_MISSING_FACTOR=0.6, SOLID_GATE="proof"):
        return run_backend_like(Recommender(snapshot_v2(), ranking_method="rules"), golden)


# ---------------------------------------------------------------- E6: evidence quality factors
@experiment("E6_plausibility_rules", "E5b + down-weight explicit claims only in specialty/name/description (x0.75), name of another "
            "specialty (x0.6, merged records) and inpatient-only services at clinics (x0.7)")
def e6(golden):
    from recommender import Recommender
    with cfg(MIN_POOL_SIZE=3, MULTI_INTENT=True, EMERGENCY_MISSING_FACTOR=1.0, SOLID_GATE="proof"):
        return run_backend_like(Recommender(snapshot_v2(use_plausibility=True), ranking_method="rules"), golden)


# ---------------------------------------------------------------- E7: the final configuration, through the LIVE code path
FINAL = dict(MIN_POOL_SIZE=3, MULTI_INTENT=True, EMERGENCY_MISSING_FACTOR=1.0, CROSS_ENCODER_QUERY_STYLE="natural",
             RERANK_WEIGHTS={"text": 0.25, "proof": 0.75})
E7 = dict(FINAL, SOLID_GATE="proof")


@experiment("E7_final_ce", "E6 + cross-encoder ms-marco MiniLM, query 'a hospital that provides X', evidence = 0.25 text + "
            "0.75 proof (chosen by LOO-CV in grid.py), run through backend/recommender.py itself")
def e7_ce(golden):
    from recommender import Recommender
    with cfg(**E7):
        return run_backend_like(Recommender(snapshot_v2(use_plausibility=True), ranking_method="cross_encoder"), golden)


@experiment("E7_final_rules", "E7 without a text model (rules only), through backend/recommender.py")
def e7_rules(golden):
    from recommender import Recommender
    with cfg(**E7):
        return run_backend_like(Recommender(snapshot_v2(use_plausibility=True), ranking_method="rules"), golden)


@experiment("E8a_solid_evidence_rules", "E7 rules with solid proof = explicit, non-equipment, not down-weighted evidence (location and "
            "single-statement no longer push a claim behind every 'solid' one)")
def e8a(golden):
    from recommender import Recommender
    with cfg(**FINAL, SOLID_GATE="evidence"):
        return run_backend_like(Recommender(snapshot_v2(use_plausibility=True), ranking_method="rules"), golden)


@experiment("E8b_solid_off_rules", "E7 rules without a separate solid-proof tier")
def e8b(golden):
    from recommender import Recommender
    with cfg(**FINAL, SOLID_GATE="off"):
        return run_backend_like(Recommender(snapshot_v2(use_plausibility=True), ranking_method="rules"), golden)


@experiment("E8c_solid_evidence_ce", "E8a with the E7 cross-encoder")
def e8c(golden):
    from recommender import Recommender
    with cfg(**FINAL, SOLID_GATE="evidence"):
        return run_backend_like(Recommender(snapshot_v2(use_plausibility=True), ranking_method="cross_encoder"), golden)


# ---------------------------------------------------------------- E9: the shipped defaults, no overrides at all
@experiment("E9_shipped_defaults", "backend/config.py defaults as committed (v2 index with plausibility, pool 3, multi-service "
            "intent, evidence-based solid gate, rules ranking): must equal the best experiment")
def e9(golden):
    from recommender import Recommender
    return run_backend_like(Recommender(snapshot_v2(use_plausibility=True)), golden)


# ---------------------------------------------------------------- E10: robustness, not tuned on
@experiment("E10_freetext_service", "Robustness: the shipped system with the golden query's full natural-language sentence "
            "(English / Hinglish, e.g. '... ke paas emergency trauma care ... kahan milega') as the service text")
def e10(golden):
    from recommender import Recommender
    return run_backend_like(Recommender(snapshot_v2(use_plausibility=True)), golden, service_fn=lambda q: q.query_text)


@experiment("E10_freetext_baseline", "Robustness: the baseline backend (main) with the same natural-language service text")
def e10_base(golden):
    import json, shutil, subprocess, tempfile
    g = type(golden)(golden.queries.assign(service_label=golden.queries.query_text), golden.judgments)
    return run_baseline_backend(g, "rules")


@experiment("E11_calibrated_ce", "E9 with main's calibrated cross-encoder (PR #16: logit mapped to 0-1 over [-11, -5], "
            "evidence = 0.3 text + 0.7 proof), backend defaults otherwise")
def e11(golden):
    from recommender import Recommender
    return run_backend_like(Recommender(snapshot_v2(use_plausibility=True), ranking_method="cross_encoder"), golden)


def main(selected: list[str]):
    golden = load_golden()
    RESULTS.mkdir(exist_ok=True)
    names = [n for n in EXPERIMENTS if not selected or any(n.startswith(s) for s in selected)]
    summ_path, pq_path = RESULTS / "golden_dev_summary.csv", RESULTS / "golden_dev_per_query.csv"
    summ = pd.read_csv(summ_path) if summ_path.exists() else pd.DataFrame()
    perq = pd.read_csv(pq_path) if pq_path.exists() else pd.DataFrame()
    for name in names:
        desc, fn = EXPERIMENTS[name]
        t0 = time.time()
        ranked, errors = fn(golden)
        pq = score_run(golden, ranked, errors).assign(experiment=name)
        s = {"experiment": name, "description": desc, **summarize(pq), "seconds": round(time.time() - t0, 1)}
        print(f"{name:34} P@3 {s['P@3']:.3f}  nDCG@3 {s['nDCG@3']:.3f}  P@3_j {s['P@3_j']:.3f}  nDCG@3_j {s['nDCG@3_j']:.3f}  "
              f"bad@3 {s['bad@3']}  answered {s['answered']:.2f}  errors {s['errors']}  ({s['seconds']}s)", flush=True)
        summ = pd.concat([summ[summ.get("experiment", pd.Series(dtype=str)) != name] if len(summ) else summ, pd.DataFrame([s])])
        perq = pd.concat([perq[perq.get("experiment", pd.Series(dtype=str)) != name] if len(perq) else perq, pq])
        summ.to_csv(summ_path, index=False); perq.to_csv(pq_path, index=False)


if __name__ == "__main__":
    main(sys.argv[1:])
