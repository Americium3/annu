# CarePath API (backend)

FastAPI service that connects the React frontend (`web/`) to the service-first recommender and the Databricks data.

```
web (Vite :5173) ──/api──▶ backend (FastAPI :8000) ──SQL──▶ Databricks: workspace.cardinal_virtues
                                    │                        serving_service_index, serving_facilities,
                                    └─ in-memory recommender  ref_service_tags, pincode_reference
```

## How a request is answered

1. **Service → tag**: the text is mapped to one of the 100 service tags (`ref_service_tags`; labels, synonyms and
   `SERVICE_INPUT_SYNONYMS` in `config.py`). Ambiguous text ("surgery") returns 422 with suggestions.
2. **Who lists it**: facilities whose services column contains the tag (`model_facility_services` → `serving_service_index`).
   If none in the whole dataset, the response says so.
3. **Usable evidence + location**: rows marked `review_blocked` (identity conflict, evidence about another institution,
   coordinates vs PIN conflict, no location) are counted but never recommended.
4. **Where**: search starts at 25 km and widens 50 → 100 → 200 km until a provider is found (system decision, not a user setting).
5. **Default order: cross-encoder**. Score the canonical service name + synonyms jointly with each usable original
   evidence passage, then combine relevance and straight-line distance. The selected radius and `formal` eligibility
   remain upstream gates. Review-blocked rows cannot be rescued by a high model score.

The serving tables are built by notebook `06_build_serving_tables` and must be rebuilt after the tags or location
policy change. The optional old rules mode mirrors `03_recommender_lib` (section F); the default reranker does not.

For each eligible candidate in the selected radius, select at most five distinct usable passages deterministically
(procedure/capability/description before other fields, then stable field/position/text order), score in CPU batches,
and keep the maximum relevance score. A bounded in-memory cache reuses identical service/passage pairs across locations.
The default checkpoint is `cross-encoder/ms-marco-MiniLM-L6-v2`, with a 512-token pair limit. Longer pairs are
truncated by its tokenizer. Raw single-label logits receive sigmoid exactly once; this is a relevance score,
**not a calibrated probability of service availability or medical quality**.

```text
ranking_score = 0.4 * cross_encoder_relevance + 0.3 * formal_eligibility + 0.3 * exp(-straight_km / 30)
```

`formal_eligibility` is 1 for every admitted candidate; it does not distinguish their evidence quality. Sort by
the unrounded score descending, then distance and facility ID for deterministic ties. Return at most eight;
the old B-lane promotion no longer reorders the default results. The UI's rounded 0–100 score and its component
bars now reflect this formula. Each result's `reranking` object records the checkpoint, components, weights,
selected evidence reference/text and scored passage count. Existing evidence confidence remains separate.

## Run

```bash
cd backend
pip install -r requirements.txt
export DATABRICKS_HOST=https://dbc-662e9a8b-91a5.cloud.databricks.com
export DATABRICKS_WAREHOUSE_ID=01562a1cdb8d5257        # Serverless Starter Warehouse
export DATABRICKS_TOKEN=<your personal access token>    # never commit it
uvicorn main:app --port 8000
```

The first start loads the tables from Databricks (~15 s) and writes `backend/.cache/snapshot.pkl` (git-ignored).
Later starts read the snapshot (~1 s, no token needed). Set `CAREPATH_REFRESH=1` to reload from Databricks.

The app additionally loads and warms the cross-encoder before reporting startup readiness. First startup requires
access to the Hugging Face checkpoint (and can be slower); subsequent model loads use its normal disk cache.
For offline deployments, pre-download the checkpoint and set `CAREPATH_CROSS_ENCODER_MODEL` to its local directory.
The Databricks Apps bundle includes the scorer and neural dependencies automatically; `app.yaml` sets the default
method and a writable `HF_HOME`. This code change does not deploy/restart an existing app.

Configuration:

| Environment variable | Default |
|---|---|
| `CAREPATH_RANKING_METHOD` | `cross_encoder`; explicitly use `rules` only for a legacy comparison |
| `CAREPATH_CROSS_ENCODER_MODEL` | `cross-encoder/ms-marco-MiniLM-L6-v2` or a local checkpoint directory |
| `CAREPATH_CROSS_ENCODER_REVISION` | unset; pin a checkpoint revision for reproducible final runs |
| `CAREPATH_CROSS_ENCODER_DEVICE` | `cpu` |
| `CAREPATH_CROSS_ENCODER_BATCH_SIZE` | `32` |
| `CAREPATH_CROSS_ENCODER_MAX_LENGTH` | `512` tokens per pair |

Only single-logit relevance checkpoints are supported by this scorer. There is no automatic model fallback:
dependency/checkpoint failure blocks startup; inference failure or a malformed formal row with no usable passage
returns 503, rather than presenting rule-ranked results as cross-encoder output. Inspect serving-table integrity
before deployment. Health and recommendation metadata report the configured method/model/version.

```bash
# Deterministic fixture tests; no model download or Databricks access:
python -m unittest discover -s backend/tests -v  # run from repository root
```

Then start the frontend (`cd web && pnpm install && pnpm dev`) and open http://127.0.0.1:5173.
Vite proxies `/api` to port 8000.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | data source, row counts, ranking method/model/version and model readiness |
| GET | `/api/services` | the 100 service tags (search suggestions) |
| GET | `/api/locations?q=pun` | district / city / PIN suggestions |
| POST | `/api/recommendations` | `{serviceText, locationText}` (or `coordinates` from "Use my location" instead of text) → `RecommendationResponse` (`web/src/types.ts`) plus `metadata.funnel`. Any other field is rejected with 422. |

Errors: 422 `{"detail": {"field": "service" | "location", "message": ..., "suggestions": [...]}}`.
