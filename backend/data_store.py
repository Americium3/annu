"""Loads the serving tables from Databricks once (or from the local snapshot) and keeps them in memory."""
from __future__ import annotations

import json
import pickle
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

import config

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))


@dataclass
class Snapshot:
    tags: pd.DataFrame
    index: pd.DataFrame
    facilities: pd.DataFrame
    pins: pd.DataFrame
    loaded_at: str
    source: str


def _frame(cols, rows, numeric=(), boolean=(), json_cols=()):
    df = pd.DataFrame(rows, columns=cols)
    for c in numeric:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in boolean:
        df[c] = df[c].map({"true": True, "false": False, True: True, False: False}).fillna(False).astype(bool)
    for c in json_cols:
        df[c] = df[c].map(lambda v: json.loads(v) if isinstance(v, str) and v else [])
    return df


def load_from_databricks() -> Snapshot:
    from databricks_sql import DatabricksSQL  # pipeline/databricks_sql.py (stdlib client)

    db = DatabricksSQL()
    t0 = time.time()
    tags = _frame(*db.query(f"SELECT tag_id, label, kind, group_name, to_json(synonyms) AS synonyms, facility_count "
                            f"FROM {config.TABLE_TAGS}"), numeric=["facility_count"], json_cols=["synonyms"])
    parts = []
    for b in range(8):   # keep each INLINE result well under 25 MiB
        cols, rows = db.query(
            "SELECT unique_id, tag_id, eligibility, to_json(reason_codes) AS reason_codes, evidence_tier, "
            "n_explicit_usable, n_explicit_elsewhere, n_time_bound, n_equipment_usable, n_explicit_fields, n_cited, "
            f"only_equipment, lists_emergency_24x7, evidence_json FROM {config.TABLE_INDEX} "
            f"WHERE pmod(hash(unique_id), 8) = {b}")
        parts.append(_frame(cols, rows,
                            numeric=["evidence_tier", "n_explicit_usable", "n_explicit_elsewhere", "n_time_bound",
                                     "n_equipment_usable", "n_explicit_fields", "n_cited"],
                            boolean=["only_equipment", "lists_emergency_24x7"],
                            json_cols=["reason_codes", "evidence_json"]))
    index = pd.concat(parts, ignore_index=True).rename(columns={"evidence_json": "evidence"})
    facilities = _frame(*db.query(
        "SELECT unique_id, name, facility_category, operator_category, city_raw, district, state, pincode, address_city, "
        "location_tier, loc_lat, loc_lon, latitude, longitude, location_source, location_confidence, location_check, "
        "coord_to_pin_km, core_identity_conflict, contact_phone, contact_website, to_json(source_urls_clean) AS source_urls, "
        "recency_of_page_update, capability_maybe_truncated, procedure_maybe_truncated, same_name_city_records, n_beds, "
        f"n_doctors, year_est, n_source_urls, flag_shared_point FROM {config.TABLE_FACILITIES}"),
        numeric=["loc_lat", "loc_lon", "latitude", "longitude", "coord_to_pin_km", "same_name_city_records", "n_beds",
                 "n_doctors", "year_est", "n_source_urls"],
        boolean=["core_identity_conflict", "capability_maybe_truncated", "procedure_maybe_truncated", "flag_shared_point"],
        json_cols=["source_urls"])
    pins = _frame(*db.query(f"SELECT pincode, to_json(states) AS states, to_json(districts) AS districts, lat, lon, "
                            f"is_precise FROM {config.TABLE_PINS}"),
                  numeric=["lat", "lon"], boolean=["is_precise"], json_cols=["states", "districts"])
    print(f"loaded from Databricks in {time.time() - t0:.1f}s: {len(index)} facility×service rows, "
          f"{len(facilities)} facilities, {len(pins)} PINs", file=sys.stderr)
    return Snapshot(tags, index, facilities, pins, pd.Timestamp.now("UTC").isoformat(timespec="seconds"), "databricks")


def get_snapshot(refresh: bool = False) -> Snapshot:
    """Databricks on first run (or refresh=True), then the local pickle so restarts are instant and offline."""
    if not refresh and config.CACHE_FILE.exists():
        with open(config.CACHE_FILE, "rb") as f:
            snap = pickle.load(f)
        snap.source = f"cache ({config.CACHE_FILE.name}, loaded from Databricks at {snap.loaded_at})"
        return snap
    snap = load_from_databricks()
    config.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(config.CACHE_FILE, "wb") as f:
        pickle.dump(snap, f)
    return snap


def haversine_km(lat0: float, lon0: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    p1, p2 = np.radians(lat0), np.radians(lats)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lons - lon0) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))
