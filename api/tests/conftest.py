from __future__ import annotations

from datetime import date

import pytest

from app.ranking import FacilityRecord, TagEvidence, TagInfo

# Query point used throughout: central Bhubaneswar.
ORIGIN = (20.2961, 85.8245)
AS_OF = date(2026, 11, 21)
KM_PER_DEG_LAT = 111.195


def at_km_north(km: float) -> tuple[float, float]:
    return ORIGIN[0] + km / KM_PER_DEG_LAT, ORIGIN[1]


def facility(uid: str, km: float = 1.0, **kw) -> FacilityRecord:
    lat, lon = at_km_north(km)
    defaults = dict(name=uid, facility_category="hospital", location_confidence="high",
                    official_website=f"https://{uid}.example", n_source_urls=4,
                    page_last_updated=date(2026, 6, 1))
    defaults.update(kw)
    return FacilityRecord(unique_id=uid, latitude=lat, longitude=lon, **defaults)


def evidence(uid: str, tag: str = "kidney-dialysis", cls: str = "strong", prob: float | None = 0.9,
             n: int = 3, fields=("procedure", "equipment"), negated: int = 0) -> TagEvidence:
    return TagEvidence(unique_id=uid, tag_id=tag, tag_class=cls, best_probability=prob,
                       sentence_count=n, fields=frozenset(fields),
                       evidence_refs=tuple(f"{f}:0" for f in fields), negated_count=negated)


TAGS = [
    TagInfo("kidney-dialysis", "Dialysis", group="Kidney & urinary", kind="service"),
    TagInfo("kidney-failure", "Kidney failure", group="Kidney & urinary", kind="condition"),
    TagInfo("root-canal", "Root canal", group="Dental", kind="service"),
    TagInfo("c-section", "C-section", group="Women's health & fertility", kind="service"),
    TagInfo("brand-new-tag", "Added later", group="Some new group", kind="service"),
    TagInfo("specialty:cardiology", "Cardiology", kind="specialty", is_specialty=True),
]


@pytest.fixture
def tags():
    return TAGS
