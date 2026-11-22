"""Independent qrels; no regex labels presented as ground truth.

Qrels: query_id, unique_id, relevance (0..3 or blank=unjudged).
relevance >= 2 means eligible based on human-reviewed service, identity and location.
Recall and nDCG are relative to the judged pool, not exhaustive corpus truth.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def evaluate(runs, qrels, k=3):
    required = {"query_id", "unique_id", "relevance"}
    if not required.issubset(qrels.columns):
        raise ValueError(f"Qrels need {required}")
    labels = qrels.copy()
    labels["relevance"] = pd.to_numeric(labels.relevance, errors="coerce")
    labels = labels.dropna(subset=["relevance"])
    if not labels.relevance.isin([0, 1, 2, 3]).all():
        raise ValueError("Relevance must be integer 0..3 or blank")
    if labels.duplicated(["query_id", "unique_id"]).any():
        raise ValueError("Resolve duplicate qrels before evaluation")
    labels["query_id"], labels["unique_id"] = labels.query_id.astype(str), labels.unique_id.astype(str)
    records = []
    for run in runs:
        qid = str(run["query_id"])
        judged = labels[labels.query_id.eq(qid)]
        lookup = dict(zip(judged.unique_id, judged.relevance))
        relevant = {uid for uid, grade in lookup.items() if grade >= 2}
        returned = [r["unique_id"] for r in run["results"][:k]]
        # Unknown outputs are NOT silently counted as wrong.
        fully_judged = all(uid in lookup for uid in returned) and len(judged) > 0
        grades = [lookup.get(uid, 0) for uid in returned]
        ideal = sorted(lookup.values(), reverse=True)[:k]
        dcg = sum((2**g-1)/math.log2(i+2) for i, g in enumerate(grades))
        idcg = sum((2**g-1)/math.log2(i+2) for i, g in enumerate(ideal))
        answered = bool(returned)
        distances = [r["distance_km"] for r in run["results"][:k] if r.get("distance_km") is not None]
        records.append({"query_id": qid, "method": run["method"], "service_id": run["service_id"],
            "density_group": run.get("density_group", "unspecified"), "answered": int(answered),
            "no_answer": int(not answered),
            "top1_distance_km": run["results"][0].get("distance_km") if answered else np.nan,
            "mean_distance_km": float(np.mean(distances)) if distances else np.nan,
            "returned_count": len(returned), "candidate_count": len(run["candidate_ids"]),
            "judged_query": int(len(judged) > 0), "known_positives": len(relevant),
            "judged_result_fraction": sum(uid in lookup for uid in returned)/len(returned) if returned else np.nan,
            "precision_at_k": sum(g >= 2 for g in grades)/k if fully_judged else np.nan,
            "precision_returned": sum(g >= 2 for g in grades)/len(returned) if fully_judged and returned else np.nan,
            "ndcg_at_k_pool": dcg/idcg if fully_judged and idcg else np.nan,
            "candidate_recall_pool": len(relevant & set(run["candidate_ids"]))/len(relevant) if relevant else np.nan,
            "hit_at_k": int(bool(relevant & set(returned))) if relevant and fully_judged else np.nan,
            "false_abstention": int(not answered) if relevant else np.nan,
            "latency_ms": run["latency_ms"]})
    per_query = pd.DataFrame(records)
    if per_query.empty:
        return per_query, pd.DataFrame()
    means = ["answered", "precision_at_k", "precision_returned", "ndcg_at_k_pool", "candidate_recall_pool",
             "hit_at_k", "false_abstention", "judged_result_fraction"]
    summary = per_query.groupby("method")[means].mean()
    summary["query_count"] = per_query.groupby("method").size()
    for metric in means:
        summary[metric + "_n"] = per_query.groupby("method")[metric].count()
    summary["latency_p50_ms"] = per_query.groupby("method").latency_ms.quantile(.5)
    summary["latency_p95_ms"] = per_query.groupby("method").latency_ms.quantile(.95)
    return per_query, summary.reset_index()


def annotation_pool(runs):
    """Union of ALL generated candidates, including rejected ones, with blinded labels.

    Also manually add suspected misses from outside this pool before claiming recall.
    Scores, methods and suggested status are intentionally hidden from annotators.
    """
    rows = {}
    for run in runs:
        for r in run["audit"]:
            key = (str(run["query_id"]), r["unique_id"])
            rows.setdefault(key, {"query_id": key[0], "unique_id": key[1], "service_id": run["service_id"],
                "query_latitude": run["query"]["latitude"], "query_longitude": run["query"]["longitude"],
                "name": r["name"], "facility_latitude": r["latitude"], "facility_longitude": r["longitude"],
                "evidence_text": "\n".join(e["text"] for e in r["evidence"]),
                "source_urls": "\n".join(r["source_urls"]),
                "service_supported": "", "identity_correct": "", "location_correct": "", "relevance": "", "notes": ""})
    return pd.DataFrame(rows.values())


def plots(per_query, summary, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from pathlib import Path
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    metrics = ["precision_at_k", "ndcg_at_k_pool", "candidate_recall_pool", "answered"]
    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    for ax, metric in zip(axes, metrics):
        valid = summary.dropna(subset=[metric])
        if valid.empty:
            ax.text(.5, .5, "Needs human qrels", ha="center")
        else:
            ax.bar(valid.method, valid[metric])
        ax.set_title(metric)
        ax.set_ylim(0, 1.05)
        ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(out / "method_comparison.png", dpi=160)
    plt.close(fig)
    heat = per_query.pivot_table(index="service_id", columns="method", values="answered", aggfunc="mean")
    fig, ax = plt.subplots(figsize=(max(6, len(heat.columns)*1.4), max(3, len(heat)*.5)))
    im = ax.imshow(heat, vmin=0, vmax=1, cmap="YlGnBu", aspect="auto")
    ax.set_xticks(range(len(heat.columns)), heat.columns, rotation=30)
    ax.set_yticks(range(len(heat.index)), heat.index)
    ax.set_title("Answer coverage (not correctness)")
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(out / "coverage_heatmap.png", dpi=160)
    plt.close(fig)
