"""Load ranker inputs from the tag pipeline outputs and the facility table.

Inputs (all produced elsewhere in the repo):
  data/tags/service_tags.json      service/condition tag catalog (committed)
  data/tags/specialty_tags.json    specialty catalog + raw spelling variants (committed)
  data/tags/facility_tag_scores.csv  TF-IDF class per (facility, tag)  (gitignored, tfidf_classify.py)
  data/tags/facility_tags.csv        regex evidence refs per (facility, tag) (gitignored, build_tags.py)
  model_facilities                   from Databricks, or a cached CSV/TSV export of it

Each loader accepts whatever subset of columns exists, so a re-run of the
pipeline that adds columns, or a partially cleaned table, still loads.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Callable, Protocol

from .features import (
    FACILITY_COLUMNS, EvidenceIndex, FacilityRecord, SchemaReport, TagEvidence, TagInfo,
    check_schema, facility_from_row, to_float, to_int,
)

csv.field_size_limit(sys.maxsize)

REPO_ROOT = Path(__file__).resolve().parents[3]
TAGS_DIR = REPO_ROOT / "data" / "tags"
FACILITIES_TABLE = "workspace.cardinal_virtues.model_facilities"


class SQLClient(Protocol):
    def query(self, statement: str) -> tuple[list[str], list[list]]: ...


# ── tag catalog ──────────────────────────────────────────────────────────

def load_tag_catalog(tags_dir: Path = TAGS_DIR) -> list[TagInfo]:
    out: list[TagInfo] = []
    service = json.loads((tags_dir / "service_tags.json").read_text())
    for t in service["tags"]:
        out.append(TagInfo(id=t["id"], label=t["label"], group=t.get("group"), kind=t.get("kind"),
                           synonyms=tuple(t.get("synonyms", ()))))
    spec_path = tags_dir / "specialty_tags.json"
    if spec_path.exists():
        for t in json.loads(spec_path.read_text())["tags"]:
            out.append(TagInfo(id=t["id"], label=t["label"], kind="specialty", is_specialty=True))
    return out


def load_specialty_normalizer(tags_dir: Path = TAGS_DIR) -> Callable[[str], str]:
    """Raw ``specialties_std`` value → canonical specialty code (``ENT`` → ``otolaryngology``).

    Uses the pipeline's own ``specialty_key`` (spelling, case and alias rules) so a
    facility's specialties normalize exactly as the catalog was built, including raw
    spellings that first appear in a later data refresh. Values with no catalog
    entry are returned unchanged.
    """
    sys.path.insert(0, str(REPO_ROOT / "pipeline"))
    from build_tags import specialty_key  # noqa: PLC0415

    by_key: dict[str, str] = {}
    path = tags_dir / "specialty_tags.json"
    if path.exists():
        for t in json.loads(path.read_text())["tags"]:
            for v in [t["code"], *t.get("variants", ())]:
                by_key[specialty_key(v)] = t["code"]

    def normalize(raw: str) -> str:
        return by_key.get(specialty_key(raw), raw)

    return normalize


# ── evidence ─────────────────────────────────────────────────────────────

def load_evidence_index(scores_csv: Path = TAGS_DIR / "facility_tag_scores.csv",
                        refs_csv: Path | None = TAGS_DIR / "facility_tags.csv") -> EvidenceIndex:
    """Join TF-IDF classes with regex evidence refs into one index.

    ``facility_tag_scores.csv`` is required. ``facility_tags.csv`` is optional; it adds
    the list of fields each hit came from (used for multi-field corroboration).
    """
    refs: dict[tuple[str, str], tuple[str, ...]] = {}
    if refs_csv is not None and Path(refs_csv).exists():
        with open(refs_csv, newline="") as f:
            for row in csv.DictReader(f):
                if row.get("tag_type") == "specialty":
                    continue
                r = tuple(x for x in (row.get("evidence_refs") or "").split(";") if x)
                refs[(row["unique_id"], row["tag_id"])] = r

    index: EvidenceIndex = {}
    with open(scores_csv, newline="") as f:
        for row in csv.DictReader(f):
            key = (row["unique_id"], row["tag_id"])
            pair_refs = refs.get(key, ())
            best_ref = (row.get("best_evidence_ref") or "").strip()
            if best_ref and best_ref not in pair_refs:
                pair_refs = (best_ref, *pair_refs)
            fields = frozenset(r.split(":", 1)[0] for r in pair_refs if ":" in r)
            index[key] = TagEvidence(
                unique_id=key[0], tag_id=key[1],
                tag_class=(row.get("class") or "mention").strip().lower(),
                best_probability=to_float(row.get("best_probability")),
                sentence_count=to_int(row.get("regex_sentence_count")) or len(pair_refs) or 1,
                fields=fields, evidence_refs=pair_refs,
                negated_count=to_int(row.get("negated_sentence_count")) or 0,
            )
    return index


# ── facilities ───────────────────────────────────────────────────────────

def load_facilities_file(path: Path, normalize_specialty: Callable[[str], str] | None = None
                         ) -> tuple[list[FacilityRecord], SchemaReport]:
    """CSV or TSV export of model_facilities (delimiter detected from the extension)."""
    delimiter = "\t" if Path(path).suffix.lower() in (".tsv", ".tab") else ","
    with open(path, newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        report = check_schema(reader.fieldnames or [])
        if not report.ok:
            raise ValueError(f"{path}: missing required columns {report.missing_required}")
        return [facility_from_row(r, normalize_specialty) for r in reader if r.get("unique_id")], report


def load_facilities_sql(db: SQLClient, table: str = FACILITIES_TABLE,
                        normalize_specialty: Callable[[str], str] | None = None,
                        cache_path: Path | None = None) -> tuple[list[FacilityRecord], SchemaReport]:
    """Select only the columns the ranker uses that the table currently has.

    With ``cache_path`` the raw rows are also written as TSV, readable later by
    ``load_facilities_file`` without querying Databricks.
    """
    cols, _ = db.query(f"SELECT * FROM {table} LIMIT 0")
    report = check_schema(cols)
    if not report.ok:
        raise ValueError(f"{table}: missing required columns {report.missing_required}")
    present = set(cols)
    wanted = [c for c in FACILITY_COLUMNS if c in present]
    select = ", ".join(f"to_json({c}) AS {c}" if c == "specialties_std" else c for c in wanted)
    names, rows = db.query(f"SELECT {select} FROM {table}")
    dict_rows = [dict(zip(names, r)) for r in rows]
    if cache_path is not None:
        with open(cache_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=names, delimiter="\t")
            w.writeheader()
            w.writerows(dict_rows)
    return [facility_from_row(r, normalize_specialty) for r in dict_rows], report
