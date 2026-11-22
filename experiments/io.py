"""Read-only adapters for existing model tables and local CSV/TSV exports."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from .engine import items, validate_point


def table_name(value):
    parts = value.split(".")
    if not parts or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", p) for p in parts):
        raise ValueError("Unsafe table identifier")
    return ".".join(f"`{p}`" for p in parts)


def read_frame(path):
    path = Path(path)
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, sep="\t" if path.suffix == ".tsv" else ",", dtype={"unique_id": str, "pincode": str}, keep_default_na=False)


def load_tables(schema="workspace.cardinal_virtues", spark=None):
    """No writes/cache()/classic-only Spark APIs. SQL API results fetched in small buckets."""
    def query(sql):
        if spark is not None:
            return spark.sql(sql).toPandas()
        from pipeline.databricks_sql import DatabricksSQL
        cols, rows = DatabricksSQL().query(sql)
        return pd.DataFrame(rows, columns=cols)

    facilities = query(f"SELECT * FROM {table_name(schema + '.model_facilities')}")
    evidence = pd.concat([
        query(f"SELECT * FROM {table_name(schema + '.model_evidence_items')} "
              f"WHERE pmod(hash(unique_id), 32) = {b}") for b in range(32)], ignore_index=True)
    # Keep all columns, including upstream attribution/evidence_status where present.
    return facilities, evidence


def augment_facility_text(facilities, evidence):
    """Add description and specialties missing from the evidence table, with traceable refs."""
    additions = []
    present = set(zip(evidence.unique_id.astype(str), evidence.field))
    for row in facilities.to_dict("records"):
        uid = str(row["unique_id"])
        for field, columns in (("description", ("description",)), ("specialty", ("specialties_std", "specialties"))):
            if (uid, field) in present or (field == "specialty" and (uid, "specialties") in present):
                continue
            value = next((row[c] for c in columns if c in row and items(row[c])), None)
            values = items(value)
            for i, text in enumerate(values):
                if isinstance(text, str) and text.strip():
                    additions.append({"unique_id": uid, "field": field, "item_idx": i, "text": text,
                                      "evidence_status": ""})
    return pd.concat([evidence, pd.DataFrame(additions)], ignore_index=True) if additions else evidence.copy()


def resolve_location(text, facilities, pins=None):
    """Exact, unambiguous resolution. Returns a point plus explicit area precision.

    District/PIN centres are query reference points, not patient addresses.
    pins expects pincode, lat, lon, districts, states (existing pincode_reference).
    """
    text = str(text).strip()
    match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*", text)
    if match:
        lat, lon = map(float, match.groups())
        if not validate_point(lat, lon):
            raise ValueError("Invalid location coordinates")
        return {"latitude": lat, "longitude": lon, "precision": "point", "resolved": text}
    if re.fullmatch(r"\d{6}", text):
        if pins is None:
            raise ValueError("PIN resolution requires --pins export of pincode_reference")
        found = pins[pins.pincode.astype(str).str.replace(r"\.0$", "", regex=True).eq(text)]
        if len(found) != 1:
            raise ValueError("PIN must resolve to one audited reference row")
        row = found.iloc[0]
        if len(items(row.get("states"))) != 1 or len(items(row.get("districts"))) != 1:
            raise ValueError("Ambiguous PIN; supply explicit coordinates")
        lat, lon = float(row.lat), float(row.lon)
        if not validate_point(lat, lon):
            raise ValueError("PIN has no valid reference point")
        return {"latitude": lat, "longitude": lon, "precision": "pin_area", "resolved": text}
    parts = [s.strip().casefold() for s in text.split(",")]
    name, state = parts[0], parts[1] if len(parts) == 2 else None
    if len(parts) > 2:
        raise ValueError("Use City/District, State or coordinates")
    for columns, precision in ((("district", "district_key"), "district_area"), (("city_raw", "address_city"), "city_area")):
        mask = pd.Series(False, index=facilities.index)
        for col in columns:
            if col in facilities:
                mask |= facilities[col].fillna("").astype(str).str.strip().str.casefold().eq(name)
        found = facilities[mask].copy()
        state_col = next((c for c in ("state", "state_key", "address_stateOrRegion") if c in found), None)
        if not state_col:
            continue
        found["_state"] = found[state_col].fillna("").astype(str).str.strip().str.casefold()
        if state:
            found = found[found._state.eq(state)]
        if found.empty:
            continue
        if found._state.eq("").any() or found._state.nunique() != 1:
            raise ValueError("Ambiguous place name; specify state or coordinates")
        # Only use upstream checked points; do not let suspect outliers define the city centre.
        if "location_tier" in found:
            found = found[found.location_tier.eq("point_verified")]
        else:
            found = found.iloc[0:0]
        for a, b in (("loc_lat", "loc_lon"), ("best_lat", "best_lon")):
            if a in found and b in found:
                valid = found.apply(lambda r: validate_point(r[a], r[b]), axis=1)
                points = found[valid]
                if len(points):
                    return {"latitude": float(pd.to_numeric(points[a]).median()),
                            "longitude": float(pd.to_numeric(points[b]).median()),
                            "precision": precision, "resolved": text,
                            "note": "Approximate reference centre from upstream-verified facility points"}
    raise ValueError("Place could not be resolved unambiguously; use coordinates or an audited PIN")


def dump_json(path, value):
    def convert(v):
        if hasattr(v, "item"):
            return v.item()
        raise TypeError(f"Cannot serialize {type(v)}")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=convert), encoding="utf-8")
