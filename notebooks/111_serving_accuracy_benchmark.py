# Databricks notebook source
# MAGIC %md
# MAGIC # Actual web-backend ablation (independent qrels required)
# MAGIC Run in a separate notebook/process from the API: this harness temporarily patches config.
# MAGIC Reads the exact serving tables with Spark SELECTs; does not modify source data or production policy.
# COMMAND ----------
# MAGIC %pip install -r ../experiments/requirements-neural.txt
# COMMAND ----------
from pathlib import Path
import sys
ROOT=Path.cwd()
if not (ROOT/'backend').is_dir(): ROOT=ROOT.parent
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'backend'))
import config
from data_store import load_from_databricks
from benchmark_serving import benchmark_serving
from experiments.io import read_frame,table_name
# COMMAND ----------
dbutils.widgets.text('schema','workspace.cardinal_virtues')
dbutils.widgets.text('queries','')
dbutils.widgets.text('qrels','')
dbutils.widgets.text('out','')
if not all(dbutils.widgets.get(k).strip() for k in ['queries','qrels','out']):
 raise ValueError('Set independently labelled queries/qrels CSVs and a NEW private output directory')
schema=dbutils.widgets.get('schema')
table_name(schema)  # validate before interpolating into SELECT statements
config.TABLE_TAGS=schema+'.ref_service_tags'
config.TABLE_INDEX=schema+'.serving_service_index'
config.TABLE_FACILITIES=schema+'.serving_facilities'
config.TABLE_PINS=schema+'.pincode_reference'
def query(sql):
 frame=spark.sql(sql)
 return frame.columns,[tuple(row) for row in frame.collect()]
snapshot=load_from_databricks(query=query)
# COMMAND ----------
report=benchmark_serving(snapshot,read_frame(dbutils.widgets.get('queries')),
 read_frame(dbutils.widgets.get('qrels')),dbutils.widgets.get('out'))
display(report)
# COMMAND ----------
# MAGIC %md
# MAGIC Baseline: old serving cross-encoder policy (guard off, original 4:3 weights and travel scale).
# MAGIC Compare guard off/explicit/strict, rules/cross-encoder, text weights and travel scale.
# MAGIC Select on fully judged dev only, then compare the frozen winner on test. No automatic deployment.
# MAGIC Candidate recall is left blank because the API exposes only a count, not all candidate IDs.
