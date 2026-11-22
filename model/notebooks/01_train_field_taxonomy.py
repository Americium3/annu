# Databricks notebook source
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import mlflow
import numpy as np
import pandas as pd
from mlflow.models.signature import infer_signature
from mlflow.tracking import MlflowClient
from pyspark.sql import functions as F
from pyspark.sql import types as T
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.feature_extraction.text import TfidfVectorizer


dbutils.widgets.text(
    "source_table",
    "workspace.cardinal_virtues.model_facilities",
    "Source facility table",
)
dbutils.widgets.text("output_catalog", "workspace", "Output catalog")
dbutils.widgets.text("output_schema", "cardinal_virtues", "Output schema")
dbutils.widgets.text(
    "model_name",
    "workspace.cardinal_virtues.model_field_taxonomy",
    "UC model name",
)
dbutils.widgets.text(
    "experiment_path",
    "/Users/kevinzh3@andrew.cmu.edu/carepath_model_field_taxonomy",
    "MLflow experiment",
)
dbutils.widgets.text(
    "model_src_path",
    "/Workspace/Users/kevinzh3@andrew.cmu.edu/carepath_model/src",
    "Workspace path containing carepath_model",
)
dbutils.widgets.text("register_model", "true", "Register UC Champion alias")
dbutils.widgets.text("min_class_count", "5", "Minimum weak-label class count")

source_table = dbutils.widgets.get("source_table").strip()
output_catalog = dbutils.widgets.get("output_catalog").strip()
output_schema = dbutils.widgets.get("output_schema").strip()
model_name = dbutils.widgets.get("model_name").strip()
experiment_path = dbutils.widgets.get("experiment_path").strip()
model_src_path = dbutils.widgets.get("model_src_path").strip()
register_model = dbutils.widgets.get("register_model").lower() == "true"
min_class_count = int(dbutils.widgets.get("min_class_count"))

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){1,2}$")
if not TABLE_RE.fullmatch(source_table):
    raise ValueError("source_table must be a valid UC table identifier")
for value, name in (
    (output_catalog, "output_catalog"),
    (output_schema, "output_schema"),
):
    if not IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{name} is not a valid SQL identifier")

try:
    from carepath_model.taxonomy import (
        CAPABILITY_FIELD,
        CATEGORY_BY_FIELD,
        EQUIPMENT_FIELD,
        PROCEDURE_FIELD,
        SPECIALTY_FIELD,
        evidence_role,
        normalize_text,
        weak_label,
    )
except ModuleNotFoundError:
    if model_src_path not in sys.path:
        sys.path.insert(0, model_src_path)
    from carepath_model.taxonomy import (
        CAPABILITY_FIELD,
        CATEGORY_BY_FIELD,
        EQUIPMENT_FIELD,
        PROCEDURE_FIELD,
        SPECIALTY_FIELD,
        evidence_role,
        normalize_text,
        weak_label,
    )


RAW_TABLE = f"{output_catalog}.{output_schema}.model_tag_raw_element"
CANONICAL_TABLE = f"{output_catalog}.{output_schema}.model_tag_canonical_element"
REVIEW_TABLE = f"{output_catalog}.{output_schema}.model_mapping_review_queue"
METRICS_TABLE = f"{output_catalog}.{output_schema}.model_field_taxonomy_metrics"
ALGORITHM_VERSION = "field-taxonomy-weak-tfidf-v1"

source = spark.table(source_table)
required = {
    "unique_id",
    PROCEDURE_FIELD,
    CAPABILITY_FIELD,
    EQUIPMENT_FIELD,
    SPECIALTY_FIELD,
}
missing = required - set(source.columns)
if missing:
    raise ValueError(f"Missing required columns: {sorted(missing)}")


normalize_udf = F.udf(normalize_text, T.StringType())
weak_label_schema = T.StructType(
    [
        T.StructField("rule_category", T.StringType()),
        T.StructField("rule_evidence_role", T.StringType()),
        T.StructField("rule_confidence", T.DoubleType()),
        T.StructField("rule_method", T.StringType()),
    ]
)


@F.udf(returnType=weak_label_schema)
def weak_label_udf(source_field: str, value: str):
    label = weak_label(source_field, value)
    return (
        label.category,
        label.evidence_role,
        float(label.confidence),
        label.match_method,
    )


def explode_field(frame, field: str):
    array_col = F.coalesce(F.col(field), F.array().cast(T.ArrayType(T.StringType())))
    return (
        frame.select(
            F.col("unique_id").cast("string").alias("unique_id"),
            F.lit(field).alias("source_field"),
            array_col.alias("_source_array"),
        )
        .select(
            "unique_id",
            "source_field",
            F.size("_source_array").alias("array_size"),
            F.posexplode("_source_array").alias("item_index", "raw_value"),
        )
        .where(F.col("raw_value").isNotNull() & (F.trim("raw_value") != ""))
        .withColumn("raw_value", F.trim("raw_value"))
        .withColumn("possibly_truncated", F.col("array_size") >= 50)
        .withColumn("source_version", F.lit(source_table))
        .withColumn("algorithm_version", F.lit(ALGORITHM_VERSION))
        .withColumn("generated_at", F.current_timestamp())
    )


parts = [
    explode_field(source, field)
    for field in (PROCEDURE_FIELD, CAPABILITY_FIELD, EQUIPMENT_FIELD, SPECIALTY_FIELD)
]
raw_elements = parts[0]
for part in parts[1:]:
    raw_elements = raw_elements.unionByName(part)

(
    raw_elements.write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(RAW_TABLE)
)

elements = (
    spark.table(RAW_TABLE)
    .withColumn("normalized_value", normalize_udf("raw_value"))
    .withColumn("_weak", weak_label_udf("source_field", "raw_value"))
    .select(
        "*",
        F.col("_weak.rule_category").alias("rule_category"),
        F.col("_weak.rule_evidence_role").alias("rule_evidence_role"),
        F.col("_weak.rule_confidence").alias("rule_confidence"),
        F.col("_weak.rule_method").alias("rule_method"),
    )
    .drop("_weak")
)

label_counts = (
    elements.where(F.col("rule_category") != "unclassified")
    .groupBy("source_field", "rule_category")
    .count()
    .toPandas()
)
valid_classes = {
    (row.source_field, row.rule_category)
    for row in label_counts.itertuples()
    if int(row.count) >= min_class_count
}

training = (
    elements.where(F.col("rule_category") != "unclassified")
    .select(
        "unique_id",
        "source_field",
        "normalized_value",
        "rule_category",
    )
    .dropDuplicates(["unique_id", "source_field", "normalized_value", "rule_category"])
    .toPandas()
)
training["valid_class"] = list(
    zip(training["source_field"], training["rule_category"])
)
training = training[training["valid_class"].isin(valid_classes)].drop(
    columns=["valid_class"]
)

if training["rule_category"].nunique() < 2:
    raise ValueError("Not enough weak-label categories to train a classifier")

groups = training["unique_id"].nunique()
if groups >= 10:
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, test_idx = next(splitter.split(training, groups=training["unique_id"]))
    train_pdf = training.iloc[train_idx].copy()
    test_pdf = training.iloc[test_idx].copy()
    split_method = "GroupShuffleSplit(unique_id)"
else:
    train_pdf = training.copy()
    test_pdf = training.copy()
    split_method = "all_rows_small_sample"

features_pdf = train_pdf[["source_field", "normalized_value"]].rename(
    columns={"normalized_value": "text"}
)
features_test = test_pdf[["source_field", "normalized_value"]].rename(
    columns={"normalized_value": "text"}
)

feature_preprocessor = ColumnTransformer(
    [
        (
            "text",
            TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(3, 5),
                min_df=2,
                max_features=60000,
                sublinear_tf=True,
            ),
            "text",
        ),
        (
            "field",
            OneHotEncoder(handle_unknown="ignore"),
            ["source_field"],
        ),
    ]
)

pipeline = Pipeline(
    [
        ("features", feature_preprocessor),
        (
            "classifier",
            LogisticRegression(
                class_weight="balanced",
                max_iter=1000,
                random_state=42,
            ),
        ),
    ]
)
pipeline.fit(features_pdf, train_pdf["rule_category"])
test_pred = pipeline.predict(features_test)
macro_f1 = float(f1_score(
    test_pdf["rule_category"],
    test_pred,
    average="macro",
    zero_division=0,
))
report = classification_report(
    test_pdf["rule_category"],
    test_pred,
    output_dict=True,
    zero_division=0,
)

mlflow.set_tracking_uri("databricks")
mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(experiment_path)
mlflow.autolog(disable=True)
mlflow.sklearn.autolog(disable=True)

signature = infer_signature(features_pdf.head(100), pipeline.predict(features_pdf.head(100)))
registered_version = None
with mlflow.start_run(run_name=ALGORITHM_VERSION) as run:
    mlflow.log_params(
        {
            "source_table": source_table,
            "algorithm_version": ALGORITHM_VERSION,
            "training_rows": len(train_pdf),
            "test_rows": len(test_pdf),
            "class_count": training["rule_category"].nunique(),
            "group_split": split_method,
        }
    )
    mlflow.log_metric("macro_f1", macro_f1)
    mlflow.sklearn.log_model(
        sk_model=pipeline,
        artifact_path="model",
        signature=signature,
    )
    run_id = run.info.run_id

if register_model:
    mlflow.register_model(model_uri=f"runs:/{run_id}/model", name=model_name)
    versions = list(MlflowClient().search_model_versions(f"name='{model_name}'"))
    versions.sort(key=lambda version: int(version.version), reverse=True)
    registered_version = versions[0].version
    MlflowClient().set_registered_model_alias(
        name=model_name,
        alias="Champion",
        version=registered_version,
    )


prediction_schema = T.StructType(
    [
        T.StructField("source_field", T.StringType()),
        T.StructField("normalized_value", T.StringType()),
        T.StructField("model_category", T.StringType()),
        T.StructField("model_confidence", T.DoubleType()),
    ]
)
prediction_rows = []
classes = np.asarray(pipeline.classes_)
for field in (PROCEDURE_FIELD, CAPABILITY_FIELD, EQUIPMENT_FIELD):
    allowed_categories = set(CATEGORY_BY_FIELD[field]) - {"unclassified"}
    allowed_mask = np.array(
        [category in allowed_categories for category in classes],
        dtype=bool,
    )
    unresolved_pdf = (
        elements.where(
            (F.col("source_field") == field)
            & (F.col("rule_category") == "unclassified")
        )
        .select("normalized_value")
        .dropDuplicates()
        .toPandas()
    )
    for start in range(0, len(unresolved_pdf), 50000):
        batch = unresolved_pdf.iloc[start : start + 50000].copy()
        if batch.empty:
            continue
        batch["source_field"] = field
        batch = batch.rename(columns={"normalized_value": "text"})
        probabilities = pipeline.predict_proba(batch[["source_field", "text"]])
        probabilities[:, ~allowed_mask] = -1.0
        best = probabilities.argmax(axis=1)
        confidence = probabilities[np.arange(len(batch)), best]
        for value, category_index, probability in zip(
            batch["text"], best, confidence
        ):
            prediction_rows.append(
                (field, value, str(classes[category_index]), float(probability))
            )

model_predictions = spark.createDataFrame(prediction_rows, prediction_schema)
model_evidence_role_udf = F.udf(evidence_role, T.StringType())

rule_canonical = elements.where(F.col("rule_category") != "unclassified").select(
    "unique_id",
    "source_field",
    "item_index",
    "raw_value",
    "normalized_value",
    "array_size",
    "possibly_truncated",
    F.col("rule_category").alias("canonical_category"),
    F.col("rule_evidence_role").alias("evidence_role"),
    F.lit(1.0).alias("classification_confidence"),
    F.col("rule_method").alias("match_method"),
    "source_version",
    "algorithm_version",
    "generated_at",
)

model_canonical = (
    elements.alias("e")
    .where(F.col("rule_category") == "unclassified")
    .join(
        model_predictions.alias("p"),
        (F.col("e.source_field") == F.col("p.source_field"))
        & (F.col("e.normalized_value") == F.col("p.normalized_value")),
        "left",
    )
    .select(
        F.col("e.unique_id"),
        F.col("e.source_field"),
        F.col("e.item_index"),
        F.col("e.raw_value"),
        F.col("e.normalized_value"),
        F.col("e.array_size"),
        F.col("e.possibly_truncated"),
        F.coalesce(F.col("p.model_category"), F.lit("unclassified")).alias(
            "canonical_category"
        ),
        model_evidence_role_udf(
            F.col("e.source_field"),
            F.coalesce(F.col("p.model_category"), F.lit("unclassified")),
        ).alias("evidence_role"),
        F.coalesce(F.col("p.model_confidence"), F.lit(0.0)).alias(
            "classification_confidence"
        ),
        F.lit("tfidf_logistic_regression").alias("match_method"),
        F.col("e.source_version"),
        F.col("e.algorithm_version"),
        F.col("e.generated_at"),
    )
)

canonical = rule_canonical.unionByName(model_canonical)

HIGH_RISK_RE = re.compile(
    r"\b(emergency|icu|intensive care|ventilat|dialysis|cardiac|oncology|"
    r"cancer|surgery|surgical|neonatal|nicu|stroke)\b",
    re.IGNORECASE,
)
high_risk_udf = F.udf(
    lambda value: bool(HIGH_RISK_RE.search(value or "")),
    T.BooleanType(),
)

canonical = (
    canonical.withColumn("high_risk", high_risk_udf("normalized_value"))
    .withColumn(
        "review_status",
        F.when(
            F.col("classification_confidence") < 0.65, F.lit("review_low_confidence")
        )
        .when(F.col("canonical_category") == "unclassified", F.lit("review_unmapped"))
        .when(F.col("high_risk"), F.lit("review_high_risk"))
        .otherwise(F.lit("auto_seed")),
    )
)

(
    canonical.write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(CANONICAL_TABLE)
)
(
    canonical.where(F.col("review_status").startswith("review_"))
    .select(
        "unique_id",
        "source_field",
        "item_index",
        "raw_value",
        "normalized_value",
        "canonical_category",
        "classification_confidence",
        "review_status",
        "possibly_truncated",
    )
    .write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(REVIEW_TABLE)
)

report_json = json.dumps(report, sort_keys=True)
metrics = spark.createDataFrame(
    [
        (
            ALGORITHM_VERSION,
            source_table,
            run_id,
            model_name,
            registered_version,
            split_method,
            int(len(train_pdf)),
            int(len(test_pdf)),
            int(training["rule_category"].nunique()),
            float(macro_f1),
            report_json,
            datetime.now(timezone.utc),
        )
    ],
    """
    algorithm_version string,
    source_table string,
    mlflow_run_id string,
    model_name string,
    model_version string,
    split_method string,
    training_rows int,
    test_rows int,
    class_count int,
    macro_f1 double,
    classification_report string,
    generated_at timestamp
    """,
)
(
    metrics.write.mode("append")
    .option("mergeSchema", "true")
    .saveAsTable(METRICS_TABLE)
)

dbutils.notebook.exit(
    json.dumps(
        {
            "raw_table": RAW_TABLE,
            "canonical_table": CANONICAL_TABLE,
            "review_table": REVIEW_TABLE,
            "metrics_table": METRICS_TABLE,
            "mlflow_run_id": run_id,
            "registered_model_version": registered_version,
            "macro_f1": macro_f1,
        }
    )
)
