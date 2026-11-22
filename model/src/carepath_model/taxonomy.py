from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


PROCEDURE_FIELD = "procedure_arr"
CAPABILITY_FIELD = "capability_arr"
EQUIPMENT_FIELD = "equipment_arr"
SPECIALTY_FIELD = "specialties_std"
SOURCE_FIELDS = (PROCEDURE_FIELD, CAPABILITY_FIELD, EQUIPMENT_FIELD, SPECIALTY_FIELD)

PROCEDURE_CATEGORIES = (
    "diagnostic_procedure",
    "therapeutic_procedure",
    "surgical_procedure",
    "screening_procedure",
    "follow_up_procedure",
    "emergency_procedure",
    "supportive_procedure",
    "unclassified",
)

CAPABILITY_CATEGORIES = (
    "service_offered",
    "care_setting",
    "critical_care",
    "emergency_availability",
    "diagnostic_capability",
    "therapeutic_capability",
    "accreditation",
    "ownership_or_facility_type",
    "accessibility",
    "general_marketing",
    "administrative",
    "unclassified",
)

EQUIPMENT_CATEGORIES = (
    "diagnostic_imaging",
    "diagnostic_monitoring",
    "therapeutic_device",
    "renal_device",
    "respiratory_device",
    "neonatal_device",
    "critical_care_device",
    "laboratory_device",
    "support_device",
    "accessibility",
    "irrelevant_or_ambiguous",
    "unclassified",
)

CATEGORY_BY_FIELD = {
    PROCEDURE_FIELD: PROCEDURE_CATEGORIES,
    CAPABILITY_FIELD: CAPABILITY_CATEGORIES,
    EQUIPMENT_FIELD: EQUIPMENT_CATEGORIES,
    SPECIALTY_FIELD: ("specialty",),
}

SPELLING_REPLACEMENTS = (
    ("haemodialysis", "hemodialysis"),
    ("paediatric", "pediatric"),
    ("paedodontic", "pedodontic"),
    ("orthopaedic", "orthopedic"),
    ("gynaec", "gynec"),
    ("haemat", "hemat"),
    ("anaesth", "anesth"),
    ("oesoph", "esoph"),
    ("foetal", "fetal"),
    ("homoeo", "homeo"),
)

ABBREVIATION_REPLACEMENTS = (
    (r"\bct scans?\b", "computed tomography scan"),
    (r"\bmri scans?\b", "magnetic resonance imaging scan"),
    (r"\becgs?\b|\bekgs?\b", "electrocardiography"),
    (r"\bivf\b", "in vitro fertilization"),
    (r"\bicu\b", "intensive care unit"),
    (r"\bnicu\b", "neonatal intensive care unit"),
    (r"\bpicu\b", "pediatric intensive care unit"),
    (r"\bcabg\b", "coronary artery bypass graft"),
    (r"\bct\b", "computed tomography"),
    (r"\bmri\b", "magnetic resonance imaging"),
)

NEGATION_RE = re.compile(
    r"\b(no|not|without|unavailable|planned|coming soon|proposed|"
    r"partner facility|referral only|discontinued|closed)\b"
)


@dataclass(frozen=True)
class WeakLabel:
    category: str
    evidence_role: str
    confidence: float
    match_method: str


def normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    text = text.replace("&", " and ")
    for source, target in SPELLING_REPLACEMENTS:
        text = text.replace(source, target)
    for pattern, replacement in ABBREVIATION_REPLACEMENTS:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"[_\W]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _has(text: str, *patterns: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _procedure_category(text: str) -> str:
    if _has(text, r"\bemergency\b", r"\btrauma\b", r"\baccident\b"):
        return "emergency_procedure"
    if _has(text, r"\bfollow up\b", r"\bpost operative\b", r"\bpostoperative\b", r"\breview\b"):
        return "follow_up_procedure"
    if _has(text, r"\bscreen(ing)?\b", r"\bpreventive\b"):
        return "screening_procedure"
    if _has(
        text,
        r"\bscan\b",
        r"\bimaging\b",
        r"\bradiograph\b",
        r"\bultrasound\b",
        r"\bechocardiogra",
        r"\bendoscop",
        r"\bbiopsy\b",
        r"\blaboratory\b",
        r"\bpathology\b",
        r"\btest\b",
    ):
        return "diagnostic_procedure"
    if _has(
        text,
        r"\bsurgeon\b",
        r"\bsurgical\b",
        r"\bsurgery\b",
        r"\btransplant",
        r"\bectomy\b",
        r"\bplasty\b",
        r"\bcraniotomy\b",
        r"\blaparoscop",
        r"\barthroscop",
    ):
        return "surgical_procedure"
    if _has(
        text,
        r"\bphysiotherap",
        r"\brehabilitation\b",
        r"\bnutrition\b",
        r"\bpalliative\b",
        r"\bcounsel",
        r"\bspeech therapy\b",
    ):
        return "supportive_procedure"
    if _has(
        text,
        r"\btreatment\b",
        r"\btherapy\b",
        r"\bprocedure\b",
        r"\boperation\b",
        r"\bcatheter",
        r"\bstent",
        r"\bdialysis\b",
        r"\bchemotherapy\b",
        r"\bradiotherapy\b",
        r"\bventilation\b",
    ):
        return "therapeutic_procedure"
    return "unclassified"


def _capability_category(text: str) -> str:
    if _has(text, r"\bwheelchair\b", r"\bramp\b", r"\baccessible\b", r"\baccessibility\b"):
        return "accessibility"
    if _has(text, r"\baccredit", r"\bnabh\b", r"\bnabl\b", r"\bcertified\b"):
        return "accreditation"
    if _has(
        text,
        r"\bprivate\b",
        r"\bpublic\b",
        r"\btrust\b",
        r"\bmultispeciality\b",
        r"\bmulti speciality\b",
        r"\bhospital\b",
        r"\bclinic\b",
    ):
        return "ownership_or_facility_type"
    if _has(text, r"\b24x7\b", r"\b24 7\b", r"\bemergency\b", r"\btrauma centre\b"):
        return "emergency_availability"
    if _has(text, r"\bicu\b", r"\bintensive care\b", r"\bcritical care\b"):
        return "critical_care"
    if _has(
        text,
        r"\bdiagnostic\b",
        r"\bimaging\b",
        r"\bscan\b",
        r"\blaboratory\b",
        r"\bpathology\b",
        r"\btests?\b",
    ):
        return "diagnostic_capability"
    if _has(
        text,
        r"\bsurgery\b",
        r"\bsurgical\b",
        r"\btreatment\b",
        r"\btherapy\b",
        r"\bintervention\b",
        r"\btransplant",
    ):
        return "therapeutic_capability"
    if _has(
        text,
        r"\bavailable\b",
        r"\bprovided\b",
        r"\boffered\b",
        r"\bservices?\b",
        r"\bunit\b",
        r"\bcentre\b",
        r"\bcenter\b",
        r"\bdepartment\b",
        r"\bfacility\b",
    ):
        return "service_offered"
    if _has(text, r"\badministration\b", r"\bregistration\b", r"\binsurance\b"):
        return "administrative"
    if _has(text, r"\bcare\b", r"\bhealth\b", r"\bpatient\b"):
        return "general_marketing"
    return "unclassified"


def _equipment_category(text: str) -> str:
    if _has(text, r"\bwheelchair\b", r"\bramp\b", r"\baccessible\b", r"\blift\b"):
        return "accessibility"
    if _has(
        text,
        r"\bmagnetic resonance imaging\b",
        r"\bmri\b",
        r"\bcomputed tomography\b",
        r"\bct scanner\b",
        r"\bx ray\b",
        r"\bultrasound\b",
        r"\bmammogra",
        r"\bpet scanner\b",
    ):
        return "diagnostic_imaging"
    if _has(
        text,
        r"\bdialysis\b",
        r"\bdialysis machine\b",
        r"\bdialysis equipment\b",
        r"\bdialysis unit\b",
    ):
        return "renal_device"
    if _has(text, r"\bventilator\b", r"\brespirator\b", r"\boxygen concentrator\b"):
        return "respiratory_device"
    if _has(text, r"\bincubator\b", r"\bneonatal\b", r"\bphototherapy\b"):
        return "neonatal_device"
    if _has(text, r"\bmonitor\b", r"\belectrocardiogra", r"\becg\b", r"\bekg\b"):
        return "diagnostic_monitoring"
    if _has(text, r"\banaly[sz]er\b", r"\blaboratory\b", r"\bpathology\b"):
        return "laboratory_device"
    if _has(text, r"\bicu\b", r"\bdefibrillator\b", r"\banaesthesia\b", r"\banesthesia\b"):
        return "critical_care_device"
    if _has(
        text,
        r"\blaser\b",
        r"\blithotripter\b",
        r"\bendoscope\b",
        r"\bcath lab\b",
        r"\brf machine\b",
        r"\bradiotherapy\b",
    ):
        return "therapeutic_device"
    if _has(text, r"\bbed\b", r"\bstretcher\b", r"\bfurniture\b", r"\bpower backup\b"):
        return "support_device"
    return "unclassified"


def evidence_role(source_field: str, category: str) -> str:
    if source_field == PROCEDURE_FIELD and category != "unclassified":
        return "direct_procedure"
    if source_field == CAPABILITY_FIELD:
        if category in {
            "service_offered",
            "critical_care",
            "emergency_availability",
            "diagnostic_capability",
            "therapeutic_capability",
        }:
            return "direct_capability"
        return "context_only" if category != "unclassified" else "unknown"
    if source_field == EQUIPMENT_FIELD:
        if category == "diagnostic_imaging":
            return "defines_service"
        if category in {"accessibility", "irrelevant_or_ambiguous"}:
            return "context_only"
        if category != "unclassified":
            return "supports_service"
        return "unknown"
    if source_field == SPECIALTY_FIELD:
        return "specialty_hint"
    return "unknown"


def weak_label(source_field: str, value: str) -> WeakLabel:
    normalized = normalize_text(value)
    if not normalized:
        return WeakLabel("unclassified", "unknown", 0.0, "empty")
    if NEGATION_RE.search(normalized):
        return WeakLabel("unclassified", "negative", 0.95, "negation")

    if source_field == PROCEDURE_FIELD:
        category = _procedure_category(normalized)
    elif source_field == CAPABILITY_FIELD:
        category = _capability_category(normalized)
    elif source_field == EQUIPMENT_FIELD:
        category = _equipment_category(normalized)
    elif source_field == SPECIALTY_FIELD:
        category = "specialty"
    else:
        category = "unclassified"

    confidence = 0.9 if category != "unclassified" else 0.0
    method = "rule" if category != "unclassified" else "unclassified"
    return WeakLabel(category, evidence_role(source_field, category), confidence, method)
