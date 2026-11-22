# Databricks notebook source
# MAGIC %md
# MAGIC # Two-stage service retrieval experiments
# MAGIC Run from a Databricks Git folder containing this repository. No table writes.
# MAGIC CPU defaults; neural models require model downloads and extra packages.

# COMMAND ----------
# MAGIC %pip install -r ../experiments/requirements.txt

# COMMAND ----------
from pathlib import Path
import sys

ROOT = Path.cwd()
if not (ROOT / "experiments").is_dir():
    ROOT = ROOT.parent
if not (ROOT / "experiments").is_dir():
    raise RuntimeError("Open this notebook inside the cloned cardinal_virtues Git folder")
sys.path.insert(0, str(ROOT))

from experiments.engine import ExperimentEngine, Settings
from experiments.io import load_tables, load_context_table, augment_facility_text, read_frame
from experiments.district_context import DistrictContext, DEFAULT_NFHS_TABLE
import json
from experiments.run import run_experiments
import pandas as pd

# COMMAND ----------
dbutils.widgets.text("schema", "workspace.cardinal_virtues")
dbutils.widgets.text("methods", "rules,tfidf,bm25")
dbutils.widgets.text("queries", str(ROOT / "experiments/queries.example.csv"))
dbutils.widgets.text("qrels", "")
dbutils.widgets.text("pins", "")
dbutils.widgets.text("nfhs_table", "")  # Optional: paste DEFAULT_NFHS_TABLE; blank disables context.
dbutils.widgets.text("district_alias_table", "")  # Reviewed export with the documented column names.
dbutils.widgets.text("nfhs_group_bins", "")  # Optional JSON path with frozen cut points.
dbutils.widgets.text("out", "/Volumes/workspace/cardinal_virtues/tag_files/experiments/run_001")

# COMMAND ----------
# Uses SELECT and toPandas only; no .cache(), RDD access, or source table mutation.
facilities, evidence = load_tables(dbutils.widgets.get("schema"), spark=spark)
engine = ExperimentEngine(facilities, augment_facility_text(facilities, evidence), Settings())
queries = read_frame(dbutils.widgets.get("queries"))
qrels_path = dbutils.widgets.get("qrels").strip()
pins_path = dbutils.widgets.get("pins").strip()
nfhs_table = dbutils.widgets.get("nfhs_table").strip()
alias_table = dbutils.widgets.get("district_alias_table").strip()
bins_path = dbutils.widgets.get("nfhs_group_bins").strip()
if not nfhs_table and (alias_table or bins_path):
    raise ValueError("Set nfhs_table to use district aliases/bins")
context = DistrictContext(
    load_context_table(nfhs_table, spark=spark),
    load_context_table(alias_table, spark=spark) if alias_table else None,
    group_bins=json.loads(Path(bins_path).read_text()) if bins_path else None,
) if nfhs_table else None
runs, metrics, summary = run_experiments(
    engine, queries, [m.strip() for m in dbutils.widgets.get("methods").split(",")],
    dbutils.widgets.get("out"), read_frame(qrels_path) if qrels_path else None,
    read_frame(pins_path) if pins_path else None,
    district_context=context,
)
display(summary)
display(metrics)

# COMMAND ----------
# MAGIC %md
# MAGIC Download/open `map.html`, GeoJSON, plots and `annotation_pool.csv` from the output path.
# MAGIC Grade the pool independently (0–3), add suspected misses outside the pool, then run
# MAGIC again with the qrels path and a NEW output directory. Blank metrics mean unlabelled.
# MAGIC For neural methods: install `../experiments/requirements-neural.txt` in a separate
# MAGIC `%pip` cell before imports, then add `bi_encoder,cross_encoder` to methods.
# MAGIC The output Volume must already exist and be writable; change the path if necessary.
# MAGIC
# MAGIC Optional NFHS: set `nfhs_table` to
# MAGIC `databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.nfhs_5_district_health_indicators`.
# MAGIC Supply reviewed `context_state,context_district` query metadata for coordinate/city inputs;
# MAGIC audited district/PIN inputs supply these automatically. No nearest-hospital district guessing.
# MAGIC `district_alias_table` requires `source_state,source_district,target_state,target_district,mapping_type`;
# MAGIC adapt your existing `ref_district_alias` to this contract before selecting it. No fuzzy or boundary-change join.
# MAGIC NFHS affects only background, subgroup metrics and map reference-point overlays, never ranking.
# MAGIC Outputs: `district_context.csv`, join audits, `district_service_coverage.csv`,
# MAGIC `metrics_by_district_context.csv`, `district_context.geojson` and `plots/nfhs_groups_*.png`.
# MAGIC Without qrels, precision/nDCG remain blank. Freeze bin thresholds from the context manifest for comparisons.
