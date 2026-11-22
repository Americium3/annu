"""python -m experiments.run --help (run from repository root)."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import time
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .engine import ExperimentEngine, Settings, METHODS, canonical_service, geojson
from .evaluation import annotation_pool, evaluate, plots
from .io import augment_facility_text, dump_json, load_tables, read_frame, resolve_location


def map_html(runs):
    """One map with switchable method/query layers; escape data before embedding."""
    layers = [{"label": f"{r['query_id']} / {r['method']}", "data": geojson(r), "query": r["query"]} for r in runs]
    data = json.dumps(layers, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    return '''<!doctype html><html><head><meta charset="utf-8"><title>Reranking comparison</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>body{margin:0;font:14px system-ui}#map{height:88vh}header{padding:12px}select{max-width:80vw}</style></head>
<body><header><b>Candidate reranking experiments</b> <select id="choice"></select>
<div>Approximate straight-line distances. Text support is not verified availability. PIN markers are area references.</div></header>
<div id="map"></div><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const layers=DATA; const map=L.map('map').setView([22,79],5);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors'}).addTo(map);
const select=document.getElementById('choice'); let active=L.layerGroup().addTo(map);
layers.forEach((x,i)=>{const o=document.createElement('option');o.value=i;o.textContent=x.label;select.appendChild(o)});
function show(){active.clearLayers();const x=layers[Number(select.value)];if(!x)return;
const points=[[x.query.latitude,x.query.longitude]];
L.circleMarker(points[0],{color:'black',radius:6}).addTo(active).bindPopup('Query reference point');
x.data.features.forEach(f=>{const p=f.properties;const pt=[f.geometry.coordinates[1],f.geometry.coordinates[0]];points.push(pt);
const box=document.createElement('div');const title=document.createElement('b');title.textContent=p.rank+'. '+p.name;box.appendChild(title);
[p.recommendation_reason,'Location: '+p.location_tier,...p.warnings].forEach(t=>{const el=document.createElement('p');el.textContent=t;box.appendChild(el)});
L.marker(pt).addTo(active).bindPopup(box)});map.fitBounds(points,{maxZoom:12,padding:[30,30]});}
select.onchange=show;show();</script></body></html>'''.replace("DATA", data, 1)


def run_experiments(engine, queries, methods, out, qrels=None, pins=None):
    required = {"query_id", "service"}
    if not required.issubset(queries):
        raise ValueError("Queries need query_id and service; plus latitude/longitude or location")
    if queries.query_id.isna().any() or queries.query_id.astype(str).duplicated().any():
        raise ValueError("query_id must be unique and non-null")
    if not methods or len(set(methods)) != len(methods) or not set(methods).issubset(METHODS):
        raise ValueError("Choose distinct methods from " + ", ".join(METHODS))
    out = Path(out)
    if (out / "manifest.json").exists():
        raise ValueError("Output already contains a run; choose a new directory")
    out.mkdir(parents=True, exist_ok=True)
    resolved = []
    for q in queries.to_dict("records"):
        canonical_service(q["service"])
        if str(q.get("latitude", "")).strip() and str(q.get("longitude", "")).strip():
            loc = resolve_location(f"{q['latitude']},{q['longitude']}", engine.facilities)
        else:
            loc = resolve_location(q.get("location", ""), engine.facilities, pins)
        resolved.append({**q, **loc})
    # Eagerly precompute all service/model pairs. Time this separately from warm queries.
    timings = []
    for method in methods:
        for service in sorted({canonical_service(q["service"]) for q in resolved}):
            start = time.perf_counter()
            engine.score_service(service, method)  # fail visibly; never substitute another model
            timings.append({"service_id": service, "method": method, "seconds": time.perf_counter()-start})
    runs = []
    for q in resolved:
        for method in methods:
            run = engine.recommend(q["service"], q["latitude"], q["longitude"], method)
            run.update(query_id=str(q["query_id"]), density_group=q.get("density_group", "unspecified"))
            run["query"].update(precision=q["precision"], resolved=q["resolved"])
            runs.append(run)
    empty_qrels = pd.DataFrame(columns=["query_id", "unique_id", "relevance"])
    per_query, summary = evaluate(runs, qrels if qrels is not None else empty_qrels, engine.settings.top_k)
    dump_json(out / "runs.json", runs)
    pd.DataFrame(timings).to_csv(out / "precompute_timings.csv", index=False)
    per_query.to_csv(out / "metrics_per_query.csv", index=False)
    summary.to_csv(out / "metrics_summary.csv", index=False)
    annotation_pool(runs).to_csv(out / "annotation_pool.csv", index=False)
    # Full extraction audit, not only the shared capped scoring passages.
    extraction = pd.concat([engine.candidates(s) for s in sorted({canonical_service(q['service']) for q in resolved})], ignore_index=True)
    extraction.to_csv(out / "service_candidates.csv", index=False)
    for i, run in enumerate(runs):
        dump_json(out / "geojson" / f"{i:04d}.geojson", geojson(run))
    (out / "map.html").write_text(map_html(runs), encoding="utf-8")
    versions = {}
    for package in ("numpy", "pandas", "scikit-learn", "sentence-transformers", "torch", "transformers"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    dump_json(out / "manifest.json", {"settings": asdict(engine.settings), "methods": methods,
        "data_fingerprint": engine.data_fingerprint,
        "query_fingerprint": hashlib.sha256(queries.to_csv(index=False).encode()).hexdigest(),
        "python": platform.python_version(), "packages": versions, "setup_seconds": engine.setup_seconds,
        "orphan_evidence_count": engine.orphan_evidence_count, "queries": len(resolved),
        "labelled": qrels is not None, "latency_scope": "warm recommendation only; see precompute_timings.csv",
        "notes": ["No clinical verification. Metrics use independent human qrels.",
                  "Recall/nDCG are relative to the annotated candidate pool.",
                  "Positive/negative clause detection is heuristic; independently inspect missed cases.",
                  "Pin model_revision for exact neural artifact reproducibility."]})
    plots(per_query, summary, out / "plots")
    return runs, per_query, summary


def main():
    from .engine import DEFAULT_METHOD
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facilities", help="CSV/TSV/parquet export of model_facilities")
    parser.add_argument("--evidence", help="CSV/TSV/parquet export of model_evidence_items")
    parser.add_argument("--from-databricks", action="store_true")
    parser.add_argument("--schema", default="workspace.cardinal_virtues")
    parser.add_argument("--queries", required=True)
    parser.add_argument("--pins", help="Optional audited pincode_reference export")
    parser.add_argument("--qrels", help="Independently annotated query/facility grades")
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=[DEFAULT_METHOD])
    parser.add_argument("--out", required=True)
    parser.add_argument("--settings", help="Settings JSON; omit to use documented defaults")
    args = parser.parse_args()
    if args.from_databricks:
        fac, ev = load_tables(args.schema)
    elif args.facilities and args.evidence:
        fac, ev = read_frame(args.facilities), read_frame(args.evidence)
    else:
        parser.error("Supply --facilities and --evidence or --from-databricks")
    settings = Settings(**json.loads(Path(args.settings).read_text())) if args.settings else Settings()
    engine = ExperimentEngine(fac, augment_facility_text(fac, ev), settings)
    _, _, summary = run_experiments(engine, read_frame(args.queries), args.methods, args.out,
                                   read_frame(args.qrels) if args.qrels else None,
                                   read_frame(args.pins) if args.pins else None)
    print(summary.to_string(index=False))
    print(f"Outputs: {args.out}; unlabelled accuracy cells remain blank, not fabricated.")


if __name__ == "__main__":
    main()
