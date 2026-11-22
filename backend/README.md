# Annu API (backend)

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
   evidence field when the snapshot loads (`ANNU_SERVICE_INDEX=v2`, about 2 minutes). Each sentence gets a status:
   explicit, related (specialty only), negated / planned / outsourced / referred, or about another institution. Grade
   3 = explicit and corroborated, 2 = one explicit statement (both recommendable), 1 = related only, 0 = negative only.
   Wrong senses are dropped ("gastric bypass" is not cardiac surgery, "emergency dentistry" is not emergency care,
   jaw fractures are not trauma care). Down-weights: explicit wording only in specialty / name / description (× 0.75),
   a facility name announcing another specialty ("… Eye Hospital" claiming burns care: × 0.6, likely merged records),
   inpatient-only services at a clinic (× 0.7). `ANNU_SERVICE_INDEX=v1` reads the old `serving_service_index`.
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
     <service>", from the cross-encoder (below). Its raw scores are tiny even for relevant quotes, so the logit is
     mapped onto a fixed scale: −11 (unrelated text) = 0, −5 and above = 1 (`TEXT_MATCH_LOGIT_RANGE`).
   - *Evidence strength* = proof strength in the default `rules` mode. In `cross_encoder` mode it is
     0.3 × text match + 0.7 × proof strength (proof weighs more: the model is noisy on short passages).
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
rank_score = proof_strength * 1 / (1 + (straight_km / travel_km)^2)                               # rules (default)
rank_score = (0.3 * text_match + 0.7 * proof_strength) * 1 / (1 + (straight_km / travel_km)^2)   # cross_encoder
```

Solid proof first, then the unrounded score descending, then distance and facility ID for deterministic ties.
Return at most eight; the old B-lane promotion no longer reorders results. Each result's `reranking` object records
the checkpoint, components, weights, selected evidence reference/text and scored passage count.

## Free-text requests (`/api/ask`, `nlu.py`)

The flow is fixed in code; a model fills in one step at most (after the pre-consultation agent in
`Americium3/ai-medical-demo`):

1. **Screen**: red-flag rules over the person's words in English, Hindi and Hinglish, with negation ("no chest pain",
   "सीने में दर्द नहीं है" do not trigger). Urgency level → emergency score: 1 = 100 (unconscious, not breathing),
   2 = 85 (chest pain, breathing trouble, stroke signs, heavy bleeding, poisoning, snakebite, seizure, crisis),
   3 = 60 (labour, fracture, accident, high fever, missed dialysis), 4 = 15. **80 or more opens the emergency
   screen at once: no model call, no search.** The place is still read, so the screen lists hospitals near it.
2. **Extract**: care and place from `web/src/data/lexicon.json` (shared with the web app's demo mode): 100 kinds of
   care with everyday English/Hindi/Hinglish words, matched as whole phrases, longest first. A broad word ("kidney",
   "दाँत") becomes a question with options, never a guess. Places: PIN codes, Hindi city names, "near X" / "X के पास" /
   "X mein", or a bare city the location reference knows; "near me" uses the device location. When no care word
   matched, symptom and disease names from `data/tags/alias_table.csv` give the condition ("bawaseer" →
   Hemorrhoids) and, where curated, its care tag; short all-caps abbreviations are ignored.
3. **Model (optional)**: set `ANNU_LLM_ENDPOINT` to a Databricks model serving endpoint (the app's own identity
   is used). One chat call fills what the rules left open. Answers are kept only if their quote appears verbatim in
   the message and is not denied; care ids must be in the catalogue; model urgency can only raise the rule level.
   If the call fails, the rules result stands and `llm.error` says so.

## LLM judge of hospital records (`judge.py`)

The pipeline decided offline which records *mention* a kind of care (regex + TF-IDF evidence tiers). Mentioning is
not offering: "dialysis machine", "refer to X for dialysis" and "Department of Nephrology" all mention dialysis. With
`judge: true` on `/api/recommendations` (the page asks right after showing the rules ranking), the language model
reads the top `JUDGE_TOP_K` hospitals' record lines (procedure, capability, equipment, specialty, description) and
gives each a verdict: `offers`, `likely`, `mentions_only`, `equipment_only` or `not_supported`, quoting the line
that decided it.

- A verdict is kept only if its quote is in that hospital's own lines; otherwise the rules ranking stands for it.
- Proof strength × `JUDGE_MULTIPLIER[verdict]` (1.0 / 0.85 / 0.65 / 0.5 / 0.25): it can lower proof, never raise
  it; `equipment_only` and `not_supported` also become weak proof (listed after every solid one).
- One batched call per search; verdicts are cached per (care, hospital). A failed call leaves the rules ranking and
  `metadata.judge.error`. Each judged result carries `judgement` (verdict, field, quote, full line, reason, model).

Urgency also changes the ranking: level 3 halves the travel distance (`URGENT_TRAVEL_FACTOR`), so nearer hospitals
count more. When the best option for an urgent request is still far (more than twice that distance), the page
suggests calling 108. Nothing here is a diagnosis.

## Voice input (`stt.py`, `POST /api/transcribe`)

As in Sprout, the browser records and the server transcribes. Sprout uses Groq's Whisper; Annu runs the same
open model inside the app (`ANNU_STT_MODEL`, default `openai/whisper-small`, CPU) so speech stays on
Databricks. The page records with the Web Audio API and sends 16 kHz mono 16-bit PCM (no audio decoder needed on
the server). Recording stops on a tap, after ~1.4 s of silence once the person has spoken, or at 20 s. A short hint
of Indian place names and kinds of care is passed as Whisper's prompt (it turned "near Kodak" into "near Cuttack"
on sample audio). Small, not base: base writes Hindi in Urdu script. If the server can't transcribe (503), the page
falls back to the browser's own voice typing where it exists; microphone problems get their own messages.

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
Later starts read the snapshot (~1 s, no token needed). Set `ANNU_REFRESH=1` to reload from Databricks.

In `cross_encoder` mode the app additionally loads and warms the cross-encoder before reporting startup readiness. First startup requires
access to the Hugging Face checkpoint (and can be slower); subsequent model loads use its normal disk cache.
For offline deployments, pre-download the checkpoint and set `ANNU_CROSS_ENCODER_MODEL` to its local directory.
The Databricks Apps bundle includes the scorer and neural dependencies automatically; `app.yaml` sets the default
method and a writable `HF_HOME`. This code change does not deploy/restart an existing app.

Configuration:

| Environment variable | Default |
|---|---|
| `ANNU_RANKING_METHOD` | `rules`; `cross_encoder` reranks with the cross-encoder (no gain on the golden dev set) |
| `ANNU_SERVICE_INDEX` | `v2` (build candidates from evidence at load); `v1` reads `serving_service_index` |
| `ANNU_MIN_POOL_SIZE` | `3` facilities before the search stops widening |
| `ANNU_SOLID_GATE` | `evidence`; `proof` restores the earlier proof ≥ 0.5 gate |
| `ANNU_CROSS_ENCODER_QUERY_STYLE` | `natural` ("a hospital that provides X"); `keywords` = label + synonyms |
| `ANNU_EMERGENCY_MISSING_FACTOR` | `1.0` (off); e.g. `0.6` ranks facilities with emergency evidence first for urgent wording |
| `ANNU_CROSS_ENCODER_MODEL` | `cross-encoder/ms-marco-MiniLM-L6-v2` or a local checkpoint directory |
| `ANNU_CROSS_ENCODER_REVISION` | unset; pin a checkpoint revision for reproducible final runs |
| `ANNU_CROSS_ENCODER_DEVICE` | `cpu` |
| `ANNU_CROSS_ENCODER_BATCH_SIZE` | `32` |
| `ANNU_CROSS_ENCODER_MAX_LENGTH` | `512` tokens per pair |

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
| POST | `/api/ask` | `{text, locationText?, coordinates?}`: a request in the person's own words → what was understood (care, place, urgency, each with the exact words it rests on) and `next`: `emergency`, `ask_care`, `ask_place` or `results` (with `results`). `locationText` / `coordinates` are the saved place or device location, used only when the text names no place. |
| POST | `/api/recommendations` | `{serviceText, locationText, urgency?}` (or `coordinates` from "Use my location" instead of text) → `RecommendationResponse` (`web/src/types.ts`) plus `metadata.funnel`. `urgency` 3 halves the travel distance. Any other field is rejected with 422. |

Errors: 422 `{"detail": {"field": "service" | "location", "message": ..., "suggestions": [...]}}`.

## Statement checks before scoring

`ANNU_CLAIM_GUARD=explicit` is the v5 default. Explicit service denials, future/historical
claims and contradictory statements are excluded before choosing the radius. If a formal
row contains no remaining usable evidence, it is omitted with a `metadata.claimGuard` audit;
one bad row no longer fails all other recommendations. `strict` additionally excludes
referral/awareness/counselling/training-only mentions; it is an experimental option pending
real-data review. `off` restores the previous admission policy. Unknown services retain the
upstream policy. These are local linguistic rules, not verified operational availability.
See the synthetic stress results and the independently-labelled real-data benchmark entry
point in `experiments/README.md` before promoting stronger policies or changing weights.

For an evaluation of this exact backend, use `notebooks/111_serving_accuracy_benchmark.py`
or `python backend/benchmark_serving.py --help`, in a **separate offline process**. It compares
36 guard/ranker/weight/travel policies with independent qrels and grouped dev/test selection.
No automatic production promotion. If a guard removes only part of the evidence, the returned
proof tier/counts are conservatively downgraded so the explanation cannot reuse deleted support.
