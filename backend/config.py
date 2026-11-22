"""Backend settings. Recommender rules mirror facilities_qc/00_config.py + 03_recommender_lib.py (section F)."""
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
RANKING_VERSION = "proof-x-closeness-v3"

# How far people reasonably travel for each kind of care (km). Closeness halves at this distance:
#   closeness = 1 / (1 + (km / travel_km)^2)      rank score = proof strength x closeness
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
