from __future__ import annotations

import re


TAG_ACTION_OVERRIDES = {
    "kidney-transplant": ["MAXO:0010043"],
    "angiography": ["MAXO:0001259"],
    "angioplasty": ["MAXO:0009038"],
    "cardiac-surgery": ["MAXO:0025001"],
    "x-ray": ["MAXO:0000595"],
    "pet-ct": ["MAXO:0000137", "MAXO:0000571"],
    "bone-density": ["MAXO:0020004"],
    "bone-marrow-transplant": ["MAXO:0010030"],
    "physiotherapy": ["MAXO:0000011"],
    "eeg-emg": ["MAXO:0000932"],
    "liver-transplant": ["MAXO:0001175"],
    "dental-implants": ["MAXO:0001534"],
    "dentures": ["MAXO:0001533"],
}

ACTION_ALIAS_OVERRIDES = {
    "MAXO:0000424": (
        "MRI",
        "MRI scan",
        "magnetic resonance imaging",
        "MRI scanner",
        "MRI equipment",
    ),
    "MAXO:0000571": (
        "CT",
        "CT scan",
        "computed tomography",
        "CT scanner",
        "CT equipment",
    ),
    "MAXO:0000601": (
        "dialysis",
        "renal dialysis",
        "dialysis unit",
        "dialysis machine",
    ),
    "MAXO:0000900": (
        "ECG",
        "EKG",
        "electrocardiogram",
        "ECG machine",
    ),
}


EMERGENCY_PATTERNS = (
    r"\bemergency\b",
    r"\btrauma\b",
    r"\bthrombolysis\b",
    r"\bthrombectomy\b",
    r"\bresuscitation\b",
    r"急诊|急救|创伤|卒中|中风|溶栓|取栓",
)

URGENT_PATTERNS = (
    r"\bacute\b",
    r"\burgent\b",
    r"\bintensive care\b",
    r"\bicu\b",
    r"\bnicu\b",
    r"\bcritical care\b",
    r"\bcaesarean\b",
    r"\bcesarean\b",
    r"\bambulance\b",
    r"\bblood bank\b",
    r"重症|急性|紧急",
)

Routine_EMERGENCY_EXCLUSIONS = (
    r"^dialysis$",
    r"^renal dialysis$",
    r"^hemodialysis$",
    r"^peritoneal dialysis$",
)


def infer_service_urgency(
    label: str,
    aliases: list[str] | tuple[str, ...] | None = None,
    contexts: list[str] | tuple[str, ...] | None = None,
    emergency_relevant: bool = False,
) -> str:
    text = " ".join([label or "", *(aliases or [])]).casefold()
    if emergency_relevant:
        return "emergency"
    if any(re.search(pattern, text) for pattern in Routine_EMERGENCY_EXCLUSIONS):
        return "routine"
    if any(re.search(pattern, text) for pattern in EMERGENCY_PATTERNS):
        return "emergency"
    if any(re.search(pattern, text) for pattern in URGENT_PATTERNS):
        return "urgent"
    if contexts and "treatment" in contexts and "diagnostic" not in contexts:
        return "routine"
    return "routine"


def infer_action_service_type(
    contexts: list[str] | tuple[str, ...] | None,
) -> str:
    values = set(contexts or [])
    if "diagnostic" in values and "treatment" in values:
        return "mixed_action_service"
    if "diagnostic" in values:
        return "diagnostic_service"
    if "treatment" in values:
        return "procedure_service"
    return "action_service"
