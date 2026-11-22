# Databricks notebook source
from __future__ import annotations

import json
import sys

from pyspark.sql import functions as F
from pyspark.sql import types as T
from pyspark.sql.window import Window


dbutils.widgets.text("output_catalog", "workspace", "Output catalog")
dbutils.widgets.text("output_schema", "cardinal_virtues", "Output schema")
dbutils.widgets.text(
    "service_tag_table",
    "workspace.cardinal_virtues.ref_service_tags",
    "Reference service tags",
)
dbutils.widgets.text(
    "action_catalog_table",
    "workspace.cardinal_virtues.model_action_catalog",
    "MAxO action catalog",
)
dbutils.widgets.text(
    "action_alias_table",
    "workspace.cardinal_virtues.model_action_alias",
    "MAxO action aliases",
)
dbutils.widgets.text(
    "action_match_table",
    "workspace.cardinal_virtues.model_facility_action_match",
    "Facility action matches",
)
dbutils.widgets.text(
    "model_src_path",
    "/Workspace/Users/kevinzh3@andrew.cmu.edu/carepath_model/src",
    "Workspace source path",
)

output_catalog = dbutils.widgets.get("output_catalog").strip()
output_schema = dbutils.widgets.get("output_schema").strip()
service_tag_table = dbutils.widgets.get("service_tag_table").strip()
action_catalog_table = dbutils.widgets.get("action_catalog_table").strip()
action_alias_table = dbutils.widgets.get("action_alias_table").strip()
action_match_table = dbutils.widgets.get("action_match_table").strip()
model_src_path = dbutils.widgets.get("model_src_path").strip()

try:
    from carepath_model.service_catalog import (
        TAG_ACTION_OVERRIDES,
        infer_action_service_type,
        infer_service_urgency,
    )
    from carepath_model.taxonomy import normalize_text
except ModuleNotFoundError:
    if model_src_path not in sys.path:
        sys.path.insert(0, model_src_path)
    from carepath_model.service_catalog import (
        TAG_ACTION_OVERRIDES,
        infer_action_service_type,
        infer_service_urgency,
    )
    from carepath_model.taxonomy import normalize_text


SERVICE_CATALOG_TABLE = f"{output_catalog}.{output_schema}.model_service_catalog"
SERVICE_ACTION_TABLE = f"{output_catalog}.{output_schema}.model_service_action_map"
RUN_VERSION = "service-catalog-v1"

service_tags = spark.table(service_tag_table).where(F.col("kind") == "service")
actions = spark.table(action_catalog_table)
action_aliases = spark.table(action_alias_table)
action_matches = spark.table(action_match_table)

required_tag_columns = {"tag_id", "label", "kind", "synonyms", "facility_count"}
missing_tag_columns = required_tag_columns - set(service_tags.columns)
if missing_tag_columns:
    raise ValueError(f"Missing service tag columns: {sorted(missing_tag_columns)}")

normalize_udf = F.udf(normalize_text, T.StringType())

tag_alias_rows = (
    service_tags.select(
        F.concat(F.lit("tag:"), F.col("tag_id")).alias("service_id"),
        F.col("tag_id"),
        F.col("label").alias("service_label"),
        F.col("group_name"),
        F.expr(
            "array_distinct(array_union(array(label), coalesce(synonyms, array())))"
        ).alias("aliases"),
    )
    .select(
        "service_id",
        "tag_id",
        "service_label",
        "group_name",
        F.explode("aliases").alias("alias"),
    )
    .withColumn("normalized_alias", normalize_udf("alias"))
    .where(F.trim("normalized_alias") != "")
)

action_facility_summary = action_matches.groupBy("action_id").agg(
    F.countDistinct("unique_id").alias("facility_count"),
    F.max("match_strength").alias("best_match_strength"),
    F.collect_set("source_fields").alias("source_field_groups"),
    F.collect_set("evidence_roles").alias("evidence_role_groups"),
)

matched_action_summary = (
    actions.alias("a")
    .join(
        action_facility_summary.alias("m"),
        F.col("a.action_id") == F.col("m.action_id"),
        "left",
    )
    .select(
        F.col("a.action_id"),
        F.col("a.label").alias("action_label"),
        F.col("a.parents").alias("parent_action_ids"),
        F.col("a.aliases"),
        F.col("a.contexts"),
        F.col("a.emergency_relevant"),
        F.coalesce(F.col("m.facility_count"), F.lit(0)).cast("long").alias(
            "facility_count"
        ),
        F.col("m.best_match_strength"),
    )
)

exact_tag_action_map = (
    tag_alias_rows.alias("t")
    .join(
        action_aliases.alias("a"),
        F.col("t.normalized_alias") == F.col("a.normalized_alias"),
        "inner",
    )
    .join(
        matched_action_summary.alias("s"),
        F.col("a.action_id") == F.col("s.action_id"),
        "inner",
    )
    .select(
        F.col("t.service_id"),
        F.col("t.tag_id"),
        F.col("a.action_id"),
        F.col("s.action_label"),
        F.col("t.alias").alias("matched_alias"),
        F.lit("exact_alias").alias("relation_type"),
        F.when(F.col("a.is_primary_label"), F.lit(1)).otherwise(F.lit(2)).alias(
            "priority"
        ),
        F.lit(0.95).alias("confidence"),
    )
    .dropDuplicates(["service_id", "action_id"])
)

override_rows = [
    (f"tag:{tag_id}", tag_id, action_id)
    for tag_id, action_ids in TAG_ACTION_OVERRIDES.items()
    for action_id in action_ids
]
override_schema = "service_id string, tag_id string, action_id string"
manual_tag_action_map = (
    spark.createDataFrame(override_rows, schema=override_schema)
    .join(
        matched_action_summary.select("action_id", "action_label"),
        "action_id",
        "inner",
    )
    .select(
        "service_id",
        "tag_id",
        "action_id",
        "action_label",
        F.lit("manual_override").alias("matched_alias"),
        F.lit("manual_override").alias("relation_type"),
        F.lit(1).alias("priority"),
        F.lit(0.9).alias("confidence"),
    )
)

tag_action_map = exact_tag_action_map.unionByName(manual_tag_action_map).dropDuplicates(
    ["service_id", "action_id"]
)

primary_tag_action = (
    tag_action_map.withColumn(
        "_rank",
        F.row_number().over(
            Window.partitionBy("service_id").orderBy(
                F.col("priority"),
                F.col("confidence").desc(),
            )
        ),
    )
    .where(F.col("_rank") == 1)
    .select("service_id", F.col("action_id").alias("primary_action_id"))
)

service_urgency_udf = F.udf(infer_service_urgency, T.StringType())
action_service_type_udf = F.udf(infer_action_service_type, T.StringType())

tag_services = (
    service_tags.select(
        F.concat(F.lit("tag:"), F.col("tag_id")).alias("service_id"),
        F.col("label").alias("service_label"),
        F.expr(
            "array_distinct(array_union(array(label), coalesce(synonyms, array())))"
        ).alias("aliases"),
        F.lit("reference_service_tag").alias("service_type"),
        F.col("group_name").alias("service_group"),
        F.coalesce(F.col("facility_count"), F.lit(0)).cast("long").alias(
            "facility_count"
        ),
        F.col("kind").alias("reference_kind"),
    )
    .join(primary_tag_action, "service_id", "left")
    .join(
        matched_action_summary.select("action_id", "parent_action_ids"),
        F.col("primary_action_id") == F.col("action_id"),
        "left",
    )
    .drop("action_id")
    .withColumn(
        "parent_action_ids",
        F.coalesce(F.col("parent_action_ids"), F.array().cast(T.ArrayType(T.StringType()))),
    )
    .withColumn(
        "urgency_level",
        service_urgency_udf(
            F.col("service_label"),
            F.col("aliases"),
            F.array(F.lit("treatment")),
            F.lit(False),
        ),
    )
    .withColumn(
        "service_contexts",
        F.array(F.lit("reference_service_tag")),
    )
    .withColumn("source", F.lit(service_tag_table))
)

linked_action_ids = tag_action_map.select("action_id").distinct()
additional_action_services = (
    matched_action_summary.alias("s")
    .join(linked_action_ids.alias("l"), "action_id", "left_anti")
    .where(F.col("s.facility_count") > 0)
    .select(
        F.concat(F.lit("maxo:"), F.col("s.action_id")).alias("service_id"),
        F.col("s.action_label").alias("service_label"),
        F.col("s.aliases"),
        action_service_type_udf(F.col("s.contexts")).alias("service_type"),
        F.lit("MAxO").alias("service_group"),
        F.col("s.facility_count"),
        F.lit("service").alias("reference_kind"),
        F.col("s.parent_action_ids"),
        F.col("s.action_id").alias("primary_action_id"),
        service_urgency_udf(
            F.col("s.action_label"),
            F.col("s.aliases"),
            F.col("s.contexts"),
            F.col("s.emergency_relevant"),
        ).alias("urgency_level"),
        F.col("s.contexts").alias("service_contexts"),
        F.lit(action_catalog_table).alias("source"),
    )
)

service_catalog = (
    tag_services.select(
        "service_id",
        "service_label",
        "aliases",
        "service_type",
        "service_group",
        "facility_count",
        "reference_kind",
        "parent_action_ids",
        "primary_action_id",
        "urgency_level",
        "service_contexts",
        "source",
    )
    .unionByName(
        additional_action_services.select(
            "service_id",
            "service_label",
            "aliases",
            "service_type",
            "service_group",
            "facility_count",
            "reference_kind",
            "parent_action_ids",
            "primary_action_id",
            "urgency_level",
            "service_contexts",
            "source",
        )
    )
    .withColumn("run_version", F.lit(RUN_VERSION))
    .withColumn("generated_at", F.current_timestamp())
    .withColumn(
        "action_mapping_status",
        F.when(
            F.col("primary_action_id").isNull(),
            F.lit("capability_only_or_unmapped"),
        ).otherwise(F.lit("mapped")),
    )
)

tag_service_links = tag_action_map.select(
    "service_id",
    "action_id",
    "action_label",
    "relation_type",
    "priority",
    "confidence",
)
action_service_links = additional_action_services.select(
    "service_id",
    F.col("primary_action_id").alias("action_id"),
    F.col("service_label").alias("action_label"),
    F.lit("primary").alias("relation_type"),
    F.lit(1).alias("priority"),
    F.lit(1.0).alias("confidence"),
)
service_action_map = (
    tag_service_links.unionByName(action_service_links)
    .withColumn("run_version", F.lit(RUN_VERSION))
    .withColumn("generated_at", F.current_timestamp())
    .dropDuplicates(["service_id", "action_id"])
)

(
    service_catalog.write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(SERVICE_CATALOG_TABLE)
)
(
    service_action_map.write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(SERVICE_ACTION_TABLE)
)

tag_with_actions = (
    tag_action_map.select("service_id").distinct().join(
        tag_services.select("service_id"), "service_id", "inner"
    ).count()
)
tag_total = tag_services.count()

dbutils.notebook.exit(
    json.dumps(
        {
            "service_catalog_table": SERVICE_CATALOG_TABLE,
            "service_action_table": SERVICE_ACTION_TABLE,
            "service_count": service_catalog.count(),
            "service_action_count": service_action_map.count(),
            "reference_service_tags": tag_total,
            "reference_tags_with_action_links": tag_with_actions,
            "additional_maxo_services": additional_action_services.count(),
            "run_version": RUN_VERSION,
        }
    )
)
