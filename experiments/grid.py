"""Stage-2 grid on the golden DEV queries + leave-one-query-out cross-validation.

  python -m experiments.grid [kind ...]        # kinds: none bm25 bi ce_msmarco ce_bge ce_bge_l nli

For every text model, all combinations of w_text, travel_mult, urgency factor and query style are run on the SAME
candidate pool (E5b: v2 candidates, min pool 3, multi-service intent). Per-query metrics go to
results/grid_per_query.csv. `cv_report()` then picks, for each held-out query, the best combination on the other
queries (by mean nDCG@3) and scores it on the held-out query: an honest estimate that is not tuned on itself.
"""
from __future__ import annotations

import itertools
import os
import sys
import time

import numpy as np
import pandas as pd

from experiments.golden_eval import load_golden, score_run
from experiments.run_golden import RESULTS, cfg, run_backend_like, snapshot_v2

GRID = {"w_text": [0.25, 0.4, 4 / 7, 0.8], "travel_mult": [0.5, 1.0, 2.0, 4.0], "urgent": [1.0, 0.6],
        "style": ["keywords", "natural"]}


def run(kinds):
    import recommender as R
    from experiments.rankers import make_ranker
    golden = load_golden()
    path = RESULTS / "grid_per_query.csv"
    done = pd.read_csv(path) if path.exists() else pd.DataFrame()
    base = os.environ.get("GRID_BASE", "E5b")   # E5b: v2 + pool 3 + intent; E6: + plausibility; E8: + evidence-based solid gate
    snap = snapshot_v2(use_plausibility=(base in ("E6", "E8")))
    gate = "evidence" if base == "E8" else "proof"
    original = R.rank_candidates
    for kind in kinds:
        combos = [dict(w_text=0.0, travel_mult=m, urgent=u, style="-") for m in GRID["travel_mult"] for u in GRID["urgent"]] \
            if kind == "none" else \
            [dict(w_text=w, travel_mult=m, urgent=u, style=s) for w, m, u, s in itertools.product(*GRID.values())
             if not (kind in ("bm25", "bi") and s == "natural" and False)]
        if os.environ.get("GRID_SMALL"):    # slow models (LLM verifiers, large reranker): the region that won for the others
            combos = [c for c in combos if c["w_text"] in (0.25, 0.4) and c["travel_mult"] in (1.0, 2.0)
                      and c["urgent"] == 1.0 and c["style"] in ("natural", "-")]
        t0 = time.time()
        rows = []
        for c in combos:
            with cfg(MIN_POOL_SIZE=3, MULTI_INTENT=True, EMERGENCY_MISSING_FACTOR=c["urgent"], SOLID_GATE=gate):
                rec = R.Recommender(snap, ranking_method="rules")
                R.rank_candidates = make_ranker(rec, kind, c["w_text"], c["travel_mult"], c["style"] if c["style"] != "-" else "natural")
                try:
                    ranked, errors = run_backend_like(rec, golden)
                finally:
                    R.rank_candidates = original
            pq = score_run(golden, ranked, errors)
            cid = f"{kind}|w={c['w_text']:.2f}|m={c['travel_mult']}|u={c['urgent']}|q={c['style']}"
            rows.append(pq.assign(kind=kind, base=base, config=f"{base}|{cid}", **c))
        new = pd.concat(rows)
        keep = ~((done.kind == kind) & (done.get("base", "E5b") == base)) if len(done) else None
        done = pd.concat([done[keep] if len(done) else done, new])
        done.to_csv(path, index=False)
        a = new[new.answerable].groupby("config")["nDCG@3"].mean()
        print(f"{kind:11} {len(combos):3} configs in {time.time()-t0:5.0f}s | best in-sample nDCG@3 {a.max():.3f} ({a.idxmax()})", flush=True)


def cv_report(metric="nDCG@3"):
    g = pd.read_csv(RESULTS / "grid_per_query.csv")
    g = g[g.answerable]
    out = []
    g["base"] = g["base"].fillna("E5b") if "base" in g else "E5b"
    for (base, kind), gk in g.groupby(["base", "kind"]):
        piv = gk.pivot_table(index="query_id", columns="config", values=metric)
        p3 = gk.pivot_table(index="query_id", columns="config", values="P@3")
        p3j = gk.pivot_table(index="query_id", columns="config", values="P@3_j")
        cv, cvp, cvpj, picks = [], [], [], []
        for q in piv.index:
            best = piv.drop(index=q).mean().idxmax()
            cv.append(piv.at[q, best]); cvp.append(p3.at[q, best]); cvpj.append(p3j.at[q, best]); picks.append(best)
        full_best = piv.mean().idxmax()
        out.append({"base": base, "text_model": kind, "LOO-CV nDCG@3": np.mean(cv), "LOO-CV P@3": np.mean(cvp), "LOO-CV P@3_j": np.mean(cvpj),
                    "in-sample best nDCG@3": piv.mean().max(), "best config (all queries)": full_best,
                    "most picked in CV": pd.Series(picks).mode()[0], "configs": piv.shape[1]})
    rep = pd.DataFrame(out).sort_values("LOO-CV nDCG@3", ascending=False)
    rep.to_csv(RESULTS / "grid_cv_summary.csv", index=False)
    return rep


if __name__ == "__main__":
    kinds = sys.argv[1:] or ["none", "bm25", "bi", "ce_msmarco", "ce_bge", "nli"]
    run(kinds)
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60)
    print(cv_report().round(3).to_string(index=False))
