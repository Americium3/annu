"""End-to-end evaluation against workspace.golden_eval (DEV split only).

Every system is called exactly like the app: the user gives a service and a location as text
(the golden query's `service_label` and `location_text`). Nothing else from the query
(coordinates, radius, expected answers) is passed to the system.

Metrics (per query, then averaged):
  P@3        share of the top 3 with gain >= 2 (recommend / recommend_with_caveat); short lists still divide by 3
  nDCG@3     graded gain 0-3; ideal = best 3 judged gains for the query; unjudged results count as gain 0
  P@3_j      same, but unjudged results are skipped (condensed list: removes the pooling penalty)
  nDCG@3_j   condensed nDCG@3
  bad@3      results in the top 3 judged do_not_recommend (gain 0)
  answered   the system returned at least one result, over queries that have a recommendable facility
  abstain_ok the system returned nothing for queries with no recommendable facility ("desert")
  errors     the system could not resolve the service or the location
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"


@dataclass
class Golden:
    queries: pd.DataFrame
    judgments: pd.DataFrame

    @property
    def gains(self) -> dict:
        return {(r.query_id, r.unique_id): int(r.gain) for r in self.judgments.itertuples()}


def load_golden() -> Golden:
    q = pd.read_parquet(DATA / "queries_dev.parquet")
    assert set(q["split"]) == {"dev"}, "only the dev split may be used here"
    j = pd.read_parquet(DATA / "judgments_dev.parquet")
    j["gain"] = j["gain"].astype(int)
    q["n_recommend"] = q["n_recommend"].astype(int)
    return Golden(q, j)


def _dcg(gains):
    return sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(gains))


def score_run(golden: Golden, ranked: dict[str, list[str]], errors: dict[str, str] | None = None) -> pd.DataFrame:
    """ranked: query_id -> ordered unique_ids returned by the system. Returns one row per query."""
    errors = errors or {}
    G = golden.gains
    rows = []
    for q in golden.queries.itertuples():
        top = ranked.get(q.query_id, [])
        judged = [g for (qq, _), g in G.items() if qq == q.query_id]
        ideal = sorted(judged, reverse=True)[:3]
        raw = [G.get((q.query_id, u), 0) for u in top[:3]]
        cond = [G[(q.query_id, u)] for u in top if (q.query_id, u) in G][:3]
        answerable = q.n_recommend > 0
        rows.append({
            "query_id": q.query_id, "service": q.service, "slice": q.slice, "answerable": answerable,
            "P@3": sum(g >= 2 for g in raw) / 3 if answerable else np.nan,
            "nDCG@3": (_dcg(raw) / _dcg(ideal)) if answerable and _dcg(ideal) else np.nan,
            "P@3_j": sum(g >= 2 for g in cond) / 3 if answerable else np.nan,
            "nDCG@3_j": (_dcg(cond) / _dcg(ideal)) if answerable and _dcg(ideal) else np.nan,
            "bad@3": sum(1 for u in top[:3] if G.get((q.query_id, u)) == 0),
            "answered": (len(top) > 0) if answerable else np.nan,
            "abstain_ok": (len(top) == 0) if not answerable else np.nan,
            "error": errors.get(q.query_id, ""),
            "returned": len(top),
        })
    return pd.DataFrame(rows)


def summarize(per_query: pd.DataFrame) -> dict:
    a = per_query[per_query.answerable]
    return {
        "P@3": a["P@3"].mean(), "nDCG@3": a["nDCG@3"].mean(), "P@3_j": a["P@3_j"].mean(), "nDCG@3_j": a["nDCG@3_j"].mean(),
        "bad@3": int(per_query["bad@3"].sum()), "answered": a["answered"].mean(),
        "abstain_ok": per_query.loc[~per_query.answerable, "abstain_ok"].mean(),
        "errors": int((per_query["error"] != "").sum()), "queries": len(per_query),
    }


def paired_bootstrap(a: pd.DataFrame, b: pd.DataFrame, metric="nDCG@3", n=4000, seed=0):
    """Mean difference b - a over answerable queries with a 95% bootstrap interval."""
    x = a.set_index("query_id")[metric]; y = b.set_index("query_id")[metric]
    d = (y - x).dropna().to_numpy()
    rng = np.random.default_rng(seed)
    boots = rng.choice(d, (n, len(d))).mean(axis=1)
    return float(d.mean()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
