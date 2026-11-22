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
4. **Where**: the candidate pool is at least twice the travel distance for this kind of care (see below), widened
   25 → 50 → 100 → 200 km until a provider is found. Inside the pool, distance is a ranking factor, not a cut-off.
5. **Order**: rank score = **proof strength × closeness** (`rank_candidates` in `recommender.py`, weights in `config.py`).
   - *Proof strength* (0–1): evidence tier 1 / 2 / 3 → 1.0 / 0.8 / 0.55, × 0.6 if only equipment is mentioned,
     × 0.85 if statements also name another institution, × 1.0 / 0.9 / 0.75 for a verified point / unverified point /
     PIN-area location.
   - *Closeness* (0–1) = 1 / (1 + (km / travel_km)²): it halves at the distance people reasonably travel for this kind
     of care, about 10 km for emergencies and births, 15 km for dialysis and routine care, 30 km for scans and 60 km for
     planned surgery (default 25 km).
   - Weak proof (equipment only, or proof below 0.5) is always listed after every facility with solid proof, however
     close it is.
   - The score shown in the UI is this rank score × 100, so the number and the order always agree. Each result also
     carries `rankFactors` (proof, closeness, travel distance and the reasons behind proof strength), and `phone` /
     `website` when the record has them.

Run `python test_ranking.py` for the ranking tests (synthetic data, no Databricks access needed).

The rules are the same as Databricks notebook `03_recommender_lib` (section F). The serving tables are built by
notebook `06_build_serving_tables` and must be rebuilt after the tags or the location policy change.

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

Then start the frontend (`cd web && pnpm install && pnpm dev`) and open http://127.0.0.1:5173.
Vite proxies `/api` to port 8000.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | data source and row counts |
| GET | `/api/services` | the 100 service tags (search suggestions) |
| GET | `/api/locations?q=pun` | district / city / PIN suggestions |
| POST | `/api/recommendations` | `{serviceText, locationText}` (or `coordinates` from "Use my location" instead of text) → `RecommendationResponse` (`web/src/types.ts`) plus `metadata.funnel`. Any other field is rejected with 422. |

Errors: 422 `{"detail": {"field": "service" | "location", "message": ..., "suggestions": [...]}}`.
