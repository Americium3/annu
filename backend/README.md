# CarePath API (backend)

FastAPI service that connects the React frontend (`web/`) to the service-first recommender and the Databricks data.

```
web (Vite :5173) ──/api──▶ backend (FastAPI :8000) ──SQL──▶ Databricks: workspace.cardinal_virtues
                                    │                        serving_service_index, serving_facilities,
                                    └─ in-memory recommender  ref_service_tags, pincode_reference
```

## How a request is answered

> Measured on `workspace.golden_eval` (dev): P@3 0.369 → 0.881, nDCG@3 0.351 → 0.779 against the previous main.
> Every step, model and parameter that was tried is in [experiments/RESULTS.md](../experiments/RESULTS.md).

1. **Service → tag**: the text is mapped to one of the 100 service tags (`ref_service_tags`; labels, synonyms and
   `SERVICE_INPUT_SYNONYMS` in `config.py`). Ambiguous text ("surgery") returns 422 with suggestions. Text that names
   several *services* ("Trauma / emergency care") searches all of them; a condition next to a service
   ("chemotherapy / cancer treatment") only describes it. Whole sentences work too ("Bangalore ke paas an emergency
   C-section kahan milega?").
2. **Location**: coordinates; a 6-digit PIN anywhere in the text ("PIN 232115", "pincode 560 034"); district or city,
   also through old / variant spellings from `ref_address_alias` ("Calcutta", "Bombay", "UP"); a facility named as the
   location ("Chole Eye Hospital, Bhandara"); last, the closest place name (marked low confidence).
3. **Who offers it (stage 1, v2)**: `pipeline/service_index_v2.py` builds facility × service candidates from every
   evidence field when the snapshot loads (`CAREPATH_SERVICE_INDEX=v2`, about 2 minutes). Each sentence gets a status:
   explicit, related (specialty only), negated / planned / outsourced / referred, or about another institution. Grade
   3 = explicit and corroborated, 2 = one explicit statement (both recommendable), 1 = related only, 0 = negative only.
   Wrong senses are dropped ("gastric bypass" is not cardiac surgery, "emergency dentistry" is not emergency care,
   jaw fractures are not trauma care). Down-weights: explicit wording only in specialty / name / description (× 0.75),
   a facility name announcing another specialty ("… Eye Hospital" claiming burns care: × 0.6, likely merged records),
   inpatient-only services at a clinic (× 0.7). `CAREPATH_SERVICE_INDEX=v1` reads the old `serving_service_index`.
4. **Usable evidence + location**: rows marked `review_blocked` (identity conflict, evidence about another institution,
   coordinates vs PIN conflict, no location) are counted but never recommended.
5. **Where**: the candidate pool is at least twice the travel distance for this kind of care (see below), widened
   25 → 50 → 100 → 200 km until at least `MIN_POOL_SIZE` (3) facilities are inside, so people get options to compare.
   Inside the pool, distance is a ranking factor, not a cut-off.
6. **Order**: rank score = **evidence strength × closeness** (`rank_candidates` in `recommender.py`, weights in
   `config.py`). The selected pool and `formal` eligibility stay upstream gates: review-blocked rows cannot be rescued
   by a high score.
   - *Proof strength* (0–1): evidence tier 1 / 2 / 3 → 1.0 / 0.8 / 0.55, × 0.6 if only equipment is mentioned,
     × 0.85 if statements also name another institution, × 1.0 / 0.9 / 0.75 for a verified point / unverified point /
     PIN-area location.
   - *Text match* (0–1, only in `cross_encoder` mode): how well the best quote matches "a hospital that provides
     <service>", from the cross-encoder (below).
   - *Evidence strength* = proof strength in the default `rules` mode. In `cross_encoder` mode it is 0.25 × text match
     + 0.75 × proof strength (picked by leave-one-query-out CV; was 4/7 : 3/7).
   - *Closeness* (0–1) = 1 / (1 + (km / travel_km)²): it halves at the distance people reasonably travel for this kind
     of care, about 10 km for emergencies and births, 15 km for dialysis and routine care, 30 km for scans and 60 km for
     planned surgery (default 25 km). It multiplies evidence, so a far facility needs much stronger evidence to rank first.
   - Weak proof (equipment only, or explicit wording that was down-weighted for its source or plausibility) is always
     listed after every facility with solid proof (`SOLID_GATE=evidence`). The earlier gate (`proof`, proof strength
     ≥ 0.5) also pushed a one-statement claim at an unverified point behind everything, however close.
   - The score shown in the UI is this rank score × 100, so the number and the order always agree. Each result also
     carries `rankFactors` (text match, proof, evidence, closeness, travel distance and the reasons behind proof
     strength), `reranking` in cross-encoder mode, and `phone` / `website` when the record has them.

Run `python test_ranking.py` (rules mode) and `python -m unittest tests.test_serving_cross_encoder` (cross-encoder
mode, fake model) for the ranking tests: synthetic data, no Databricks access or model download needed.

The serving tables are built by notebook `06_build_serving_tables` and must be rebuilt after the tags or location
policy change. The optional old rules mode mirrors `03_recommender_lib` (section F); the default reranker does not.

For each eligible candidate in the selected radius, select at most five distinct usable passages deterministically
(procedure/capability/description before other fields, then stable field/position/text order), score in CPU batches,
and keep the maximum relevance score. A bounded in-memory cache reuses identical service/passage pairs across locations.
The default checkpoint is `cross-encoder/ms-marco-MiniLM-L6-v2`, with a 512-token pair limit. Longer pairs are
truncated by its tokenizer. Raw single-label logits receive sigmoid exactly once; this is a relevance score,
**not a calibrated probability of service availability or medical quality**.

```text
rank_score = proof_strength * 1 / (1 + (straight_km / travel_km)^2)                                   # rules (default)
rank_score = (0.25 * cross_encoder_relevance + 0.75 * proof_strength) * 1 / (1 + (straight_km / travel_km)^2)  # cross_encoder
```

Solid proof first, then the unrounded score descending, then distance and facility ID for deterministic ties.
Return at most eight; the old B-lane promotion no longer reorders results. Each result's `reranking` object records
the checkpoint, components, weights, selected evidence reference/text and scored passage count.

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

In `cross_encoder` mode the app additionally loads and warms the cross-encoder before reporting startup readiness. First startup requires
access to the Hugging Face checkpoint (and can be slower); subsequent model loads use its normal disk cache.
For offline deployments, pre-download the checkpoint and set `CAREPATH_CROSS_ENCODER_MODEL` to its local directory.
The Databricks Apps bundle includes the scorer and neural dependencies automatically; `app.yaml` sets the default
method and a writable `HF_HOME`. This code change does not deploy/restart an existing app.

Configuration:

| Environment variable | Default |
|---|---|
| `CAREPATH_RANKING_METHOD` | `rules`; `cross_encoder` reranks with the cross-encoder (no gain on the golden dev set) |
| `CAREPATH_SERVICE_INDEX` | `v2` (build candidates from evidence at load); `v1` reads `serving_service_index` |
| `CAREPATH_MIN_POOL_SIZE` | `3` facilities before the search stops widening |
| `CAREPATH_SOLID_GATE` | `evidence`; `proof` restores the earlier proof ≥ 0.5 gate |
| `CAREPATH_CROSS_ENCODER_QUERY_STYLE` | `natural` ("a hospital that provides X"); `keywords` = label + synonyms |
| `CAREPATH_EMERGENCY_MISSING_FACTOR` | `1.0` (off); e.g. `0.6` ranks facilities with emergency evidence first for urgent wording |
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
