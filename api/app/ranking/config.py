"""Every tunable number of the rule-based ranker, in one place.

The values are starting points. Tune them against a graded evaluation set (see
docs/ranking_model.md) rather than by eye, and bump ``RANKING_VERSION`` whenever
a change would alter the order of results.

New service tags added to ``pipeline/tag_dictionary.py`` need no change here:
they inherit the urgency of their group (or ``DEFAULT_URGENCY``) and simply have
no specialty fallback until one is added to ``SPECIALTY_FALLBACK``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

RANKING_VERSION = "rules-v0.1"


# ── Urgency profiles: how far a patient will reasonably travel ───────────
# distance_score = exp(-road_km / decay_km). At road_km == decay_km the score is
# 0.37; at 2 × decay_km it is 0.14.
URGENCY_DECAY_KM: dict[str, float] = {
    "emergency": 10.0,   # time-critical: C-section, burns, snakebite, stroke
    "recurring": 15.0,   # visited many times: dialysis, chemotherapy, physiotherapy
    "routine": 20.0,     # ordinary consultations: fever, skin, ENT, dental
    "diagnostic": 25.0,  # one-off tests: MRI, CT, lab work
    "elective": 60.0,    # planned, quality matters more than distance: IVF, transplants
}
DEFAULT_URGENCY = "routine"

URGENCY_BY_GROUP: dict[str, str] = {
    "Emergency & critical care": "emergency",
    "Imaging & diagnostics": "diagnostic",
    "Dental": "routine",
    "Cancer": "elective",
}

URGENCY_BY_TAG: dict[str, str] = {
    # emergency
    "c-section": "emergency", "nicu": "emergency", "picu": "emergency",
    "burns": "emergency", "snakebite-rabies": "emergency", "stroke": "emergency",
    "fracture-trauma": "emergency", "appendicitis": "emergency",
    "pregnancy-delivery": "emergency", "high-risk-pregnancy": "emergency",
    # recurring
    "kidney-dialysis": "recurring", "chemotherapy": "recurring", "radiotherapy": "recurring",
    "physiotherapy": "recurring", "palliative-care": "recurring",
    # elective
    "ivf": "elective", "iui": "elective", "infertility": "elective",
    "kidney-transplant": "elective", "liver-transplant": "elective",
    "bone-marrow-transplant": "elective", "cardiac-surgery": "elective",
    "angioplasty": "elective", "pacemaker": "elective", "joint-replacement": "elective",
    "spine-surgery": "elective", "neurosurgery": "elective", "bariatric-surgery": "elective",
    "cosmetic-surgery": "elective", "refractive-surgery": "elective", "cataract": "elective",
}

# Straight-line km × this ≈ road km, until a routing engine is added.
ROAD_DETOUR_FACTOR = 1.3


# ── Specialty fallback ───────────────────────────────────────────────────
# A facility that lists one of these specialties but has no evidence sentence for
# the tag is still a candidate, gated low (see GATE["specialty_only"]). Keep the
# lists tight: a broad specialty (internalMedicine, radiology) says nothing about
# a specific service such as MRI, so equipment and unit tags have no fallback.
SPECIALTY_FALLBACK: dict[str, tuple[str, ...]] = {
    "kidney-failure": ("nephrology",),
    "kidney-stones": ("urology",),
    "prostate": ("urology",),
    "kidney-transplant": ("renalTransplantationUrology",),
    "heart-disease": ("cardiology",),
    "cardiac-surgery": ("cardiacSurgery", "cardiothoracicSurgery"),
    "varicose-veins": ("vascularSurgery",),
    "cancer": ("medicalOncology", "surgicalOncology", "radiationOncology"),
    "pregnancy-delivery": ("gynecologyAndObstetrics", "obstetricsAndMaternityCare"),
    "high-risk-pregnancy": ("maternalFetalMedicineOrPerinatology",),
    "infertility": ("reproductiveEndocrinologyAndInfertility",),
    "pcos": ("reproductiveEndocrinologyAndInfertility", "gynecology", "gynecologyAndObstetrics"),
    "hysterectomy": ("gynecology", "gynecologyAndObstetrics"),
    "family-planning": ("familyPlanningAndComplexContraception",),
    "child-development": ("developmentalBehavioralPediatrics", "pediatricNeurodevelopmentalDisabilities"),
    "cataract": ("cataractAndAnteriorSegmentSurgery",),
    "glaucoma": ("glaucomaOphthalmology",),
    "retina": ("retinaAndVitreoretinalOphthalmology",),
    "cornea": ("corneaOphthalmology",),
    "squint": ("pediatricsAndStrabismusOphthalmology",),
    "refractive-surgery": ("refractiveSurgeryOphthalmology",),
    "joint-replacement": ("jointReconstructionSurgery",),
    "spine-surgery": ("orthopedicSpineSurgery", "spineNeurosurgery"),
    "back-pain": ("orthopedicSpineSurgery", "spineNeurosurgery", "painMedicinePMR"),
    "fracture-trauma": ("orthopedicSurgery",),
    "arthritis": ("rheumatology",),
    "physiotherapy": ("physicalMedicineAndRehabilitation",),
    "stroke": ("neurology",),
    "epilepsy": ("epilepsyNeurology", "neurology"),
    "headache-migraine": ("headacheMedicine", "neurology"),
    "parkinsons-dementia": ("neurology",),
    "neurosurgery": ("neurosurgery",),
    "gallstones": ("generalSurgery", "hepatopancreatobiliarySurgery"),
    "hernia": ("generalSurgery",),
    "appendicitis": ("generalSurgery",),
    "piles-fistula": ("colorectalSurgery", "generalSurgery"),
    "liver-disease": ("gastroenterology", "hepatopancreatobiliarySurgery"),
    "bariatric-surgery": ("bariatricSurgery",),
    "ent": ("otolaryngology",),
    "sinus": ("otolaryngology",),
    "hearing": ("otolaryngology",),
    "tonsils": ("otolaryngology",),
    "asthma-copd": ("pulmonology",),
    "tuberculosis": ("pulmonology", "infectiousDiseases"),
    "sleep-apnea": ("sleepMedicine",),
    "diabetes": ("endocrinologyAndDiabetesAndMetabolism",),
    "thyroid": ("endocrinologyAndDiabetesAndMetabolism",),
    "hiv": ("infectiousDiseases",),
    "skin-disease": ("dermatology",),
    "hair-loss": ("dermatology",),
    "cosmetic-surgery": ("plasticSurgery",),
    "burns": ("burnAndTraumaPlasticSurgery",),
    "root-canal": ("endodontics",),
    "dental-implants": ("dentalImplants", "prosthodontics"),
    "orthodontics": ("orthodontics",),
    "dentures": ("prosthodontics",),
    "tooth-extraction": ("dentistry", "oralAndMaxillofacialSurgery"),
    "gum-disease": ("periodontics",),
    "mental-health": ("psychiatry",),
    "addiction": ("addictionPsychiatry",),
    "palliative-care": ("hospiceAndPalliativeInternalMedicine",),
}


# ── Facility types ───────────────────────────────────────────────────────
DENTAL_GROUP = "Dental"
# facility_category values never returned for a non-dental service / dental service.
EXCLUDED_CATEGORIES_NON_DENTAL = frozenset({"dentist", "pharmacy"})
EXCLUDED_CATEGORIES_DENTAL = frozenset({"pharmacy"})


@dataclass(frozen=True)
class RankingConfig:
    # Evidence gate G: multiplies every other component, so a nearby facility
    # can never outrank one with stronger evidence just by being close.
    gate: dict[str, float] = field(default_factory=lambda: {
        "strong": 1.0,
        "mention_with_specialty": 0.8,
        "mention": 0.6,
        "specialty_only": 0.5,
        "suggested": 0.35,
        "specialty_query": 1.0,  # the user searched for a specialty directly
    })
    # Weights of the components inside F. They sum to 1.
    weights: dict[str, float] = field(default_factory=lambda: {
        "service_match": 0.20,
        "evidence": 0.20,
        "distance": 0.30,
        "capacity": 0.10,
        "source": 0.10,
        "location_quality": 0.10,
    })
    # Penalty points subtracted from the 0–100 total.
    penalties: dict[str, float] = field(default_factory=lambda: {
        "coord_pin_conflict": 5.0,
        "implausible_scale": 5.0,
        "address_nothing_agrees": 5.0,
        "negated_claim": 10.0,
    })
    max_penalty: float = 20.0

    location_confidence_score: dict[str, float] = field(default_factory=lambda: {
        "high": 1.0, "medium": 0.7, "low": 0.3,
    })
    unknown_location_confidence_score: float = 0.5

    # Capacity: log-scaled, these values map to 1.0. Missing values score NEUTRAL,
    # because only ~25% of facilities publish beds and ~36% doctors.
    capacity_full_beds: int = 200
    capacity_full_doctors: int = 50
    capacity_full_specialties: int = 20
    capacity_neutral: float = 0.5

    # Source: recency of the facility's own web page / social posts.
    recency_half_life_days: float = 365.0
    recency_missing_score: float = 0.3
    stale_after_days: int = 730
    full_source_urls: int = 5

    # Retrieval
    default_radius_km: float = 25.0
    widen_radii_km: tuple[float, ...] = (50.0, 100.0, 200.0)
    min_results: int = 10
    default_limit: int = 20
    # In "nearest" mode only facilities at least this well evidenced are shown.
    nearest_min_gate: float = 0.6

    def decay_km(self, urgency: str) -> float:
        return URGENCY_DECAY_KM.get(urgency, URGENCY_DECAY_KM[DEFAULT_URGENCY])


DEFAULT_CONFIG = RankingConfig()


def urgency_for(tag_id: str, group: str | None) -> str:
    if tag_id in URGENCY_BY_TAG:
        return URGENCY_BY_TAG[tag_id]
    if group and group in URGENCY_BY_GROUP:
        return URGENCY_BY_GROUP[group]
    return DEFAULT_URGENCY
