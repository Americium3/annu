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
from experiments.io import load_tables, augment_facility_text, read_frame
from experiments.run import run_experiments
import pandas as pd

# COMMAND ----------
dbutils.widgets.text("schema", "workspace.cardinal_virtues")
dbutils.widgets.text("methods", "rules,tfidf,bm25")
dbutils.widgets.text("queries", str(ROOT / "experiments/queries.example.csv"))
dbutils.widgets.text("qrels", "")
dbutils.widgets.text("pins", "")
dbutils.widgets.text("out", "/Volumes/workspace/cardinal_virtues/tag_files/experiments/run_001")

# COMMAND ----------
# Uses SELECT and toPandas only; no .cache(), RDD access, or source table mutation.
facilities, evidence = load_tables(dbutils.widgets.get("schema"), spark=spark)
engine = ExperimentEngine(facilities, augment_facility_text(facilities, evidence), Settings())
queries = read_frame(dbutils.widgets.get("queries"))
qrels_path = dbutils.widgets.get("qrels").strip()
pins_path = dbutils.widgets.get("pins").strip()
runs, metrics, summary = run_experiments(
    engine, queries, [m.strip() for m in dbutils.widgets.get("methods").split(",")],
    dbutils.widgets.get("out"), read_frame(qrels_path) if qrels_path else None,
    read_frame(pins_path) if pins_path else None,
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
