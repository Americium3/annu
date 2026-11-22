# Tag Subdivision and Matching Algorithms

Stage: taxonomy preparation. This document defines how the facility array
values should be divided into model-facing tags. It does not yet define a
ranking model or frontend behavior.

## 1. Design decision

The model should not create separate, unrelated tag families named:

```text
procedure dialysis
capability dialysis
equipment dialysis
```

Instead, one clinical action should be linked to several field signals:

```text
MAxO action: renal dialysis
  procedure signal: hemodialysis, peritoneal dialysis
  capability signal: dialysis unit, dialysis centre
  equipment signal: dialysis machine, reverse-osmosis system
```

The action is the semantic unit. The source field determines the evidence
role and strength. This avoids triple-counting the same service.

## 2. Source field characteristics

The supplied profile drives the subdivision strategy:

| Field | Coverage | Distinct elements | Main problem | Proposed treatment |
|---|---:|---:|---|---|
| `procedure_arr` | 88.79% | 89,465 | many fine-grained procedures and synonyms | map to MAxO/action concepts |
| `capability_arr` | 99.59% | 168,572 | highly free-textual; mixes services, settings, accreditation, ownership and marketing | split by capability dimension first |
| `equipment_arr` | 71.39% | 35,244 | mixes diagnostic/treatment devices with accessibility and facilities | classify by equipment function and evidence role |
| `specialties_arr` | 100% | 2,932 | broad and inconsistently structured | reference only; use for specialty hints |
| `specialties_std` | 100% | 2,432 | format-normalized but not a strict controlled vocabulary | normalize and map to NUCC or an internal specialty concept |

All arrays have a maximum of 50 elements. Set `possibly_truncated=true` when
the raw array length is exactly 50. Absence from an array must not be treated
as proof that a service or device is unavailable.

The current backend serving snapshot does not contain the raw arrays. A model
input export must include:

```text
unique_id
name
latitude
longitude
procedure_arr
capability_arr
equipment_arr
specialties_arr
specialties_std
source/version metadata
```

Use `equipment_arr`; `equipments_arr` is not a source column.

The confirmed source table is
`workspace.cardinal_virtues.model_facilities` (plural). It has 9,989 rows and
108 columns.

## 3. Four independent tag namespaces

Use explicit namespaces so that concepts from different layers cannot be
accidentally joined:

```text
action:MAxO:0000602
proc:diagnostic:...
cap:service_offered:...
eq:diagnostic:...
specialty:...
context:...
```

### 3.1 Clinical action tags

Canonical action ID:

```text
clinical_action
  action_id
  maxo_id
  label
  parent_action_ids
  action_category
  emergency_relevant
  source_version
```

The MAxO term is the preferred anchor because HPO diagnostic annotations and
disease annotations can point to the same action.

### 3.2 Procedure tags

Subdivide by clinical function:

```text
diagnostic_procedure
therapeutic_procedure
surgical_procedure
screening_procedure
follow_up_procedure
emergency_procedure
supportive_procedure
```

Subdivide by setting only when the source text supports it:

```text
outpatient
inpatient
emergency
critical_care
home_or_remote
unknown
```

Each procedure tag must map to an action:

```text
proc:dialysis_treatment
  action_id = MAxO renal dialysis
  evidence_role = direct_procedure
```

### 3.3 Capability tags

Do not keep one giant free-text capability class. Split into:

```text
service_offered
care_setting
critical_care
emergency_availability
diagnostic_capability
therapeutic_capability
accreditation
ownership_or_facility_type
accessibility
general_marketing
administrative
```

Only the first six categories may directly support clinical actions.

Examples:

| Raw value | Category | Clinical matching |
|---|---|---|
| `Dialysis unit on-site` | `service_offered` | direct capability |
| `24x7 emergency` | `emergency_availability` | emergency context |
| `NABH accredited` | `accreditation` | facility attribute, not condition match |
| `Private hospital` | `ownership_or_facility_type` | facility attribute |
| `Wheelchair accessible` | `accessibility` | support attribute |
| `MRI services available` | `diagnostic_capability` | direct diagnostic capability |

### 3.4 Equipment tags

Subdivide by function:

```text
diagnostic_imaging
diagnostic_monitoring
therapeutic_device
renal_device
respiratory_device
neonatal_device
critical_care_device
laboratory_device
support_device
accessibility
irrelevant_or_ambiguous
```

Each equipment value also needs an evidence role:

```text
defines_service
supports_service
context_only
irrelevant
```

Examples:

| Raw value | Equipment type | Evidence role |
|---|---|---|
| `MRI scanner` | `diagnostic_imaging` | `defines_service` when the query is MRI |
| `Dialysis machine` | `renal_device` | `supports_service` for dialysis |
| `Ventilator` | `respiratory_device` | `supports_service`; can be critical-care context |
| `Cardiac monitor` | `diagnostic_monitoring` | `supports_service` |
| `Wheelchair access` | `accessibility` | `context_only` |

`defines_service` is intentionally narrow. It applies to diagnostic equipment
such as MRI or CT when the requested service is the scan itself. It must not be
used to infer complex treatment capability.

### 3.5 Specialty tags

`specialties_std` is a routing hint:

```text
specialty:nephrology
specialty:neurology
specialty:emergency_medicine
```

Specialty evidence alone must not establish that a facility performs a
procedure or has required equipment.

## 4. Canonical element table

Materialize one row per exploded array element before clustering:

```text
model_tag_raw_element
  unique_id
  source_field
  item_index
  raw_value
  source_version
  possibly_truncated
```

Then produce:

```text
model_tag_canonical_element
  unique_id
  source_field
  item_index
  raw_value
  normalized_value
  candidate_tags
  canonical_tag
  tag_namespace
  tag_category
  evidence_role
  match_method
  confidence
  review_status
  review_notes
```

Do not destroy the raw value or item index.

## 5. Matching and clustering algorithms

The algorithms should be applied in increasing cost order. A more expensive
model should only process the unresolved remainder.

### 5.1 Deterministic normalization

- Unicode normalization, whitespace cleanup and case folding.
- Standardize British/American spelling:
  `haemodialysis` to `hemodialysis`,
  `orthopaedics` to `orthopedics`.
- Expand known abbreviations:
  `ECG`, `EKG` to `electrocardiography`;
  `CT` to `computed tomography`;
  `MRI` to `magnetic resonance imaging`.
- Remove boilerplate such as "services available" while retaining the
  original phrase for evidence.
- Detect negation and future/planned wording:
  `not available`, `planned`, `coming soon`, `referral only`,
  `at partner facility`.

### 5.2 Exact alias matching

Build a normalized alias dictionary:

```text
alias -> canonical signal -> action/category
```

Use longest-phrase-first matching to prevent `dialysis` from winning over
`peritoneal dialysis` when the latter is the meaningful concept.

### 5.3 Token and character similarity

For unresolved strings:

- token Jaccard similarity;
- character 3-gram Jaccard similarity;
- normalized Levenshtein distance;
- optional RapidFuzz `token_set_ratio`.

Set conservative thresholds, for example:

```text
auto_apply >= 0.94 and one clear winner
review     0.82-0.94
no_match   < 0.82
```

Thresholds are initial values and must be evaluated against a labeled sample.

### 5.4 TF-IDF clustering

Apply word and character TF-IDF to canonicalized values.

- Use word 1-2 grams and character 3-5 grams.
- Set `min_df` to group rare spelling variants without treating every unique
  capability sentence as its own concept.
- Run MiniBatchKMeans for first-pass grouping of large fields.
- Run Agglomerative clustering on cluster centroids or small ambiguous subsets.
- Use HDBSCAN only if noise detection is important and the dependency can be
  justified.

Cluster representatives should be reviewed rather than accepting all cluster
members automatically.

### 5.5 Weakly supervised field classification

Use a small manually labeled sample to predict:

```text
proc type
capability category
equipment type
evidence role
```

Recommended baseline:

```text
TF-IDF + logistic regression / linear SVM
```

This is appropriate for tens to hundreds of thousands of short values and is
easy to explain and review.

Use class-balanced training. Never let more than one sentence or array element
from the same facility appear in both train and test folds; group folds by
`unique_id`.

### 5.6 Semantic embeddings

Use multilingual embeddings only for values that remain unresolved after
rules and TF-IDF.

Candidate models:

```text
multilingual-e5
BGE-M3
```

Uses:

- map unseen paraphrases to canonical signals;
- retrieve candidate actions;
- cluster semantically similar capability sentences.

Embeddings should rank candidates, not approve a medical mapping by
themselves. High-risk and equipment-only mappings require rule or human
review.

### 5.7 LLM-assisted review

An LLM may classify the remaining ambiguous strings, but it must:

- return a constrained JSON schema;
- include a short justification;
- reference the original raw value;
- choose only from an allowed category/tag list;
- never create a new clinical action autonomously;
- be treated as `suggested`, never `approved`.

High-risk terms such as emergency, ICU, ventilation, dialysis, cardiology,
oncology, neonatology, and surgery require human review.

### 5.8 Multi-keyword extraction from user text

User input may contain a paragraph with several symptoms, diseases and negative
statements. The model must extract a set of candidate mentions rather than
classifying the entire paragraph as one condition.

Build an alias index from:

- HPO labels and synonyms;
- MAxO labels and exact synonyms;
- disease names from MAxO annotations;
- existing service/condition tag labels and synonyms;
- manually curated English lay terms. The current baseline does not add Chinese
  symptom aliases; the parser remains Unicode-safe for future reviewed data.

Use a phrase trie or Aho-Corasick scanner over normalized text. Prefer the
longest non-overlapping phrase at each position, then restore the original
span and offsets. This supports English word boundaries and Unicode text
without requiring whitespace between words.

Each extraction should produce:

```text
QueryMention
  text
  start
  end
  matched_label
  concept_id
  concept_type        -- symptom, disease, service
  match_method
  confidence
  negated
```

Exclude negated mentions from candidate expansion. Keep them in the trace so
the user can see why a term was not used. Apply a specificity filter to root or
very broad phenotype terms; broad matches are allowed only with low confidence
and a user-visible broad-search notice.

### 5.9 Urgency and distance weighting

Urgency is a query-level label and must not be inferred solely from distance:

```text
routine
urgent
emergency
```

Initial classification sources:

- reviewed red-flag phrases such as chest pain, breathing difficulty,
  stroke signs, severe bleeding, loss of consciousness and newborn fever;
- explicit MAxO emergency/critical-care actions;
- existing `emergency-24x7` service capability.

Run negation filtering before urgency assignment. "No chest pain" must not
raise urgency. Ambiguous or conflicting mentions should use the safer higher
urgency tier while displaying uncertainty.

The local v3 baseline increases the distance weight with urgency:

```text
routine    distance_weight = 0.50
urgent     distance_weight = 0.75
emergency  distance_weight = 0.90
```

Direct action evidence remains strongest. Procedure, capability and equipment
bridges can expand recall as weak evidence, but are capped and labelled.
Emergency weak evidence is restricted to acute-response services and hospitals
with a recorded emergency signal.

## 6. Matching MAxO to facility signals

For each action, maintain:

```text
model_action_signal
  action_id
  target_field
  canonical_signal
  synonyms
  signal_category
  evidence_role
  base_strength
  source
```

Suggested evidence strength:

| Evidence | Base tier |
|---|---|
| Explicit procedure matching an action | strong |
| Explicit service/capability matching an action | strong |
| Diagnostic equipment that defines the requested service | medium/strong |
| Supporting treatment equipment | weak/medium |
| Specialty only | hint |
| Accessibility-only equipment | irrelevant to clinical match |

Aggregate multiple fields into one facility-action match:

```text
facility_action_match
  unique_id
  action_id
  strongest_evidence_role
  evidence_tier
  supporting_field_count
  matched_signals
  source_references
  uncertainty
```

## 7. Example taxonomy rows

### Dialysis

```text
action_id: MAxO renal dialysis
procedure: dialysis treatment
capability: dialysis unit / dialysis centre
equipment: dialysis machine / reverse-osmosis system
```

### Stroke

```text
action_id: MAxO neurologic evaluation or treatment action
procedure: thrombolysis / thrombectomy
capability: stroke unit / neurointerventional services
equipment: CT / MRI / ICU / ventilator as supporting context
```

An MRI scanner alone does not establish stroke-treatment capability.

### MRI

```text
action_id: MAxO MRI
procedure: MRI scan
capability: MRI services available
equipment: MRI scanner
evidence_role: defines_service
```

## 8. Databricks Serverless execution plan

Use local files first for algorithm development and small labeled samples. Use
Databricks Serverless for the full array explosion, profiling, TF-IDF and batch
classification jobs when the raw arrays are exported.

Serverless is appropriate for:

1. Reading the source table and exploding all arrays.
2. Counting raw and normalized distinct values by field and facility.
3. Computing truncation flags from raw array sizes.
4. Running grouped train/test TF-IDF classification.
5. Producing canonical-element and facility-action candidate tables.
6. Refreshing exports consumed by the offline model.

Keep embedding generation as a separate stage. Do not introduce a GPU workload
until unresolved volume and retrieval quality justify it.

Proposed output tables in the existing schema:

```text
workspace.cardinal_virtues.model_tag_raw_element
workspace.cardinal_virtues.model_tag_canonical_element
workspace.cardinal_virtues.model_action_signal
workspace.cardinal_virtues.model_facility_action_match
workspace.cardinal_virtues.model_mapping_review_queue
```

Each table should include `source_version`, `generated_at`, and an algorithm
version. Keep reviewed overrides in a separate immutable table so reruns do
not erase human decisions.

## 9. Human review queues

Create separate review queues for:

```text
high-risk clinical actions
equipment-only matches
emergency and critical-care context
negation or partner-facility ambiguity
low-confidence automatic clustering
strings occurring in exactly 50-element arrays
```

Review should support:

```text
approve
reject
map_to_existing
create_candidate_tag
mark_irrelevant
```

Do not automatically promote an LLM or embedding suggestion to reviewed.

## 10. Evaluation and acceptance

Before using the subdivisions in search, evaluate:

- category precision on a stratified manual sample;
- cluster purity for high-frequency values;
- coverage by field (matched, uncertain, unmapped);
- precision/recall for MAxO action retrieval;
- false-positive rate for equipment-only matches;
- emergency-context recall;
- facility-level impact before and after result limits.

Minimum preparation output:

1. A canonical taxonomy with namespaces and categories.
2. A mapping from every canonical signal to an action where applicable.
3. A reviewed sample of at least 200 elements across all array types.
4. A separate holdout sample not used to tune thresholds.
5. Versioned raw/canonical tables and an unresolved review queue.

The local baseline is implemented. A larger reviewed gold set and stronger
source-level evaluation are required before treating these mappings as
production clinical logic.

## 11. Implemented Serverless workflow

The first implementation is in:

```text
model/notebooks/01_train_field_taxonomy.py
model/notebooks/02_build_maxo_mapping.py
model/notebooks/03_register_field_taxonomy.py
model/notebooks/07_build_service_catalog.py
model/resources/serverless_model_job.json
```

Submit it with the CLI:

```bash
databricks jobs run-now <JOB_ID> \
  --performance-target STANDARD \
  --no-wait
```

The job uses a Serverless Environment with pinned Python dependencies. The
Standard performance target is supplied at run time. If startup latency is
more important than cost, submit with:

```bash
databricks jobs run-now <JOB_ID> \
  --performance-target PERFORMANCE_OPTIMIZED \
  --no-wait
```

The first run writes:

```text
workspace.cardinal_virtues.model_tag_raw_element
workspace.cardinal_virtues.model_tag_canonical_element
workspace.cardinal_virtues.model_mapping_review_queue
workspace.cardinal_virtues.model_field_taxonomy_metrics
workspace.cardinal_virtues.model_action_catalog
workspace.cardinal_virtues.model_condition_action_edge
workspace.cardinal_virtues.model_action_alias
workspace.cardinal_virtues.model_facility_action_match
workspace.cardinal_virtues.model_service_catalog
workspace.cardinal_virtues.model_service_action_map
```

The model artifact is always written to the MLflow run. Set
`register_model=true` only when the caller has `CREATE MODEL` on the target
schema. The shared project schema does not currently grant that privilege.

When registration is enabled, the model name is:

```text
workspace.cardinal_virtues.model_field_taxonomy@Champion
```

## 12. Service input and compatibility

The service-input path uses two product-facing tables:

### `model_service_catalog`

```text
service_id
service_label
aliases
service_type
service_group
facility_count
reference_kind
parent_action_ids
primary_action_id
urgency_level
service_contexts
source
run_version
generated_at
action_mapping_status
```

The catalog combines:

1. service-level rows from `ref_service_tags`;
2. MAxO actions not covered by a reference service tag but already linked to
   facility evidence.

### `model_service_action_map`

```text
service_id
action_id
action_label
relation_type
priority
confidence
run_version
generated_at
```

Reference service tags are linked to MAxO actions by exact normalized aliases.
Action-only services receive a primary self-link.

The local preflight covers 54 service-level reference tags: 18 map through
exact action aliases and 13 through reviewed manual overrides. The remaining 23
are capability-only or still unmapped and stay valid catalog entries without an
action row. See
`audit/service_catalog_mapping_preview_2026-11-21.json`.

Runtime lookup:

```text
service text
→ model_service_catalog
→ model_service_action_map
→ model_facility_action_match
→ eligible facilities
```

Service input remains supported for existing clients and the frontend emergency
route. It is secondary to the condition-input model, and service-level urgency
does not override condition urgency in condition mode.

## 13. Condition-input local baseline

Version: `condition-service-local-v4`.

The local API now supports symptom/disease text as the primary input. Runtime
order is:

```text
condition text
→ urgency from the condition text
→ model_condition_action_edge
→ model_service_action_map
→ model_facility_action_match
→ weak facility text bridge (procedure / capability / equipment)
→ high-recall candidate pool
→ structured-evidence reranker
→ urgency-aware distance contribution
```

The condition-to-action mapping is deterministic and based on normalized
condition labels, curated English lay aliases, exact non-overlapping phrase
matches, related-condition expansion, developer-curated treatment-retrieval terms and
existing clinical tags. Urgency is calculated before any service expansion;
service-level urgency must not override the condition-derived urgency.

Direct facility action evidence is prioritized. When direct action coverage is
sparse, exact symptom/disease synonyms found in facility procedure, capability
or equipment text may be used as weak evidence. Weak evidence is capped below
direct evidence, uses the matching reference-tag service for traceability, and
must be labelled in both API and UI responses.

Condition searches rank hospitals only; specialist clinics are excluded. An
emergency weak candidate must also have a recorded 24/7 emergency signal.

For emergency inputs, weak evidence is restricted to acute-response service
tags such as emergency care, ICU, acute imaging, ECG/echo and vascular
intervention. Preventive vaccination evidence is excluded for active disease
queries unless the user explicitly asks about vaccination or prevention.

The local baseline also expands common conditions to related condition labels,
developer-curated treatment retrieval terms and existing clinical tags. Examples include
pneumonia → chest X-ray / CT / pulmonary function, chest pain →
ECG / echocardiography / angiography, and falls → fracture-trauma / X-ray /
CT / physiotherapy. These are weak retrieval hints and must not be presented as
diagnostic rules or treatment plans.

The API keeps `queryContext.service` populated with the matched condition name
for older UI components and returns the full trace in
`queryContext.condition` and `queryContext.services`. It also exposes optional
facility phone and website fields for the current frontend.

The second-stage reranker scores text match, evidence specificity/corroboration
and distance separately. It preserves the urgency distance weights:

```text
routine:   text 0.35, evidence 0.15, distance 0.50
urgent:    text 0.20, evidence 0.05, distance 0.75
emergency: text 0.08, evidence 0.02, distance 0.90
```

At most 200 candidates enter reranking per radius. Weak evidence is capped at
75/100 in the evidence-quality feature.
