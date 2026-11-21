"""Typed, tolerant views of the cleaned tables.

The cleaned dataset is still changing: columns may be added, renamed or not yet
filled, and new facilities keep arriving. Everything here therefore parses
defensively. A missing column or an unparseable value becomes ``None`` (or an
empty collection), and the scorer treats ``None`` as "unknown → neutral", never as
"bad". Only ``unique_id`` and coordinates are required to rank a facility.

``check_schema`` reports which expected columns a table is missing, so a data
refresh that drops a column is noticed instead of silently scoring as neutral.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Iterable, Mapping

# Columns of model_facilities the ranker reads. Only REQUIRED ones are needed.
REQUIRED_COLUMNS = ("unique_id", "best_lat", "best_lon")
OPTIONAL_COLUMNS = (
    "name", "cluster_id", "facility_category", "operator_category",
    "display_address", "district", "state", "pincode",
    "location_confidence", "specialties_std", "n_specialties_std",
    "n_beds", "n_doctors", "n_source_urls", "official_website",
    "page_last_updated", "last_social_post",
    "flag_duplicate_record", "flag_coord_pin_conflict", "flag_implausible_scale",
    "flag_address_nothing_agrees", "flag_impossible_beds", "flag_impossible_doctors",
    "flag_suspect_doctor_count",
)
FACILITY_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

EVIDENCE_FIELDS = ("procedure", "capability", "equipment")


@dataclass(frozen=True)
class SchemaReport:
    missing_required: tuple[str, ...]
    missing_optional: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing_required


def check_schema(columns: Iterable[str]) -> SchemaReport:
    present = set(columns)
    return SchemaReport(
        missing_required=tuple(c for c in REQUIRED_COLUMNS if c not in present),
        missing_optional=tuple(c for c in OPTIONAL_COLUMNS if c not in present),
    )


# ── value parsing ────────────────────────────────────────────────────────

def _blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip().lower() in ("", "null", "none", "nan"))


def to_str(v: Any) -> str | None:
    return None if _blank(v) else str(v).strip()


def to_float(v: Any) -> float | None:
    if _blank(v):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN → None


def to_int(v: Any) -> int | None:
    f = to_float(v)
    return None if f is None else int(f)


def to_bool(v: Any) -> bool:
    """Flags: anything that isn't clearly true is false (an absent flag means "not raised")."""
    if isinstance(v, bool):
        return v
    if _blank(v):
        return False
    return str(v).strip().lower() in ("true", "t", "1", "yes", "y")


def to_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = to_str(v)
    if s is None:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def to_str_list(v: Any) -> tuple[str, ...]:
    """Arrays arrive as Python lists, JSON strings (SQL API / CSV) or nothing."""
    if _blank(v):
        return ()
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("["):
            try:
                v = json.loads(s)
            except json.JSONDecodeError:
                v = s.strip("[]").split(",")
        else:
            v = s.split(",")
    if not isinstance(v, (list, tuple)):
        return ()
    return tuple(x.strip().strip('"') for x in (str(i) for i in v if i is not None) if x.strip())


def _first_not_none(*values):
    return next((v for v in values if v is not None), None)


# ── records ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FacilityRecord:
    unique_id: str
    latitude: float | None
    longitude: float | None
    name: str | None = None
    cluster_id: str | None = None
    facility_category: str | None = None
    operator_category: str | None = None
    address: str | None = None
    district: str | None = None
    state: str | None = None
    pincode: str | None = None
    location_confidence: str | None = None
    specialties: frozenset[str] = frozenset()  # canonical specialty codes
    n_specialties: int | None = None
    n_beds: int | None = None
    n_doctors: int | None = None
    n_source_urls: int | None = None
    official_website: str | None = None
    page_last_updated: date | None = None
    last_social_post: date | None = None
    flags: frozenset[str] = frozenset()  # names of raised flag_* columns, without the prefix

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None


def facility_from_row(row: Mapping[str, Any],
                      normalize_specialty: Callable[[str], str] | None = None) -> FacilityRecord:
    """Build a record from one ``model_facilities`` row (dict). Unknown columns are ignored.

    ``normalize_specialty`` maps a raw ``specialties_std`` value to its canonical code
    (see ``loaders.load_specialty_normalizer``); without it raw codes are kept as-is.
    """
    norm = normalize_specialty or (lambda x: x)
    specialties = frozenset(norm(s) for s in to_str_list(row.get("specialties_std")))
    flags = frozenset(
        k[len("flag_"):] for k, v in row.items() if k.startswith("flag_") and to_bool(v)
    )
    lat, lon = to_float(row.get("best_lat")), to_float(row.get("best_lon"))
    if lat is not None and lon is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
        lat = lon = None
    return FacilityRecord(
        unique_id=str(row["unique_id"]),
        latitude=lat,
        longitude=lon,
        name=to_str(row.get("name")),
        cluster_id=to_str(row.get("cluster_id")),
        facility_category=(to_str(row.get("facility_category")) or "").lower() or None,
        operator_category=to_str(row.get("operator_category")),
        address=to_str(row.get("display_address")),
        district=to_str(row.get("district")),
        state=to_str(row.get("state")),
        pincode=to_str(row.get("pincode")),
        location_confidence=(to_str(row.get("location_confidence")) or "").lower() or None,
        specialties=specialties,
        n_specialties=_first_not_none(to_int(row.get("n_specialties_std")), len(specialties) or None),
        n_beds=to_int(row.get("n_beds")),
        n_doctors=to_int(row.get("n_doctors")),
        n_source_urls=to_int(row.get("n_source_urls")),
        official_website=to_str(row.get("official_website")),
        page_last_updated=to_date(row.get("page_last_updated")),
        last_social_post=to_date(row.get("last_social_post")),
        flags=flags,
    )


@dataclass(frozen=True)
class TagEvidence:
    """What the tag pipeline found for one (facility, service tag) pair.

    ``tag_class`` is the TF-IDF grade from ``facility_tag_scores.csv``: ``strong``,
    ``mention`` or ``suggested``. ``fields`` are the evidence fields the regex hits
    came from (``facility_tags.csv`` evidence refs).
    """
    unique_id: str
    tag_id: str
    tag_class: str
    best_probability: float | None = None
    sentence_count: int = 0
    fields: frozenset[str] = frozenset()
    evidence_refs: tuple[str, ...] = ()  # "field:item_idx" into model_evidence_items
    negated_count: int = 0


# (unique_id, tag_id) → evidence
EvidenceIndex = dict[tuple[str, str], TagEvidence]


@dataclass(frozen=True)
class TagInfo:
    id: str
    label: str
    group: str | None = None
    kind: str | None = None
    is_specialty: bool = False
    synonyms: tuple[str, ...] = field(default_factory=tuple)
