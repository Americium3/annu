# Databricks notebook source
import json


dbutils.widgets.text(
    "canonical_table",
    "workspace.cardinal_virtues.model_tag_canonical_element",
    "Canonical table",
)
dbutils.widgets.text("per_category", "3", "Samples per field/category")

canonical_table = dbutils.widgets.get("canonical_table").strip()
per_category = max(1, int(dbutils.widgets.get("per_category")))

sample = spark.sql(
    f"""
    WITH ranked AS (
      SELECT
        source_field,
        canonical_category,
        evidence_role,
        raw_value,
        normalized_value,
        classification_confidence,
        match_method,
        review_status,
        possibly_truncated,
        high_risk,
        row_number() OVER (
          PARTITION BY source_field, canonical_category
          ORDER BY xxhash64(unique_id, item_index)
        ) AS sample_rank
      FROM {canonical_table}
      WHERE canonical_category IS NOT NULL
    )
    SELECT
      source_field,
      canonical_category,
      evidence_role,
      raw_value,
      normalized_value,
      classification_confidence,
      match_method,
      review_status,
      possibly_truncated,
      high_risk
    FROM ranked
    WHERE sample_rank <= {per_category}
    ORDER BY source_field, canonical_category, sample_rank
    """
).toPandas()

dbutils.notebook.exit(
    json.dumps(
        {
            "canonical_table": canonical_table,
            "row_count": len(sample),
            "rows": sample.to_dict(orient="records"),
        },
        ensure_ascii=False,
    )
)
