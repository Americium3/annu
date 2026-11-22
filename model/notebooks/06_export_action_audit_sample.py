# Databricks notebook source
import json


dbutils.widgets.text(
    "action_match_table",
    "workspace.cardinal_virtues.model_facility_action_match",
    "Action match table",
)
dbutils.widgets.text(
    "action_catalog_table",
    "workspace.cardinal_virtues.model_action_catalog",
    "Action catalog table",
)
dbutils.widgets.text("strong_samples", "45", "Strong match samples")
dbutils.widgets.text("context_samples", "15", "Context match samples")

match_table = dbutils.widgets.get("action_match_table").strip()
catalog_table = dbutils.widgets.get("action_catalog_table").strip()
strong_samples = max(1, int(dbutils.widgets.get("strong_samples")))
context_samples = max(1, int(dbutils.widgets.get("context_samples")))

sample = spark.sql(
    f"""
    WITH ranked AS (
      SELECT
        m.unique_id,
        m.action_id,
        m.action_label,
        m.match_strength,
        m.match_type,
        m.evidence_count,
        m.source_fields,
        m.evidence_roles,
        m.matched_values,
        c.contexts,
        c.emergency_relevant,
        row_number() OVER (
          PARTITION BY m.match_type
          ORDER BY xxhash64(m.unique_id, m.action_id)
        ) AS sample_rank
      FROM {match_table} m
      LEFT JOIN {catalog_table} c
        ON m.action_id = c.action_id
    )
    SELECT *
    FROM ranked
    WHERE
      (match_type = 'strong_exact' AND sample_rank <= {strong_samples})
      OR
      (match_type = 'context_exact' AND sample_rank <= {context_samples})
    ORDER BY match_type, sample_rank
    """
).toPandas()

dbutils.notebook.exit(
    json.dumps(
        {
            "row_count": len(sample),
            "rows": json.loads(sample.to_json(orient="records", force_ascii=False)),
        },
        ensure_ascii=False,
    )
)
