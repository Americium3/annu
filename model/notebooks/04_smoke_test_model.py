# Databricks notebook source
import json

import mlflow
import pandas as pd


dbutils.widgets.text(
    "model_uri",
    "models:/workspace.carepath_model.model_field_taxonomy@Champion",
    "UC model URI",
)

model_uri = dbutils.widgets.get("model_uri").strip()
samples = pd.DataFrame(
    [
        ("procedure_arr", "Provides hemodialysis and peritoneal dialysis"),
        ("procedure_arr", "Magnetic resonance imaging scan"),
        ("capability_arr", "24x7 emergency and trauma centre"),
        ("capability_arr", "NABH accredited multispeciality hospital"),
        ("equipment_arr", "On-site MRI scanner"),
        ("equipment_arr", "Wheelchair accessible entrance"),
    ],
    columns=["source_field", "text"],
)

mlflow.set_registry_uri("databricks-uc")
model = mlflow.pyfunc.load_model(model_uri)
predictions = model.predict(samples)
samples["prediction"] = list(predictions)

dbutils.notebook.exit(
    json.dumps(
        {
            "model_uri": model_uri,
            "predictions": samples.to_dict(orient="records"),
        }
    )
)
