"""Serving policy and the default cross-encoder reranker configuration."""
from __future__ import annotations

import os
from pathlib import Path

SCHEMA = os.environ.get("CAREPATH_SCHEMA", "workspace.cardinal_virtues")
# Stage 1: "v2" builds high-recall facility x service candidates from model_evidence_items with
# pipeline/service_index_v2.py when the snapshot is loaded (see experiments/RESULTS.md); "v1" reads serving_service_index.
SERVICE_INDEX_VERSION = os.environ.get("CAREPATH_SERVICE_INDEX", "v2")
TABLE_EVIDENCE = f"{SCHEMA}.model_evidence_items"
TABLE_INDEX = f"{SCHEMA}.serving_service_index"        # built by Databricks notebook 06_build_serving_tables
TABLE_FACILITIES = f"{SCHEMA}.serving_facilities"      # built by Databricks notebook 06_build_serving_tables
TABLE_TAGS = f"{SCHEMA}.ref_service_tags"
TABLE_PINS = f"{SCHEMA}.pincode_reference"
TABLE_ADDRESS_ALIAS = f"{SCHEMA}.ref_address_alias"   # old / variant spellings of states and cities

CACHE_FILE = Path(os.environ.get("CAREPATH_CACHE", Path(__file__).resolve().parent / ".cache" / "snapshot.pkl"))

RADIUS_STEPS_KM = [25, 50, 100, 200]          # search widens until a recommendable provider is found
DISTANCE_BANDS_KM = [0, 10, 30, 60, 100, 200, 500]
EMERGENCY_TAG = "emergency-24x7"
K_MAIN, K_SUPPORT = 3, 2                      # lane A / lane B sizes (as in notebook 70)
RESULT_LIMIT = 8                              # results returned per search (system setting, not a user input)
# Default "rules" (proof x closeness): on the golden dev set no text model beat it once stage 1 was fixed
# (experiments/RESULTS.md, section 2). "cross_encoder" stays available: CAREPATH_RANKING_METHOD=cross_encoder.
RANKING_METHOD = os.environ.get("CAREPATH_RANKING_METHOD", "rules")
RANKING_VERSION = "cross-encoder-x-closeness-v6-claim-guard" if RANKING_METHOD == "cross_encoder" else "proof-x-closeness-v6-claim-guard"
CROSS_ENCODER_MODEL = os.environ.get("CAREPATH_CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L6-v2")
CROSS_ENCODER_REVISION = os.environ.get("CAREPATH_CROSS_ENCODER_REVISION") or None
CROSS_ENCODER_DEVICE = os.environ.get("CAREPATH_CROSS_ENCODER_DEVICE", "cpu")
CROSS_ENCODER_BATCH_SIZE = int(os.environ.get("CAREPATH_CROSS_ENCODER_BATCH_SIZE", "32"))
CROSS_ENCODER_MAX_LENGTH = int(os.environ.get("CAREPATH_CROSS_ENCODER_MAX_LENGTH", "512"))
CROSS_ENCODER_MAX_EVIDENCE = 5
# How the service is phrased for the cross-encoder: "natural" = "a hospital that provides <service>" (best in the
# golden-set grid, experiments/RESULTS.md), "keywords" = label + synonyms (the earlier default).
CROSS_ENCODER_QUERY_STYLE = os.environ.get("CAREPATH_CROSS_ENCODER_QUERY_STYLE", "natural")
# Evidence strength with the cross-encoder (the live default) blends how well the best quote matches the service
# with proof strength; the 4:3 split keeps the earlier text:evidence weighting. Distance is not a third weight:
# closeness multiplies the whole evidence score, with the travel distance set per kind of care (above).
#   evidence = 4/7 x text match + 3/7 x proof strength      rank score = evidence x closeness
# text 0.25 / proof 0.75 was picked by leave-one-query-out CV on the golden dev set (was 4/7 : 3/7)
RERANK_WEIGHTS = {"text": 0.25, "proof": 0.75}


# How far people reasonably travel for each kind of care (km). Closeness halves at this distance:
#   closeness = 1 / (1 + (km / travel_km)^2)      rank score = evidence strength x closeness
# Urgent care has to be near; planned specialist care is worth a longer trip.
TRAVEL_KM_URGENT, TRAVEL_KM_ROUTINE, TRAVEL_KM_DIAGNOSTIC, TRAVEL_KM_PLANNED = 10, 15, 30, 60
TRAVEL_KM_DEFAULT = 25
TRAVEL_KM_BY_TAG = {
    **dict.fromkeys(["emergency-24x7", "icu", "ambulance", "blood-bank", "nicu", "picu", "c-section",
                     "pregnancy-delivery", "fracture-trauma", "burns", "snakebite-rabies"], TRAVEL_KM_URGENT),
    **dict.fromkeys(["kidney-dialysis", "physiotherapy", "chemotherapy", "radiotherapy", "vaccination", "pathology-lab",
                     "x-ray", "ecg", "ultrasound", "root-canal", "tooth-extraction", "dentures", "orthodontics",
                     "family-planning", "pregnancy-termination", "health-checkup", "palliative-care"], TRAVEL_KM_ROUTINE),
    **dict.fromkeys(["mri", "ct-scan", "echocardiography", "stress-test", "mammography", "endoscopy", "eeg-emg",
                     "pulmonary-function", "bone-density", "ent", "angiography", "dental-implants"], TRAVEL_KM_DIAGNOSTIC),
    **dict.fromkeys(["cardiac-surgery", "angioplasty", "pacemaker", "neurosurgery", "spine-surgery", "joint-replacement",
                     "arthroscopy", "bariatric-surgery", "liver-transplant", "kidney-transplant", "bone-marrow-transplant",
                     "ivf", "iui", "hysterectomy", "cosmetic-surgery", "refractive-surgery", "pet-ct"], TRAVEL_KM_PLANNED),
}
# Proof strength: evidence tier, then multipliers for weaker kinds of evidence or location.
PROOF_BY_TIER = {1: 1.0, 2: 0.8, 3: 0.55}
PROOF_ONLY_EQUIPMENT = 0.6          # only equipment is mentioned, not the service itself
PROOF_MENTIONS_OTHER = 0.85         # some statements also name another institution
PROOF_BY_LOCATION = {"point_verified": 1.0, "point_unverified": 0.9, "pin_area": 0.75}
# Weak proof (equipment only, or proof below this) is always listed after every facility with solid proof,
# however close it is: being next door must never push a weak claim above a solid one.
PROOF_SOLID_MIN = 0.5
# What makes proof "solid" (listed before weak proof): "proof" = proof strength >= PROOF_SOLID_MIN (location and
# single-statement penalties included, so a one-sentence claim at an unverified point fell behind everything);
# "evidence" = explicit service text that is not equipment-only and not down-weighted for source or plausibility;
# "off" = no separate tier.
SOLID_GATE = os.environ.get("CAREPATH_SOLID_GATE", "evidence")

# Search area: widen 25 -> 50 -> 100 -> 200 km until at least this many recommendable facilities are inside
# (people need options to compare; stopping at the first hit often left one far-from-ideal answer).
MIN_POOL_SIZE = int(os.environ.get("CAREPATH_MIN_POOL_SIZE", "3"))
# Service text that names several services ("Trauma / emergency care") searches all of them.
MULTI_INTENT = True
# Urgent wording in the service text ("emergency C-section", "accident") can put facilities with emergency / 24x7
# evidence first: proof strength of facilities without it is multiplied by this factor. Off by default (1.0): on the
# golden dev set 0.6 did not help (experiments/RESULTS.md, E5c); "Trauma / emergency care" is handled by the intent
# step instead, which searches the 24/7 emergency service too.
EMERGENCY_WORDS = r"\b(emergency|emergencies|urgent|accident|trauma|casualty|24\s*[x/]\s*7|24 ?hours?)\b"
EMERGENCY_MISSING_FACTOR = float(os.environ.get("CAREPATH_EMERGENCY_MISSING_FACTOR", "1.0"))

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
    "emergency-24x7": ["emergency", "emergency care", "emergency services", "emergency department", "casualty", "24x7 emergency"],
    "x-ray": ["xray", "x ray"],
    "snakebite-rabies": ["snakebite", "snake bite", "rabies", "dog bite"],
}

DIRECTORY_DOMAINS = ("practo.com", "justdial.com", "hexahealth.com", "lybrate.com", "medindia.net", "apollo247.com",
                     "policyx.com", "onefivenine.com", "bharatibiz.com", "ambitionbox.com", "credihealth.com",
                     "sehat.com", "clinicspots.com", "healthfrog.in", "quickerala.com", "sulekha.com", "indiamart.com",
                     "business.site", "bookimed.com", "medifee.com", "vaidam.com", "joonsquare.com", "drlogy.com")
SOCIAL_DOMAINS = ("facebook.com", "instagram.com", "linkedin.com", "youtube.com", "twitter.com", "x.com", "wa.me")

# Explicit contradictions/plans are excluded before radius selection and model scoring.
CLAIM_GUARD_POLICY = os.environ.get("CAREPATH_CLAIM_GUARD", "explicit")
