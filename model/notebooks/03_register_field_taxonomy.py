# Databricks notebook source
import json

import mlflow
from mlflow.tracking import MlflowClient


dbutils.widgets.text(
    "metrics_table",
    "workspace.cardinal_virtues.model_field_taxonomy_metrics",
    "Training metrics table",
)
dbutils.widgets.text(
    "registered_model_name",
    "workspace.carepath_model.model_field_taxonomy",
    "Registered model name",
)
dbutils.widgets.text("alias", "Champion", "Model alias")
dbutils.widgets.text("algorithm_version", "", "Optional algorithm version")

metrics_table = dbutils.widgets.get("metrics_table").strip()
registered_model_name = dbutils.widgets.get("registered_model_name").strip()
alias = dbutils.widgets.get("alias").strip()
algorithm_version = dbutils.widgets.get("algorithm_version").strip()

metrics = spark.table(metrics_table)
if algorithm_version:
    metrics = metrics.where(metrics.algorithm_version == algorithm_version)
rows = metrics.orderBy(metrics.generated_at.desc()).limit(1).toPandas()
if rows.empty:
    raise ValueError(f"No model metrics found in {metrics_table}")

metric_row = rows.iloc[0]
run_id = str(metric_row["mlflow_run_id"])
mlflow.set_registry_uri("databricks-uc")
model_uri = f"runs:/{run_id}/model"
registered = mlflow.register_model(model_uri=model_uri, name=registered_model_name)
versions = list(
    MlflowClient().search_model_versions(f"name='{registered_model_name}'")
)
versions.sort(key=lambda version: int(version.version), reverse=True)
latest = versions[0]
MlflowClient().set_registered_model_alias(
    name=registered_model_name,
    alias=alias,
    version=registered.version,
)

dbutils.notebook.exit(
    json.dumps(
        {
            "registered_model": registered_model_name,
            "alias": alias,
            "version": registered.version,
            "latest_version": latest.version,
            "source_run_id": run_id,
        }
    )
)
