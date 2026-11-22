# Two-stage service retrieval and reranking

This experiment package implements the agreed design: **offline high-recall hospital ×
service membership**, then **online service filtering, evidence-aware reranking and map
output**. No generative model/API/LLM judge is used. Existing backend and frontend APIs
are not changed; use the outputs to choose a ranking method before integrating it.

## Quick start (local)

Run from the repository root, Python 3.10+:

```bash
python -m pip install -r experiments/requirements.txt
python -m unittest discover -s experiments/tests -v
python -m experiments.run \
  --facilities /path/to/model_facilities.tsv \
  --evidence /path/to/model_evidence_items.tsv \
  --queries experiments/queries.example.csv \
  --methods rules tfidf bm25 \
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
  --methods rules tfidf bm25 --out data/experiments/dev_002
```

The adapter only sends SELECT statements. The SQL API uses 32 evidence buckets to
avoid a single oversized INLINE result. The facilities query currently reads all model
columns: use the notebook/Spark adapter if the result exceeds the API size limit.

## Databricks Free Edition

Clone this branch/repository into a Databricks Git folder. Open
`notebooks/100_two_stage_experiments.py` as a source notebook and run its cells. It loads
`model_facilities` and `model_evidence_items` with Spark SQL + `toPandas`, with no RDD,
`.cache()`, classic-only API or writes to source tables. About 10k facilities plus the
evidence corpus must fit driver memory; this is not a distributed neural training job.

Set the notebook's `schema`, `queries`, `qrels`, `methods`, `pins`, and `out` widgets.
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
