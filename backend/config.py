"""Serving policy and the default cross-encoder reranker configuration."""
from __future__ import annotations

import os
from pathlib import Path

SCHEMA = os.environ.get("CAREPATH_SCHEMA", "workspace.cardinal_virtues")
TABLE_INDEX = f"{SCHEMA}.serving_service_index"        # built by Databricks notebook 06_build_serving_tables
TABLE_FACILITIES = f"{SCHEMA}.serving_facilities"      # built by Databricks notebook 06_build_serving_tables
TABLE_TAGS = f"{SCHEMA}.ref_service_tags"
TABLE_PINS = f"{SCHEMA}.pincode_reference"

CACHE_FILE = Path(os.environ.get("CAREPATH_CACHE", Path(__file__).resolve().parent / ".cache" / "snapshot.pkl"))

RADIUS_STEPS_KM = [25, 50, 100, 200]          # search widens until a recommendable provider is found
DISTANCE_BANDS_KM = [0, 10, 30, 60, 100, 200, 500]
EMERGENCY_TAG = "emergency-24x7"
K_MAIN, K_SUPPORT = 3, 2                      # lane A / lane B sizes (as in notebook 70)
RESULT_LIMIT = 8                              # results returned per search (system setting, not a user input)
RANKING_METHOD = os.environ.get("CAREPATH_RANKING_METHOD", "cross_encoder")
RANKING_VERSION = "service-first-cross-encoder-v1" if RANKING_METHOD == "cross_encoder" else "service-first-rules-v2"
CROSS_ENCODER_MODEL = os.environ.get("CAREPATH_CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L6-v2")
CROSS_ENCODER_REVISION = os.environ.get("CAREPATH_CROSS_ENCODER_REVISION") or None
CROSS_ENCODER_DEVICE = os.environ.get("CAREPATH_CROSS_ENCODER_DEVICE", "cpu")
CROSS_ENCODER_BATCH_SIZE = int(os.environ.get("CAREPATH_CROSS_ENCODER_BATCH_SIZE", "32"))
CROSS_ENCODER_MAX_LENGTH = int(os.environ.get("CAREPATH_CROSS_ENCODER_MAX_LENGTH", "512"))
CROSS_ENCODER_MAX_EVIDENCE = 5
RERANK_WEIGHTS = {"text": .4, "evidence": .3, "distance": .3}
DISTANCE_DECAY_KM = 30.0

# Extra user wordings → tag id (kept in sync with SERVICE_INPUT_SYNONYMS in facilities_qc/00_config.py)
SERVICE_INPUT_SYNONYMS = {
    "nicu": ["neonatal intensive care", "neonatal icu", "newborn icu", "neonatal care"],
    "c-section": ["caesarean", "cesarean", "emergency c-section", "emergency c section", "emergency caesarean",
                  "emergency cesarean", "caesarean delivery", "cesarean delivery"],
    "burns": ["burn", "burn care", "burn unit", "burns unit", "burn ward", "burn treatment"],
    "mri": ["mri", "mri scan", "magnetic resonance"],
    "cardiac-surgery": ["cardiac surgery", "heart surgery", "open heart surgery"],
    "kidney-dialysis": ["dialysis", "haemodialysis", "kidney dialysis"],
    "fracture-trauma": ["trauma", "trauma care", "accident"],
    "x-ray": ["xray", "x ray"],
    "snakebite-rabies": ["snakebite", "snake bite", "rabies", "dog bite"],
}

DIRECTORY_DOMAINS = ("practo.com", "justdial.com", "hexahealth.com", "lybrate.com", "medindia.net", "apollo247.com",
                     "policyx.com", "onefivenine.com", "bharatibiz.com", "ambitionbox.com", "credihealth.com",
                     "sehat.com", "clinicspots.com", "healthfrog.in", "quickerala.com", "sulekha.com", "indiamart.com",
                     "business.site", "bookimed.com", "medifee.com", "vaidam.com", "joonsquare.com", "drlogy.com")
SOCIAL_DOMAINS = ("facebook.com", "instagram.com", "linkedin.com", "youtube.com", "twitter.com", "x.com", "wa.me")
