"""Historical district context, never facility capability or patient-level inference.

No survey estimates are aggregated using household counts. Exact normalized joins or
explicit reviewed name aliases only; boundary changes need an external crosswalk.
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata

import pandas as pd

DEFAULT_NFHS_TABLE = (
    "databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset."
    "nfhs_5_district_health_indicators"
)
DEFAULT_GROUP_INDICATORS = (
    "hh_member_covered_health_insurance_pct", "institutional_birth_5y_pct",
)
SAMPLE_COLUMNS = ("households_surveyed", "women_15_49_interviewed", "men_15_54_interviewed")
CONTEXT_NOTE = (
    "NFHS-5 (2019–2021): historical district survey estimates, not this patient's "
    "condition, hospital quality, current demand or availability. District context "
    "does not affect eligibility, scores, radius or order."
)


def name_key(value):
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    if text in {"null", "none", "nan"}:
        return ""
    return re.sub(r"[\W_]+", " ", text).strip()


def parse_value(raw, percentage=False, sample_count=False):
    """Keep raw + marker status; suppressed/invalid values never become zero."""
    text = "" if raw is None or pd.isna(raw) else str(raw).strip()
    result = {"raw": text, "value": None, "status": "missing"}
    if not text or text.casefold() in {"null", "none", "nan", "na", "n/a", "-"}:
        return result
    if re.fullmatch(r"\*+", text):
        return {**result, "status": "suppressed"}
    low_sample = text.startswith("(") and text.endswith(")")
    number = text[1:-1].strip() if low_sample else text
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", number):
        return {**result, "status": "invalid"}
    value = float(number)
    if (not math.isfinite(value) or value < 0 or (percentage and value > 100)
            or (sample_count and not value.is_integer())):
        return {**result, "status": "out_of_range"}
    return {**result, "value": value, "status": "low_sample" if low_sample else "valid"}


def first_name(row, columns):
    return next((row[c] for c in columns if c in row and name_key(row[c])), "")


class DistrictContext:
    def __init__(self, nfhs, aliases=None, group_indicators=None, group_bins=None):
        required = {"district_name", "state_ut"}
        if not required.issubset(nfhs):
            raise ValueError("NFHS needs district_name and state_ut")
        if nfhs.empty:
            raise ValueError("NFHS table must contain at least one district")
        self.frame = nfhs.copy().reset_index(drop=True)
        self.frame["state_key"] = self.frame.state_ut.map(name_key)
        self.frame["district_key"] = self.frame.district_name.map(name_key)
        if (self.frame.state_key.eq("") | self.frame.district_key.eq("")).any():
            raise ValueError("NFHS has missing district/state keys")
        if self.frame.duplicated(["state_key", "district_key"]).any():
            raise ValueError("Duplicate normalized NFHS district/state keys; resolve before joining")
        self.indicators = sorted(c for c in nfhs if c.endswith("_pct"))
        self.other_numeric = [c for c in nfhs if c.startswith("sex_ratio_")]
        self.metrics = self.indicators + self.other_numeric
        self.aliases = {}
        if aliases is not None:
            columns = {"source_state", "source_district", "target_state", "target_district", "mapping_type"}
            if not columns.issubset(aliases):
                raise ValueError("Alias export needs " + ", ".join(sorted(columns)))
            for row in aliases.to_dict("records"):
                source = (name_key(row["source_state"]), name_key(row["source_district"]))
                target = (name_key(row["target_state"]), name_key(row["target_district"]))
                if not all(source) or not all(target) or source in self.aliases:
                    raise ValueError("Alias keys must be complete and unique; no ambiguous many-target mapping")
                mapping_type = str(row["mapping_type"]).strip()
                if mapping_type not in {"name_alias", "boundary_change", "unresolved"}:
                    raise ValueError("Unknown alias mapping_type")
                self.aliases[source] = (target, mapping_type)
        self.rows = {}
        self.long_rows = []
        for row in self.frame.to_dict("records"):
            key = (row["state_key"], row["district_key"])
            record = {"state": str(row["state_ut"]).strip(), "district": str(row["district_name"]).strip(),
                      "state_key": key[0], "district_key": key[1], "survey_period": "2019–2021",
                      "indicators": {}, "sample_metadata": {}}
            for col in self.metrics + [c for c in SAMPLE_COLUMNS if c in nfhs]:
                parsed = parse_value(row[col], percentage=col in self.indicators, sample_count=col in SAMPLE_COLUMNS)
                parsed["unit"] = "percent" if col in self.indicators else "count" if col in SAMPLE_COLUMNS else "ratio"
                record["sample_metadata" if col in SAMPLE_COLUMNS else "indicators"][col] = parsed
                self.long_rows.append({"state_key": key[0], "district_key": key[1], "indicator": col, **parsed})
            self.rows[key] = record
        groups = list(group_indicators) if group_indicators is not None else [c for c in DEFAULT_GROUP_INDICATORS if c in self.metrics]
        if len(set(groups)) != len(groups) or not set(groups).issubset(self.metrics):
            raise ValueError("Group indicators must be distinct NFHS indicator columns")
        self.group_bins = {}
        configured = group_bins or {}
        if not set(configured).issubset(groups):
            raise ValueError("Configured bins must refer to selected group indicators")
        for col in groups:
            values = [r["indicators"][col]["value"] for r in self.rows.values()
                      if r["indicators"][col]["status"] == "valid"]
            cuts = configured.get(col)
            if cuts is None:
                cuts = pd.Series(values, dtype=float).quantile([1/3, 2/3]).tolist() if values else None
            if cuts is not None:
                if not isinstance(cuts, (list, tuple)) or len(cuts) != 2:
                    raise ValueError("Each group bin needs two finite ordered cut points")
                cuts = [float(v) for v in cuts]
                if not all(math.isfinite(v) for v in cuts) or cuts[0] > cuts[1]:
                    raise ValueError("Each group bin needs two finite ordered cut points")
            self.group_bins[col] = cuts
        fingerprint = self.frame.to_json() + (aliases.to_json() if aliases is not None else "")
        self.fingerprint = hashlib.sha256(fingerprint.encode()).hexdigest()

    def lookup(self, state, district):
        source = (name_key(state), name_key(district))
        match = {"input_state_key": source[0], "input_district_key": source[1], "match_status": "missing_key"}
        if not all(source):
            return match
        # Reviewed crosswalk takes precedence, including an explicit boundary-change block.
        if source in self.aliases:
            target, kind = self.aliases[source]
            if kind != "name_alias":
                return {**match, "match_status": "boundary_review" if kind == "boundary_change" else "unresolved_alias"}
            status = "alias"
        else:
            target, status = source, "exact"
        if target not in self.rows:
            return {**match, "match_status": "unmatched_alias" if status == "alias" else "unmatched"}
        return {**match, "match_status": status, **self.rows[target]}

    def query_context(self, query, service_id):
        # Never infer the patient's district from the nearest recommended hospital.
        record = self.lookup(query.get("context_state"), query.get("context_district"))
        maternal = service_id in {"c-section", "emergency-c-section", "nicu"}
        selected = []
        for col, parsed in record.get("indicators", {}).items():
            if col not in self.indicators:
                continue
            relevant = col == "hh_member_covered_health_insurance_pct"
            relevant |= maternal and any(s in col for s in ("birth", "delivery", "delivered", "anc_", "pnc_", "antenatal", "postnatal"))
            if relevant:
                selected.append({"indicator": col, **parsed})
        return {**record, "display_indicators": selected, "note": CONTEXT_NOTE,
                "assignment_source": query.get("context_assignment_source", "explicit_query_metadata"),
                "groups": {col: self.group(record, col) for col in self.group_bins}}

    def group(self, record, col):
        metric = record.get("indicators", {}).get(col)
        if metric is None:
            return "unmatched_context"
        if metric["status"] != "valid":
            return metric["status"]
        cuts = self.group_bins[col]
        if cuts is None:
            return "no_reference_values"
        return "lower" if metric["value"] <= cuts[0] else "middle" if metric["value"] <= cuts[1] else "upper"

    def join_facilities(self, facilities):
        rows = []
        for row in facilities.to_dict("records"):
            match = self.lookup(first_name(row, ("state_key", "state", "address_stateOrRegion")),
                                first_name(row, ("district_key", "district")))
            rows.append({"unique_id": str(row["unique_id"]), **{k: v for k, v in match.items()
                         if k not in {"indicators", "sample_metadata", "survey_period"}}})
        return pd.DataFrame(rows)

    def manifest(self):
        return {"fingerprint": self.fingerprint, "districts": len(self.rows), "survey_period": "2019–2021",
                "group_bins": self.group_bins, "default_bin_reference": "valid rows in supplied NFHS table; equal-weight district tertiles",
                "bin_rule": "lower <= cut1; middle <= cut2; upper > cut2; low_sample kept separate",
                "note": CONTEXT_NOTE, "household_counts_used_as_weights": False}


def subgroup_metrics(per_query):
    """Macro query summaries with counts; no accuracy invented for unjudged queries."""
    rows = []
    metrics = ("answered", "no_answer", "precision_at_k", "ndcg_at_k_pool", "candidate_recall_pool",
               "false_abstention", "judged_result_fraction", "top1_distance_km", "mean_distance_km",
               "nearby_dataset_facility_count")
    for group_col in (c for c in per_query if c.startswith("nfhs_group__")):
        indicator = group_col.removeprefix("nfhs_group__")
        keys = ["method", "service_id", "density_group", group_col]
        for key, frame in per_query.groupby(keys, dropna=False):
            result = dict(zip(keys, key))
            result["nfhs_group"] = result.pop(group_col)
            result.update(indicator=indicator, query_count=len(frame),
                          district_count=frame["nfhs_district_id"].nunique())
            for metric in metrics:
                result[metric] = frame[metric].mean()
                result[metric + "_n"] = int(frame[metric].count())
            rows.append(result)
    return pd.DataFrame(rows)


def context_plots(per_query, out):
    """Descriptive query means and effective sample counts; not survey estimates."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from pathlib import Path

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for i, group_col in enumerate(c for c in per_query if c.startswith("nfhs_group__")):
        fig, axes = plt.subplots(1, 3, figsize=(18, 5))
        for ax, metric in zip(axes, ("no_answer", "precision_at_k", "top1_distance_km")):
            grouped = per_query.groupby([group_col, "method"])[metric]
            means = grouped.mean().unstack("method")
            counts = grouped.count().unstack("method")
            if means.notna().any().any():
                means.plot.bar(ax=ax)
                for j, container in enumerate(ax.containers):
                    method = means.columns[j]
                    ax.bar_label(container, labels=[f"n={int(n)}" if n else "" for n in counts[method]], fontsize=7)
            else:
                ax.text(.5, .5, "Needs independently judged qrels", ha="center", transform=ax.transAxes)
            ax.set_title(metric + " (macro query mean)")
            ax.set_xlabel("NFHS indicator group")
            if metric != "top1_distance_km":
                ax.set_ylim(0, 1.15)
            ax.tick_params(axis="x", rotation=40)
        fig.suptitle(group_col.removeprefix("nfhs_group__") + " — descriptive; compare service/density strata in CSV")
        fig.tight_layout()
        fig.savefig(out / f"nfhs_groups_{i:02d}.png", dpi=150)
        plt.close(fig)


def service_coverage(context, facility_matches, runs):
    """Dataset evidence counts, NOT population-normalized supply or live capacity."""
    rows = []
    for service in sorted({run["service_id"] for run in runs}):
        audit = next(run["audit"] for run in runs if run["service_id"] == service)
        supported = {r["unique_id"] for r in audit if any(e["status"] == "text_supported" for e in r["evidence"])
                     and "service_evidence_conflict" not in r["reasons"]}
        usable = {r["unique_id"] for r in audit if not (set(r["reasons"]) - {"outside_radius"})}
        for key, district in context.rows.items():
            matched = facility_matches[facility_matches.get("state_key", pd.Series(index=facility_matches.index, dtype=str)).eq(key[0]) &
                                       facility_matches.get("district_key", pd.Series(index=facility_matches.index, dtype=str)).eq(key[1])]
            ids = set(matched.unique_id)
            rows.append({"state_key": key[0], "district_key": key[1], "service_id": service,
                         "dataset_facility_count": len(ids), "service_text_supported_count": len(ids & supported),
                         "service_location_usable_count": len(ids & usable),
                         "interpretation": "Counts in supplied dataset, not total providers, capacity or unmet demand"})
    return pd.DataFrame(rows)


def context_geojson(runs):
    """Query reference points only. NFHS does not supply district polygons."""
    features = []
    seen = set()
    for run in runs:
        if run["query_id"] in seen or "district_context" not in run:
            continue
        seen.add(run["query_id"])
        q, context = run["query"], run["district_context"]
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [q["longitude"], q["latitude"]]},
                         "properties": {"query_id": run["query_id"], "reference_type": "query_reference_not_district_boundary",
                                        **context}})
    return {"type": "FeatureCollection", "features": features}
