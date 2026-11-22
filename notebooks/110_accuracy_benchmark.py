# Databricks notebook source
# MAGIC %md
# MAGIC # Accuracy benchmark: independent qrels, frozen test selection
# MAGIC SELECT-only data access. Generated outputs contain facility evidence: use a private writable Volume.
# COMMAND ----------
# MAGIC %pip install -r ../experiments/requirements-neural.txt
# COMMAND ----------
from pathlib import Path
import sys
ROOT=Path.cwd()
if not (ROOT/'experiments').is_dir(): ROOT=ROOT.parent
sys.path.insert(0,str(ROOT))
from experiments.io import load_tables,read_frame,augment_facility_text
from experiments.benchmark import benchmark
# COMMAND ----------
dbutils.widgets.text('schema','workspace.cardinal_virtues')
dbutils.widgets.text('queries','')
dbutils.widgets.text('qrels','')
dbutils.widgets.text('methods','rules,tfidf,bm25,bi_encoder,cross_encoder')
dbutils.widgets.text('cross_models','cross-encoder/ms-marco-MiniLM-L6-v2,cross-encoder/ms-marco-TinyBERT-L2-v2')
dbutils.widgets.text('out','')
# COMMAND ----------
if not all(dbutils.widgets.get(k).strip() for k in ['queries','qrels','out']):
 raise ValueError('Provide reviewed query CSV, independently labelled qrels CSV, and a NEW private output directory')
fac,ev=load_tables(dbutils.widgets.get('schema'),spark=spark)
report=benchmark(fac,augment_facility_text(fac,ev),read_frame(dbutils.widgets.get('queries')),
 read_frame(dbutils.widgets.get('qrels')),dbutils.widgets.get('out'),
 methods=dbutils.widgets.get('methods').split(','),cross_models=dbutils.widgets.get('cross_models').split(','),data_kind='real')
display(report)
# COMMAND ----------
# MAGIC %md
# MAGIC Inspect REPORT.md, attempts.json, dev_summary.csv and test_per_query.csv.
# MAGIC Fully judge all model outputs before comparing precision/nDCG. Do not present
# MAGIC synthetic challenge performance as real facility recommendation accuracy.
