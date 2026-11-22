# Databricks notebook source
import json


dbutils.widgets.text(
    "export_dir",
    "/Volumes/workspace/carepath_model/model_files/local_snapshot",
    "UC Volume export directory",
)

export_dir = dbutils.widgets.get("export_dir").strip().rstrip("/")
dbutils.fs.mkdirs(export_dir)

datasets = {
    "service_catalog.json": "workspace.cardinal_virtues.model_service_catalog",
    "service_action_map.json": "workspace.cardinal_virtues.model_service_action_map",
    "facility_action_match.json": "workspace.cardinal_virtues.model_facility_action_match",
    "condition_action_edge.json": "workspace.cardinal_virtues.model_condition_action_edge",
}

manifest = {}
for filename, table_name in datasets.items():
    pandas_frame = spark.table(table_name).toPandas()
    target = f"{export_dir}/{filename}"
    pandas_frame.to_json(target, orient="records", force_ascii=False)
    manifest[filename] = {
        "table": table_name,
        "rows": len(pandas_frame),
    }

with open(f"{export_dir}/manifest.json", "w", encoding="utf-8") as handle:
    json.dump(
        {
            "export_dir": export_dir,
            "datasets": manifest,
        },
        handle,
        ensure_ascii=False,
        indent=2,
    )

dbutils.notebook.exit(
    json.dumps(
        {
            "export_dir": export_dir,
            "datasets": manifest,
        }
    )
)
