# Databricks notebook source
from __future__ import annotations

import csv
import io
import json
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pyspark.sql import functions as F
from pyspark.sql import types as T


dbutils.widgets.text("output_catalog", "workspace", "Output catalog")
dbutils.widgets.text("output_schema", "cardinal_virtues", "Output schema")
dbutils.widgets.text(
    "canonical_table",
    "workspace.cardinal_virtues.model_tag_canonical_element",
    "Canonical element table",
)
dbutils.widgets.text(
    "model_src_path",
    "/Workspace/Users/kevinzh3@andrew.cmu.edu/carepath_model/src",
    "Workspace path containing carepath_model",
)
dbutils.widgets.text(
    "local_input_dir",
    "/local_disk0/tmp/carepath_model_inputs",
    "Ephemeral ontology input directory",
)

output_catalog = dbutils.widgets.get("output_catalog").strip()
output_schema = dbutils.widgets.get("output_schema").strip()
canonical_table = dbutils.widgets.get("canonical_table").strip()
model_src_path = dbutils.widgets.get("model_src_path").strip()
local_input_dir = Path(dbutils.widgets.get("local_input_dir").strip())
local_input_dir.mkdir(parents=True, exist_ok=True)

try:
    from carepath_model.ontology import parse_obo, read_text, term_aliases
    from carepath_model.service_catalog import ACTION_ALIAS_OVERRIDES
    from carepath_model.taxonomy import normalize_text
except ModuleNotFoundError:
    if model_src_path not in sys.path:
        sys.path.insert(0, model_src_path)
    from carepath_model.ontology import parse_obo, read_text, term_aliases
    from carepath_model.service_catalog import ACTION_ALIAS_OVERRIDES
    from carepath_model.taxonomy import normalize_text


MAXO_COMMIT = "59b5d75a454fdf6dc06e237fdab92c5b928d4bd3"
MAXO_ANNOTATIONS_COMMIT = "42edd966faac5229ce7c35fc3848f2e6b3d45bda"
HPO_RELEASE = "v2026-09-01"
SOURCE_FILES = {
    "maxo.obo": (
        f"https://raw.githubusercontent.com/monarch-initiative/MAxO/{MAXO_COMMIT}/maxo.obo"
    ),
    "maxo_diagnostic_annotations.tsv": (
        "https://raw.githubusercontent.com/monarch-initiative/maxo-annotations/"
        f"{MAXO_ANNOTATIONS_COMMIT}/data/poet/maxo_diagnostic_annotations.tsv"
    ),
    "maxo_annotations.tsv": (
        "https://raw.githubusercontent.com/monarch-initiative/maxo-annotations/"
        f"{MAXO_ANNOTATIONS_COMMIT}/data/maxo-annotations.tsv"
    ),
    "hp.obo": (
        "https://github.com/obophenotype/human-phenotype-ontology/releases/download/"
        f"{HPO_RELEASE}/hp.obo"
    ),
}


def ensure_input(name: str, url: str) -> Path:
    path = local_input_dir / name
    if not path.exists() or path.stat().st_size == 0:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "carepath-model/1.0"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            path.write_bytes(response.read())
    return path


paths = {name: ensure_input(name, url) for name, url in SOURCE_FILES.items()}

maxo_terms = [
    term
    for term in parse_obo(read_text(paths["maxo.obo"]))
    if term.id.startswith("MAXO:")
]
maxo_by_id = {term.id: term for term in maxo_terms if not term.obsolete}

hpo_terms = parse_obo(read_text(paths["hp.obo"]))
hpo_by_id = {term.id: term for term in hpo_terms if not term.obsolete}


def read_tsv(path: Path) -> list[dict[str, str]]:
    lines = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip() and not line.startswith("#"):
                lines.append(line)
    return list(csv.DictReader(io.StringIO("".join(lines)), delimiter="\t"))


diagnostic_rows = read_tsv(paths["maxo_diagnostic_annotations.tsv"])
treatment_rows = read_tsv(paths["maxo_annotations.tsv"])

edge_rows = []
action_stats = defaultdict(
    lambda: {
        "relations": set(),
        "diseases": set(),
        "phenotypes": set(),
        "contexts": set(),
    }
)

for row in diagnostic_rows:
    hpo_id = (row.get("hpo_id") or "").strip()
    action_id = (row.get("maxo_id") or "").strip()
    if not hpo_id or not action_id:
        continue
    relation = (row.get("predicate_id") or "").strip()
    hpo = hpo_by_id.get(hpo_id)
    label = (
        (row.get("hpo_label") or "").strip()
        or (hpo.name if hpo else "")
        or hpo_id
    )
    action_label = (
        (row.get("maxo_label") or "").strip()
        or (
            maxo_by_id[action_id].name
            if action_id in maxo_by_id
            else action_id
        )
    )
    edge_rows.append(
        {
            "source_kind": "phenotype",
            "condition_id": hpo_id,
            "condition_label": label,
            "action_id": action_id,
            "action_label": action_label,
            "relation": relation,
            "source_reference": f"MAxO diagnostic annotations {MAXO_ANNOTATIONS_COMMIT}",
            "evidence_code": "",
        }
    )
    stats = action_stats[action_id]
    stats["relations"].add(relation)
    stats["phenotypes"].add(hpo_id)
    if relation in {
        "is_observable_through",
        "is_prenatally_observable_through",
    }:
        stats["contexts"].add("diagnostic")

for row in treatment_rows:
    disease_id = (row.get("disease_id") or "").strip()
    action_id = (row.get("maxo_id") or "").strip()
    if not disease_id or not action_id:
        continue
    relation = (row.get("relation") or "").strip()
    action_label = (
        (row.get("maxo_name") or "").strip()
        or (
            maxo_by_id[action_id].name
            if action_id in maxo_by_id
            else action_id
        )
    )
    edge_rows.append(
        {
            "source_kind": "disease",
            "condition_id": disease_id,
            "condition_label": (row.get("disease_name") or disease_id).strip(),
            "action_id": action_id,
            "action_label": action_label,
            "relation": relation,
            "source_reference": (row.get("source_id") or "").strip(),
            "evidence_code": (row.get("evidence") or "").strip(),
        }
    )
    stats = action_stats[action_id]
    stats["relations"].add(relation)
    stats["diseases"].add(disease_id)
    if relation in {"treats", "prevents"}:
        stats["contexts"].add("treatment")

EMERGENCY_RE = re.compile(
    r"\b(emergency|critical care|intensive care|resuscitat|trauma|"
    r"thrombol|thrombectomy|dialysis)\b",
    re.IGNORECASE,
)

action_rows = []
alias_rows = []
for term in maxo_terms:
    if term.obsolete:
        continue
    aliases = list(term_aliases(term))
    for alias in ACTION_ALIAS_OVERRIDES.get(term.id, ()):
        if alias not in aliases:
            aliases.append(alias)
    stats = action_stats.get(
        term.id,
        {"relations": set(), "diseases": set(), "phenotypes": set(), "contexts": set()},
    )
    action_rows.append(
        {
            "action_id": term.id,
            "label": term.name or term.id,
            "parents": term.parents,
            "xrefs": term.xrefs,
            "aliases": aliases,
            "contexts": sorted(stats["contexts"]),
            "relations": sorted(stats["relations"]),
            "disease_count": len(stats["diseases"]),
            "phenotype_count": len(stats["phenotypes"]),
            "emergency_relevant": bool(EMERGENCY_RE.search(" ".join(aliases))),
            "source_version": (
                f"MAxO:{MAXO_COMMIT};annotations:{MAXO_ANNOTATIONS_COMMIT};"
                f"HPO:{HPO_RELEASE}"
            ),
        }
    )
    for alias in aliases:
        alias_rows.append(
            {
                "action_id": term.id,
                "action_label": term.name or term.id,
                "alias": alias,
                "normalized_alias": normalize_text(alias),
                "is_primary_label": alias == term.name,
            }
        )

action_schema = """
action_id string,
label string,
parents array<string>,
xrefs array<string>,
aliases array<string>,
contexts array<string>,
relations array<string>,
disease_count int,
phenotype_count int,
emergency_relevant boolean,
source_version string
"""
action_catalog = spark.createDataFrame(action_rows, schema=action_schema)

edge_schema = """
source_kind string,
condition_id string,
condition_label string,
action_id string,
action_label string,
relation string,
source_reference string,
evidence_code string
"""
edges = spark.createDataFrame(edge_rows, schema=edge_schema).dropDuplicates()

alias_schema = """
action_id string,
action_label string,
alias string,
normalized_alias string,
is_primary_label boolean
"""
alias_catalog = (
    spark.createDataFrame(alias_rows, schema=alias_schema)
    .where(F.trim("normalized_alias") != "")
    .dropDuplicates(["action_id", "normalized_alias"])
)

ACTION_TABLE = f"{output_catalog}.{output_schema}.model_action_catalog"
EDGE_TABLE = f"{output_catalog}.{output_schema}.model_condition_action_edge"
ALIAS_TABLE = f"{output_catalog}.{output_schema}.model_action_alias"
ACTION_MATCH_TABLE = f"{output_catalog}.{output_schema}.model_facility_action_match"

for table, frame in (
    (ACTION_TABLE, action_catalog),
    (EDGE_TABLE, edges),
    (ALIAS_TABLE, alias_catalog),
):
    (
        frame.write.mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(table)
    )

canonical = spark.table(canonical_table)
eligible = canonical.where(
    F.col("evidence_role").isin(
        "direct_procedure",
        "direct_capability",
        "defines_service",
        "supports_service",
    )
)

exact_matches = (
    eligible.alias("e")
    .join(
        alias_catalog.alias("a"),
        F.col("e.normalized_value") == F.col("a.normalized_alias"),
        "inner",
    )
    .withColumn(
        "base_strength",
        F.when(F.col("e.evidence_role") == "direct_procedure", F.lit(1.0))
        .when(F.col("e.evidence_role") == "direct_capability", F.lit(0.95))
        .when(F.col("e.evidence_role") == "defines_service", F.lit(0.90))
        .otherwise(F.lit(0.45)),
    )
)

action_matches = (
    exact_matches.groupBy(
        F.col("e.unique_id").alias("unique_id"),
        F.col("a.action_id").alias("action_id"),
        F.col("a.action_label").alias("action_label"),
    )
    .agg(
        F.max("base_strength").alias("match_strength"),
        F.count("*").alias("evidence_count"),
        F.collect_set("e.source_field").alias("source_fields"),
        F.collect_set("e.evidence_role").alias("evidence_roles"),
        F.collect_set("e.raw_value").alias("matched_values"),
        F.max(F.col("e.possibly_truncated").cast("int")).cast("boolean").alias(
            "possibly_truncated"
        ),
    )
    .withColumn(
        "match_type",
        F.when(F.col("match_strength") >= 0.90, F.lit("strong_exact"))
        .when(F.col("match_strength") >= 0.50, F.lit("supporting_exact"))
        .otherwise(F.lit("context_exact")),
    )
    .withColumn("source_version", F.lit(
        f"MAxO:{MAXO_COMMIT};annotations:{MAXO_ANNOTATIONS_COMMIT};"
        f"canonical:{canonical_table}"
    ))
    .withColumn("generated_at", F.current_timestamp())
)

(
    action_matches.write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(ACTION_MATCH_TABLE)
)

dbutils.notebook.exit(
    json.dumps(
        {
            "action_table": ACTION_TABLE,
            "edge_table": EDGE_TABLE,
            "alias_table": ALIAS_TABLE,
            "action_match_table": ACTION_MATCH_TABLE,
            "actions": action_catalog.count(),
            "edges": edges.count(),
            "aliases": alias_catalog.count(),
            "facility_action_matches": action_matches.count(),
            "hpo_terms": len(hpo_terms),
            "maxo_terms": len(maxo_terms),
            "versions": {
                "maxo": MAXO_COMMIT,
                "maxo_annotations": MAXO_ANNOTATIONS_COMMIT,
                "hpo": HPO_RELEASE,
            },
        }
    )
)
