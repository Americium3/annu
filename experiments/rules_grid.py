"""Rules-only parameter grid on the E6 base (no text model) + leave-one-query-out CV.

Parameters: MIN_POOL_SIZE, travel-distance multiplier, weight of single-statement proof (tier 3), urgency factor.
  python -m experiments.rules_grid
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from experiments.golden_eval import load_golden, score_run
from experiments.run_golden import RESULTS, cfg, run_backend_like, snapshot_v2

GRID = {"min_pool": [2, 3, 5, 8], "travel_mult": [0.5, 1.0, 2.0, 4.0], "tier3": [0.4, 0.55, 0.7], "urgent": [1.0, 0.6]}


def main():
    import recommender as R
    from experiments.rankers import make_ranker
    golden = load_golden(); snap = snapshot_v2(use_plausibility=True)
    original = R.rank_candidates; rows = []
    for mp, tm, t3, u in itertools.product(*GRID.values()):
        with cfg(MIN_POOL_SIZE=mp, MULTI_INTENT=True, EMERGENCY_MISSING_FACTOR=u, PROOF_BY_TIER={1: 1.0, 2: 0.8, 3: t3}):
            rec = R.Recommender(snap, ranking_method="rules")
            R.rank_candidates = make_ranker(rec, "none", 0.0, tm)
            try:
                ranked, errors = run_backend_like(rec, golden)
            finally:
                R.rank_candidates = original
        rows.append(score_run(golden, ranked, errors).assign(config=f"pool={mp}|m={tm}|t3={t3}|u={u}", min_pool=mp, travel_mult=tm, tier3=t3, urgent=u))
    g = pd.concat(rows); g.to_csv(RESULTS / "rules_grid_per_query.csv", index=False)
    a = g[g.answerable]
    piv = a.pivot_table(index="query_id", columns="config", values="nDCG@3"); p3 = a.pivot_table(index="query_id", columns="config", values="P@3")
    cv = [(piv.at[q, piv.drop(index=q).mean().idxmax()], p3.at[q, piv.drop(index=q).mean().idxmax()]) for q in piv.index]
    print(f"configs {piv.shape[1]} | in-sample best nDCG@3 {piv.mean().max():.3f} ({piv.mean().idxmax()}) | LOO-CV nDCG@3 {np.mean([c[0] for c in cv]):.3f} P@3 {np.mean([c[1] for c in cv]):.3f}")
    for k in GRID:
        print(f"  mean nDCG@3 by {k}:", a.groupby(k)["nDCG@3"].mean().round(3).to_dict())


if __name__ == "__main__":
    main()
