#!/usr/bin/env bash
set -euo pipefail
# Run from repository root. Output directory must be new. Dependencies must already be installed.
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 python -m experiments.benchmark \
 --facilities experiments/challenge/facilities.csv --evidence experiments/challenge/evidence.csv \
 --queries experiments/challenge/queries.csv --qrels experiments/challenge/qrels.csv \
 --data-kind synthetic --methods rules tfidf bm25 bi_encoder cross_encoder \
 --cross-models cross-encoder/ms-marco-MiniLM-L6-v2 cross-encoder/ms-marco-TinyBERT-L2-v2 \
 --out "${1:?Provide a NEW output directory}"
# Reproduce the actual backend matrix separately (also SYNTHETIC):
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 python backend/benchmark_serving.py \
 --synthetic-challenge --queries experiments/challenge/queries.csv \
 --qrels experiments/challenge/qrels.csv --out "${1}_serving"
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 python -m experiments.claim_diagnostic --out "${1}_diagnostic.json"
