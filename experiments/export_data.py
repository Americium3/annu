"""Export everything the experiments need from Databricks into experiments/data/ (git-ignored).

Only the golden_eval DEV split is exported: the test split must not be looked at or tuned on.

  export DATABRICKS_HOST=... DATABRICKS_WAREHOUSE_ID=... DATABRICKS_TOKEN=...
  python experiments/export_data.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "pipeline"))
from databricks_sql import DatabricksSQL  # noqa: E402

OUT = ROOT / "data"
S = "workspace.cardinal_virtues"


def frame(db, sql):
    cols, rows = db.query(sql)
    return pd.DataFrame(rows, columns=cols)


def main():
    OUT.mkdir(exist_ok=True)
    db = DatabricksSQL()
    # facility text: one row per (facility, field) with the sentence list as JSON (sentence-level citations kept)
    parts = [frame(db, f"""SELECT unique_id, field, to_json(collect_list(struct(item_idx, text))) items
                           FROM {S}.model_evidence_items WHERE pmod(hash(unique_id), 8) = {b} GROUP BY unique_id, field""")
             for b in range(8)]
    pd.concat(parts).to_parquet(OUT / "evidence.parquet")
    frame(db, f"""SELECT f.unique_id, f.name, f.facility_category, f.operator_category, f.city_raw, f.district, f.state,
                    f.pincode, f.best_lat, f.best_lon, f.location_source, f.location_confidence, f.flag_coord_pin_conflict,
                    f.flag_pin_imprecise, f.flag_shared_point, f.n_beds, f.n_doctors, f.official_phone, f.official_website,
                    to_json(f.source_urls) source_urls, f.page_last_updated,
                    t.location_trust_tier, t.use_lat, t.use_lon, t.osm_verdict
                  FROM {S}.model_facilities f LEFT JOIN {S}.location_trust t USING (unique_id)""").to_parquet(OUT / "facilities.parquet")
    frame(db, f"SELECT pincode, to_json(states) states, to_json(districts) districts, lat, lon, is_precise FROM {S}.pincode_reference"
          ).to_parquet(OUT / "pins.parquet")
    frame(db, f"SELECT tag_id, label, kind, group_name, to_json(synonyms) synonyms, facility_count FROM {S}.ref_service_tags"
          ).to_parquet(OUT / "tags.parquet")
    frame(db, f"SELECT kind, variant, standard FROM {S}.ref_address_alias").to_parquet(OUT / "address_alias.parquet")
    frame(db, "SELECT * FROM workspace.golden_eval.queries_dev").to_parquet(OUT / "queries_dev.parquet")
    frame(db, "SELECT query_id, unique_id, name, distance_km, evidence_grade, expected_action, gain, in_ideal_top3 "
              "FROM workspace.golden_eval.judgments_dev").to_parquet(OUT / "judgments_dev.parquet")
    for p in sorted(OUT.glob("*.parquet")):
        print(f"{p.name:24} {len(pd.read_parquet(p)):>8} rows")


if __name__ == "__main__":
    main()
