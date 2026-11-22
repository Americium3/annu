# Two-stage service retrieval and reranking

This experiment package implements the agreed design: **offline high-recall hospital ×
service membership**, then **online service filtering, evidence-aware reranking and map
output**. No generative model/API/LLM judge is used. **Cross-encoder is the default**
for direct engine calls, the CLI and notebook. The live backend now also defaults to
cross-encoder; its existing serving-table gates and widening-radius policy are described
in [backend/README.md](../backend/README.md), and differ from the fixed-radius experiment.

## Quick start (local)

Run from the repository root, Python 3.10+:

```bash
python -m pip install -r experiments/requirements-neural.txt
python -m unittest discover -s experiments/tests -v
python -m experiments.run \
  --facilities /path/to/model_facilities.tsv \
  --evidence /path/to/model_evidence_items.tsv \
  --queries experiments/queries.example.csv \
  --settings experiments/settings.example.json \
  --out data/experiments/dev_001
```

The six example queries are **illustrations, not an evaluation benchmark**. They use
city reference coordinates, not a particular patient's address. Build a fixed dev/test
query set covering service, data density, location quality, positive/negative/no-result
cases, and independent human labels. Group near-duplicate locations and equivalent
queries within a split; never tune on test labels.

To read the existing Databricks model tables with the repo's SQL client:

```bash
# Set DATABRICKS_HOST, DATABRICKS_WAREHOUSE_ID and your approved authentication
# in the environment; never commit tokens.
python -m experiments.run --from-databricks \
  --schema workspace.cardinal_virtues \
  --queries experiments/queries.example.csv \
  --out data/experiments/dev_002
```

The adapter only sends SELECT statements. The SQL API uses 32 evidence buckets to
avoid a single oversized INLINE result. The facilities query currently reads all model
columns: use the notebook/Spark adapter if the result exceeds the API size limit.

Omitting `--methods` runs `cross_encoder`. For a full comparison, explicitly pass
`--methods rules tfidf bm25 bi_encoder cross_encoder`. A lexical-only environment can
still install `experiments/requirements.txt` and explicitly choose `--methods rules tfidf bm25`.
The shared pair scorer in `backend/cross_encoder.py` uses sigmoid of raw logits exactly
once and fails visibly when the model cannot run; it never silently substitutes rules.

## Databricks Free Edition

Clone this branch/repository into a Databricks Git folder. Open
`notebooks/100_two_stage_experiments.py` as a source notebook and run its cells. It loads
`model_facilities` and `model_evidence_items` with Spark SQL + `toPandas`, with no RDD,
`.cache()`, classic-only API or writes to source tables. About 10k facilities plus the
evidence corpus must fit driver memory; this is not a distributed neural training job.

Set the notebook's `schema`, `queries`, `qrels`, `methods`, `pins`, and `out` widgets.
The notebook installs neural requirements and initializes `methods` to `cross_encoder`.
Databricks may preserve an existing widget value: set it explicitly when reopening an old notebook.
`out` must point to an existing writable Volume or workspace filesystem folder. The
default Volume path is an example and is not created automatically. Use a **new output
directory for each run**. Changing Settings requires editing the notebook's Settings
constructor (or the CLI JSON). Notebook execution has not been verified on a live
Databricks workspace by this change.

## Input contract

- Facilities: `unique_id` (unique and non-null), `name`, resolved coordinate pair
  `loc_lat/loc_lon` or `best_lat/best_lon`, preferably `location_tier`,
  `flag_coord_pin_conflict`, `core_identity_conflict`, and `row_status`. Raw
  `latitude/longitude` are fallback coordinates with an unverified warning.
- Evidence: `unique_id`, `field`, `item_idx`, `text`; optional `evidence_status`.
  Supported fields: procedure, capability, equipment, specialty/specialties, description.
  No reliance on the often-empty `text_std` column. The adapter augments missing
  description and specialty items from the facility table if available.
- Preserve upstream attribution: nonempty `evidence_status` other than `usable`,
  `positive`, `text_supported` becomes review-only. **Check actual status values first**;
  unknown values do not silently become eligible. An upstream `usable` label is
  inherited, not independently re-verified.
- Queries CSV: `query_id`, `service` (canonical ID/unique exact alias), either
  `latitude,longitude` or `location` (`City/District, State`, six-digit PIN, or `lat,lon`).
  Optional `density_group` describes dataset facility density, not automatically rurality.
- PIN queries require `--pins` with an export of `pincode_reference` containing
  `pincode,lat,lon,states,districts`. Ambiguous PINs/place names fail explicitly instead
  of silently choosing a state. Named city/district centres require upstream-verified
  facility points; production should reuse the app's audited location resolver.

Duplicate facility IDs fail early rather than silently merging hospitals. The experiment
does not collapse `cluster_id`: shared clusters must first be checked as actual duplicate
facilities, not different branches. Orphan evidence is excluded and counted in manifest.

## Stage 1: high-recall service candidates

Reuse the existing 100-tag `pipeline/tag_dictionary.py` patterns and synonyms. The
canonical service label is matched exactly for user input. Candidate extraction uses
the curated regex patterns plus related specialty expressions for the six main services.
Related specialties, equipment-only, uncertain, planned/historical and negative mentions
remain in the audit pool. They are **not asserted to provide the service**.

`emergency-c-section` is a separate query from `c-section`; formal support requires
emergency wording in the same clause as the C-section mention. This does not establish
24/7 capability or medical prerequisites. Those require separate verified evidence.
SNCU/NICU and other broad mappings inherited from the existing dictionary still require
domain review. This package is an experiment, not clinical capability certification.

Every service is scored once per method before processing location queries, reusing
the score cache across locations. A fixed service list therefore needs no online neural
inference after warmup. The current cache is in-memory per process; outputs include
scored audit results, but model embeddings are not persisted between processes.

## Stage 2: text evidence score and recommendation

Compare the SAME candidates and capped evidence selection for:

| Method | Text scoring |
|---|---|
| `rules` | Constant text score; evidence qualification + distance baseline |
| `tfidf` | Word 1–2-gram, sublinear TF, cosine similarity |
| `bm25` | Fixed-corpus BM25 (k1=1.5, b=.75), bounded `s/(s+bm25_scale)` |
| `bi_encoder` | Retrieval-trained sentence encoder, normalized vectors and clipped cosine |
| `cross_encoder` | Query/evidence joint relevance model, sigmoid of default model logits |

The query contains the canonical label and its curated synonyms. Evidence is scored as
original items (with attribution context where provided), not as a bare `service_list`.
Up to five items per facility are selected using the same heuristic status priority and
stable evidence reference ordering, before any method-specific score. Best positive item
score aggregates to the facility. The cap/maximum may miss useful context and favour
longer records; hold it fixed for comparisons and ablate separately.

Eligibility is shared across methods: textual service support in procedure/capability/
description, usable resolved location, no known identity conflict, no blocked upstream
row, and no positive-versus-negative evidence conflict. Related/equipment-only matches
stay review-only. Clause-based negation, history, plans and attribution handling are
heuristics, not entailment or independent identity verification. Inspect errors manually.

Default `review` blocks coordinate/PIN conflicts. `respect_resolved` accepts only
upstream-supplied `point_verified`/`pin_area` resolutions for conflicts; it **does not
decide to trust PIN itself**. Choose this only after auditing the upstream policy. Do not
change location policy during the text-method comparison.

Among eligible facilities within the SAME fixed 200km radius:

```
total = .4 * text_score + .3 * evidence_score + .3 * exp(-straight_km / 30)
```

These are explicit experimental starting values, not learned/calibrated probabilities.
`evidence_score` is 1 for heuristic text support (not a source-independence score).
No clinical-quality, bed availability, marketing, follower or NFHS signal is used.
`evidence_first` optionally groups by evidence score before total; with binary formal
eligibility the evidence score is constant among eligible records, so this option alone
does not create a meaningful graded-evidence ablation. Add independently reviewed evidence
grades before testing stronger evidence-first policies. Ties break by facility ID.

### Neural runs

```bash
python -m pip install -r experiments/requirements-neural.txt
python -m experiments.run --facilities /path/model_facilities.tsv \
  --evidence /path/model_evidence_items.tsv --queries experiments/queries.example.csv \
  --methods rules tfidf bm25 bi_encoder cross_encoder \
  --out data/experiments/dev_neural_001
```

Model downloads from Hugging Face must be permitted. Neural dependency/download errors
fail visibly; no fallback is passed off as a neural result. CPU is default; set `device`
and batch size in Settings. Pin model IDs/revisions and package versions for final test
runs. Default models are generic retrieval models, not medically validated. If changing
the cross-encoder to a model with different output conventions, adapt its activation.

## Outputs and evaluation

- `runs.json`: full candidate audit + selected results; actual component scores and reasons.
- `service_candidates.csv`: uncapped extraction evidence and status (use to audit misses).
- `annotation_pool.csv`: union of generated candidates, with model scores/method labels
  hidden. Read original evidence and raw records too; add suspected misses from outside
  this pool. No automatic claim of exhaustive recall.
- `geojson/*.geojson`, `map.html`: selected locations and evidence popups for each query
  and method. HTML needs internet for Leaflet/OSM; GeoJSON itself is self-contained.
- `metrics_per_query.csv`, `metrics_summary.csv`: macro query averages and denominators.
- `plots/`: method comparison and service × method answer coverage heatmap.
- `precompute_timings.csv`, `manifest.json`: cold model/service scoring costs, warm
  recommendation latency, fingerprints, settings and runtime versions.

Qrels columns: `query_id,unique_id,relevance`. Grade independently:

| Grade | Meaning based on available records, not live clinical verification |
|---|---|
| 0 | Wrong service/entity/location, explicit contradiction, or outside the agreed query scope |
| 1 | Related but insufficient/uncertain service, identity or location evidence |
| 2 | Records support the exact service and correct entity/location within agreed scope |
| 3 | Meets grade 2 with clearer, independently reviewed service evidence/fit |
| blank | Not judged; never silently interpreted as 0 |

Adjudicate ambiguous cases; double-annotate a subset. Do not label using this system's
own status/regex/model scores. Keep query radius and meaning fixed across methods.
The template has service/identity/location sublabels for audit; the **human relevance
grade** is the qrels input. It is not auto-derived from the three columns.

```bash
# After grading the annotation pool (and adding missed facilities):
python -m experiments.run --facilities /path/model_facilities.tsv \
  --evidence /path/model_evidence_items.tsv --queries /path/test_queries.csv \
  --qrels /path/adjudicated_qrels.csv --methods rules tfidf bm25 \
  --out data/experiments/test_001
```

Metrics: strict Precision@k (unfilled slots count against k), precision among returned
items, nDCG@k relative to the judged pool, candidate recall relative to known positives,
Hit@k, answer coverage, and false abstention among queries with known positives.
Unknown returned labels make precision/nDCG blank, not false; inspect judged coverage.
Queries with no known positives have undefined recall and nDCG. A query with known
positives and no output has P@k/nDCG=0 and false abstention=1. All correctness metrics
remain blank without qrels. Do not fabricate pass targets.

Candidate recall is before geographic/eligibility filtering and is intentionally equal
across rerankers. Final Hit@k/precision measure downstream effects. Current plots are
descriptive and have no confidence intervals; report counts and bootstrap by query group
before drawing strong conclusions. Baseline comparisons use the same geographic policy,
query expansion, source records, evidence cap and fusion weights; normalized score scales
still differ. For best end-to-end results, tune each method on dev only with the same
budget, then freeze and evaluate on test.

## Validation status

Unit and fixture integration tests cover candidates, false-positive controls, shared
candidate fairness, geographic policies, qrels denominators, unlabeled results, map/CSV/
plot outputs and a mocked bi-encoder. Real neural weights and live Databricks data require
your environment; passing these tests does not demonstrate healthcare recommendation
quality. No clinical ground truth or benchmark results are bundled.

## Optional NFHS district context

NFHS is used for **historical background, evaluation strata and experiment-map
overlays**. It never enters service extraction, eligibility, ranking weights, search
radius, or hospital recommendation reasons. This feature lives in the experiment
runner/notebook; the production React app/API are unchanged.

### Run with context

```bash
python -m experiments.run \
  --facilities /path/model_facilities.tsv --evidence /path/model_evidence_items.tsv \
  --queries experiments/queries.nfhs.example.csv \
  --nfhs /path/nfhs_5_district_health_indicators.csv \
  --district-aliases /path/reviewed_district_aliases.csv \
  --methods rules tfidf bm25 --out data/experiments/nfhs_dev_001
```

The alias argument is optional; without it only normalized exact district/state names
match. For SQL access, replace `--nfhs` with:

```text
--nfhs-table databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.nfhs_5_district_health_indicators
```

Use `--district-alias-table catalog.schema.reviewed_aliases` instead of an alias file
when an adapted table is available. `--from-databricks` continues to load the model
tables. All table adapters issue SELECT only. In the notebook, set `nfhs_table` to the
full table above, optionally set `district_alias_table`, choose an appropriate query
CSV, and run with a new `out` path. Blank `nfhs_table` keeps context disabled.

### District identity and crosswalk contract

Coordinate and city queries need **reviewed `context_state,context_district` metadata**.
Audited PIN queries and resolved district-name queries supply these automatically.
No nearest hospital, nearest PIN, or city-name-as-district assignment is made for raw
coordinates/cities. The NFHS example file includes illustrative district assignments
for four queries and leaves the two ambiguous examples blank; review all query geography
before evaluation. These are not gold location labels.

Map context is shown at the **query reference point**, not as a district boundary.
NFHS supplies no polygons. `district_context.geojson` contains points with explicit
reference-point metadata; this change does not invent choropleth geometries.

Your existing `ref_district_alias` must be exported/adapted to these columns:

| Column | Meaning |
|---|---|
| `source_state`, `source_district` | Reviewed names in PIN/facility/query data |
| `target_state`, `target_district` | Names identifying the corresponding NFHS district |
| `mapping_type` | `name_alias`, `boundary_change`, or `unresolved` |

Only `name_alias` is joined. Boundary changes and unresolved entries remain unmatched
for review, even if the original district name happens to match NFHS. True split/merge
crosswalks require population/boundary information and are outside this feature.
Unicode/case/whitespace/punctuation are normalized, but there is no fuzzy matching or
automatic renaming. Duplicate NFHS keys or duplicate alias source keys fail before
joining, preventing row multiplication. A reviewed many-to-one name mapping is allowed;
one-to-many mappings must be resolved externally. Aliases with absent targets are audited.

Facilities use `state_key`/`state`/`address_stateOrRegion` and `district_key`/`district`.
The raw facilities table has no district; supply the cleaned model table. PIN directory
joins and postal-office deduplication remain upstream responsibilities.

### Cleaning and interpretation

- Preserve raw values, numeric values and separate statuses: `valid`, `low_sample`,
  `suppressed`, `missing`, `invalid`, `out_of_range`. `(42.5)` retains 42.5 plus a
  low-sample flag; `*` stays suppressed, never zero. Percentages must be in 0–100.
- Parse all `_pct` indicators, `sex_ratio_*` fields and available sample-count columns.
  Household/women/men counts are metadata, not indicator-specific denominators, survey
  precision estimates, population weights, or weights for calculating state estimates.
- Preserve the historical survey period, 2019–2021. Administrative geography may differ
  from current PIN geography. Health burden/utilization is not directly service demand.
- The map displays insurance background for all services; maternal/birth/ANC/PNC
  indicators additionally appear for C-section/NICU. It does not invent MRI/burn-care
  demand indicators. District context is separate from the facility evidence popups.
- No patient's insurance, income, condition or urgency is inferred. No public/private
  preference or insurance acceptance is inferred from district rates. Preference
  elicitation and any future ranking interactions require separate validation.

The marker convention is documented by the [official NFHS district factsheet catalog](https://www.data.gov.in/catalog/national-family-health-survey-5-nfhs-5-india-districts-factsheet-data-provisional).
For weighting, see the [DHS statistics guide](https://www.dhsprogram.com/pubs/pdf/DHSG1/Guide_to_DHS_Statistics_DHS-8.pdf).

### Context outputs and evaluation

| Output | Purpose |
|---|---|
| `district_context.csv` | Long-form raw/value/status indicator and sample metadata |
| `district_join_audit.csv` | One match result per facility; missing/unmatched/boundary-review retained |
| `query_district_join_audit.csv` | One district match/assignment source per query |
| `district_service_coverage.csv` | Dataset facility count, service-text-supported count, usable-evidence/location count per district/service |
| `metrics_by_district_context.csv` | Macro query means by method × service × supplied density group × NFHS group, with per-metric denominators |
| `district_context_manifest.json` | Input fingerprint, survey period, cut points and facility/query match counts |
| `district_context.geojson`, `map.html` | Toggleable reference-point background; no boundary geometry |
| `plots/nfhs_groups_*.png` | Descriptive no-answer, P@k and top-1 distance comparisons, with effective query counts |

Coverage counts describe **providers identifiable in the supplied dataset**; zero does
not establish that no service exists. They are not population-normalized capacity or
unmet-demand estimates. Unmatched facilities are accounted for in the join audit, not
silently assigned to a district. Service text support is the existing heuristic, not
independently confirmed availability. The usable count also respects identity/location
policy, independent of the particular query's distance radius.

Default evaluation indicators are insurance coverage and institutional birth rate when
present. Use `--nfhs-group-indicators exact_column_name ...` to choose others. Valid
district values define equal-weight district tertiles; this is an evaluation grouping,
not a population estimate. Low-sample, suppressed, missing and unmatched context form
separate groups. The cut points and tie rule are recorded in both manifests.

Freeze cut points before comparing benchmark runs: save the manifest's `group_bins`
object as a JSON file and pass `--nfhs-group-bins /path/frozen_bins.json` (or the notebook
widget). Do not tune thresholds on test outcomes. Bins may collapse with tied values;
inspect group counts rather than assuming three equally sized groups.

No qrels means correctness metrics stay blank with denominator zero. No recommendation
means distance is missing, not zero; no-answer coverage is still measurable. Subgroup
CSV includes query count, matched district count, each metric's valid count and mean
number of geolocated dataset facilities within the fixed search radius. Multiple query
methods repeat the same queries; do not treat them as independent survey samples.
Plots pool services/density strata descriptively; use the stratified CSV to check
composition effects. These comparisons have no confidence intervals and establish no
causal relationship. Use sufficient independent district/query groups and uncertainty
estimates before making fairness or improvement claims.

## Accuracy benchmark and claim guards

Run `notebooks/110_accuracy_benchmark.py` in your authenticated Databricks Git folder,
using exports of independently reviewed qrels and grouped dev/test queries. Or:

```bash
python -m experiments.benchmark --from-databricks --schema workspace.cardinal_virtues \
 --queries /path/grouped_queries.csv --qrels /path/human_qrels.csv \
 --methods rules tfidf bm25 bi_encoder cross_encoder \
 --cross-models cross-encoder/ms-marco-MiniLM-L6-v2 cross-encoder/ms-marco-TinyBERT-L2-v2 \
 --out /path/new_run
```

Queries require `query_id,service,latitude,longitude,split,group_id`. Keep related locations,
institution clusters and equivalent queries in one group/split. `split` must be dev/test.
Qrels are `query_id,unique_id,relevance` (0–3); unknown stays unjudged. Do not generate
qrels with the candidate extraction rules or this scorer. Fully judge the union of
candidate outputs before selecting a winner. Test is run only for the dev-selected
variant and baseline after selection; there is no test-set tuning or automatic deployment.

The matrix compares two distance decays, three text/distance weights, max versus top-two
mean evidence aggregation, and baseline versus clause guards, using the SAME 200km radius.
Rules use no text weight. This is the experimental engine's baseline, not an assertion
that its scores reproduce the live v4 serving ranker. A positive result here still requires
a serving-policy evaluation before deployment. Every configuration and attempt/error is
checkpointed in `attempts.json`; manifest records data/query/qrels hashes, the winner and
paired cluster-bootstrap uncertainty. Original test runs preserve evidence/rejections for
review. Missing labels prevent winner selection. Failures are recorded, never called model
results. No-result distances must not be interpreted as zero.

`backend/evidence_support.py` adds independently auditable clause guards. Production defaults
to `CAREPATH_CLAIM_GUARD=explicit`: exclude explicit negatives/plans/conflicts before radius
selection; malformed formal rows without usable evidence are omitted with an audit instead
of failing the whole request. `off` reproduces the previous policy; `strict` also excludes
referral/education/training-only descriptions. Strict is experimental pending real-data
review: positive service descriptions mentioning education can be ambiguous. Unknown
services retain upstream classification. These rules are linguistic safeguards, not NLI,
clinical validation, or evidence that a facility is open today. Full entity/temporal
resolution and negation scope remain unsolved. Source URL occurrence is not treated as
independent corroboration.

`experiments/challenge/` contains GENERATED SYNTHETIC cases, not the competition data.
Its labels are manually specified linguistic expectations. Dev/test reuse templates;
results are regression diagnostics, not generalization estimates. Never promote a production
weight configuration on these results, even if its score is perfect. The challenge is
rebuildable with `python -m experiments.challenge.build`.

### Evaluate the actual web backend

The experimental engine above deliberately uses a common fixed radius. To evaluate the
website's **actual** service gate, adaptive radius, proof grouping, multiplicative distance
formula and response explanations, run `notebooks/111_serving_accuracy_benchmark.py` in a
separate Databricks notebook. Its SELECT-only Spark adapter loads the exact serving tables.
Alternatively use an authenticated shell:

```bash
python backend/benchmark_serving.py --queries /path/grouped_queries.csv \
 --qrels /path/human_qrels.csv --out /path/new_private_serving_run
```

This runs 36 guard/ranker/weight/travel configurations, including the previous cross-encoder
policy (`guard=off`, original 4:3 text:proof weights and travel scale) as `baseline`. The
runner temporarily patches global config and must **not** run in the API process. It restores
config afterward and never promotes a winner. Travel scaling changes candidate radius as
well as distance penalty, so interpret it as a policy comparison. Candidate recall is left
blank because the API returns a candidate count, not the entire candidate pool. Warmup is
excluded from latency; shared pair-cache hits/cold misses make timings descriptive only.

See [recorded diagnostic results](results/claim_challenge/README.md) for the methods actually
executed, all parameters/results, and the explicit synthetic-data limitations. This log is
not an experiment on the 10,088 real facilities. No real-data production winner is claimed.
