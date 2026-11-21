"""Try the ranker from the command line.

    cd api
    # facilities from a cached export (CSV/TSV of model_facilities):
    python -m app.ranking.cli --service kidney-dialysis --lat 20.296 --lon 85.825 \
        --facilities /tmp/model_facilities.tsv
    # or straight from Databricks (writes the cache for next time):
    python -m app.ranking.cli --service mri --lat 19.076 --lon 72.878 \
        --from-databricks --facilities /tmp/model_facilities.tsv

Needs data/tags/facility_tag_scores.csv (run pipeline/tfidf_classify.py) and,
optionally, data/tags/facility_tags.csv (pipeline/build_tags.py).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .loaders import (
    REPO_ROOT, TAGS_DIR, load_evidence_index, load_facilities_file, load_facilities_sql,
    load_specialty_normalizer, load_tag_catalog,
)
from .ranker import Ranker, RankQuery


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--service", required=True, help="tag id, e.g. kidney-dialysis or specialty:cardiology")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--radius", type=float, help="km (default from config; widens if too few results)")
    ap.add_argument("--no-widen", action="store_true")
    ap.add_argument("--mode", default="best_match", choices=["best_match", "nearest", "most_evidence"])
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--facilities", type=Path, required=True, help="CSV/TSV export of model_facilities")
    ap.add_argument("--from-databricks", action="store_true",
                    help="query model_facilities and write it to --facilities")
    ap.add_argument("--scores", type=Path, default=TAGS_DIR / "facility_tag_scores.csv")
    ap.add_argument("--refs", type=Path, default=TAGS_DIR / "facility_tags.csv")
    ap.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = ap.parse_args(argv)

    normalize = load_specialty_normalizer()
    if args.from_databricks:
        sys.path.insert(0, str(REPO_ROOT / "pipeline"))
        from databricks_sql import DatabricksSQL  # noqa: PLC0415
        facilities, report = load_facilities_sql(DatabricksSQL(), normalize_specialty=normalize,
                                                 cache_path=args.facilities)
    else:
        facilities, report = load_facilities_file(args.facilities, normalize)
    if report.missing_optional:
        print(f"note: columns not in facility data (scored neutral): {', '.join(report.missing_optional)}",
              file=sys.stderr)

    ranker = Ranker(facilities, load_evidence_index(args.scores, args.refs), load_tag_catalog())
    res = ranker.rank(RankQuery(args.service, args.lat, args.lon, radius_km=args.radius,
                                limit=args.limit, mode=args.mode, allow_widen=not args.no_widen))

    if args.json:
        print(json.dumps({
            "service": {"id": res.tag.id, "label": res.tag.label, "urgency": res.urgency, "decay_km": res.decay_km},
            "radius_km": res.radius_km, "total_candidates": res.total_candidates,
            "warnings": res.warnings, "stats": res.stats, "ranking_version": res.ranking_version,
            "results": [{
                "rank": r.rank, "facility_id": r.facility.unique_id, "facility_name": r.facility.name,
                "district": r.facility.district, "state": r.facility.state,
                "distance_km": round(r.score.distance_km, 2), "total_score": round(r.score.total, 1),
                "confidence_level": r.score.confidence, "score_breakdown": r.score.breakdown(),
                "evidence_refs": list(r.score.match.evidence.evidence_refs) if r.score.match.evidence else [],
                "uncertainty": r.score.uncertainty.to_dict(),
            } for r in res.results],
        }, indent=2, ensure_ascii=False))
        return 0

    print(f"{res.tag.label} [{res.urgency}, decay {res.decay_km:g} km] within {res.radius_km:g} km: "
          f"{res.total_candidates} candidates {res.warnings or ''}")
    for r in res.results:
        s = r.score
        print(f"{r.rank:>3}. {s.total:5.1f}  {s.confidence:<6} {s.distance_km:6.1f} km  "
              f"{s.match.gate_key:<22} {(r.facility.name or r.facility.unique_id)[:50]}"
              f"  [{', '.join(s.uncertainty.reason_codes)}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
