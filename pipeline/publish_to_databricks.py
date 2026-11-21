"""Publish the tag catalog to the Databricks workspace as Unity Catalog tables.

Uploads the generated files to the volume ``workspace.cardinal_virtues.tag_files`` and
(re)creates two Delta tables next to the cleaned facility tables:

  workspace.cardinal_virtues.tag_catalog     one row per tag (service, condition, specialty)
                                             with facility counts, TF-IDF evidence counts and
                                             MeSH / ICD-10 / NUCC references
  workspace.cardinal_virtues.facility_tags   one row per (facility, tag): evidence class
                                             (strong / mention / suggested / specialty),
                                             TF-IDF probability and evidence refs into
                                             model_evidence_items (field:item_idx)

Run after build_tags.py, tfidf_classify.py and crosswalk_taxonomies.py.

Usage:
  export DATABRICKS_HOST=... DATABRICKS_WAREHOUSE_ID=... [DATABRICKS_TOKEN=...]
  python3 pipeline/publish_to_databricks.py
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_tags import REPO_ROOT, SCHEMA  # noqa: E402
from databricks_sql import DatabricksSQL  # noqa: E402

VOLUME = "tag_files"
VOLUME_PATH = f"/Volumes/{SCHEMA.replace('.', '/')}/{VOLUME}"


def build_catalog_rows(tags_dir: Path) -> list[dict]:
    service = json.loads((tags_dir / "service_tags.json").read_text())["tags"]
    specialty = json.loads((tags_dir / "specialty_tags.json").read_text())["tags"]
    crosswalk = json.loads((tags_dir / "taxonomy_crosswalk.json").read_text())
    tfidf = {t["id"]: t for t in json.loads((tags_dir / "tfidf_tag_report.json").read_text())["tags"]}
    xs = {s["id"]: s for s in crosswalk["serviceTags"]}
    xsp = {s["id"]: s for s in crosswalk["specialtyTags"]}

    rows = []
    for t in service:
        x, f = xs[t["id"]], tfidf.get(t["id"], {}).get("facilities", {})
        rows.append({
            "tag_id": t["id"], "label": t["label"], "tag_type": t["kind"], "group_name": t["group"],
            "synonyms": t["synonyms"], "facility_count": t["facilityCount"],
            "strong_facility_count": f.get("strong"), "mention_facility_count": f.get("mention"),
            "suggested_facility_count": f.get("suggested"),
            "mesh_ids": [m["id"] for m in x["mesh"]], "mesh_labels": [m["label"] for m in x["mesh"]],
            "mesh_categories": sorted({c for m in x["mesh"] for c in m["categories"]}),
            "icd10_codes": [c["code"] for c in x["icd10"]], "icd10_labels": [c["description"] for c in x["icd10"]],
            "nucc_code": None, "nucc_display_name": None, "nucc_relation": None,
            "example_evidence": t["exampleEvidence"], "raw_variants": [],
        })
    for t in specialty:
        n = xsp[t["id"]]["nucc"]
        rows.append({
            "tag_id": t["id"], "label": t["label"], "tag_type": "specialty", "group_name": None,
            "synonyms": [], "facility_count": t["facilityCount"],
            "strong_facility_count": None, "mention_facility_count": None, "suggested_facility_count": None,
            "mesh_ids": [], "mesh_labels": [], "mesh_categories": [], "icd10_codes": [], "icd10_labels": [],
            "nucc_code": n["code"] if n else None, "nucc_display_name": n["displayName"] if n else None,
            "nucc_relation": n["relation"] if n else None,
            "example_evidence": [], "raw_variants": t["variants"],
        })
    return rows


CATALOG_SCHEMA = (
    "tag_id STRING, label STRING, tag_type STRING, group_name STRING, synonyms ARRAY<STRING>, "
    "facility_count INT, strong_facility_count INT, mention_facility_count INT, suggested_facility_count INT, "
    "mesh_ids ARRAY<STRING>, mesh_labels ARRAY<STRING>, mesh_categories ARRAY<STRING>, "
    "icd10_codes ARRAY<STRING>, icd10_labels ARRAY<STRING>, nucc_code STRING, nucc_display_name STRING, "
    "nucc_relation STRING, example_evidence ARRAY<STRING>, raw_variants ARRAY<STRING>"
)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tags-dir", default=str(REPO_ROOT / "data" / "tags"))
    args = ap.parse_args()
    tags_dir = Path(args.tags_dir)
    db = DatabricksSQL()

    with tempfile.TemporaryDirectory() as tmp:
        catalog = Path(tmp) / "tag_catalog.jsonl"
        catalog.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in build_catalog_rows(tags_dir)))
        uploads = {
            "tag_catalog.jsonl": catalog,
            "facility_tags.csv": tags_dir / "facility_tags.csv",
            "facility_tag_scores.csv": tags_dir / "facility_tag_scores.csv",
        }
        db.query(f"CREATE VOLUME IF NOT EXISTS {SCHEMA}.{VOLUME} "
                 "COMMENT 'Generated tag catalog files (cardinal_virtues pipeline)'")
        for name, path in uploads.items():
            db.put_file(f"{VOLUME_PATH}/{name}", path.read_bytes())
            print(f"uploaded {VOLUME_PATH}/{name} ({path.stat().st_size:,} bytes)", file=sys.stderr)

    db.query(f"""
        CREATE OR REPLACE TABLE {SCHEMA}.tag_catalog
        COMMENT 'Searchable tags: curated services/conditions (from evidence sentences) and normalized specialties, with MeSH, WHO ICD-10 and NUCC references. Built by pipeline/build_tags.py, tfidf_classify.py, crosswalk_taxonomies.py.'
        AS SELECT * FROM read_files('{VOLUME_PATH}/tag_catalog.jsonl', format => 'json', schema => '{CATALOG_SCHEMA}')
    """)
    db.query(f"""
        CREATE OR REPLACE TABLE {SCHEMA}.facility_tags
        COMMENT 'One row per (facility, tag). evidence_class: strong / mention / suggested (TF-IDF graded service tags) or specialty. evidence_refs point into model_evidence_items as field:item_idx.'
        AS
        WITH t AS (
          SELECT * FROM read_files('{VOLUME_PATH}/facility_tags.csv', format => 'csv', header => true,
            schema => 'unique_id STRING, tag_id STRING, tag_type STRING, evidence_refs STRING')
        ), s AS (
          SELECT * FROM read_files('{VOLUME_PATH}/facility_tag_scores.csv', format => 'csv', header => true,
            schema => 'unique_id STRING, tag_id STRING, class STRING, best_probability DOUBLE, best_evidence_ref STRING, regex_sentence_count INT')
        )
        SELECT
          coalesce(t.unique_id, s.unique_id) AS unique_id,
          coalesce(t.tag_id, s.tag_id) AS tag_id,
          coalesce(t.tag_type, c.tag_type) AS tag_type,
          CASE WHEN coalesce(t.tag_type, c.tag_type) = 'specialty' THEN 'specialty' ELSE s.class END AS evidence_class,
          s.best_probability AS tfidf_probability,
          s.best_evidence_ref,
          s.regex_sentence_count,
          t.evidence_refs
        FROM t
        FULL OUTER JOIN s ON t.unique_id = s.unique_id AND t.tag_id = s.tag_id
        LEFT JOIN {SCHEMA}.tag_catalog c ON c.tag_id = coalesce(t.tag_id, s.tag_id)
    """)

    _, rows = db.query(f"""
        SELECT 'tag_catalog', count(*), count(DISTINCT tag_type) FROM {SCHEMA}.tag_catalog
        UNION ALL SELECT 'facility_tags', count(*), count(DISTINCT unique_id) FROM {SCHEMA}.facility_tags
    """)
    for name, n, extra in rows:
        print(f"{SCHEMA}.{name}: {int(n):,} rows ({extra} distinct {'tag types' if name == 'tag_catalog' else 'facilities'})",
              file=sys.stderr)


if __name__ == "__main__":
    main()
