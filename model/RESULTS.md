# Serverless Model Run Results

## Run identity

```text
Job ID: 217503484000552
Latest successful run ID: 85282013598753
Training task run ID: 1081814336468654
MAxO task run ID: 443464005286832
Performance target: PERFORMANCE_OPTIMIZED
Registration task run ID: 966686190169319
Service catalog task run ID: 723019243157466
Latest model smoke-test run ID: 636461981523290
```

The first Standard-mode run exposed two configuration/permission issues:

1. The Serverless Environment tried to pip-install the workspace `src`
   directory without a `pyproject.toml`; the dependency was removed and source
   is loaded through `sys.path`.
2. The training model was logged to MLflow successfully, but registration in
   `workspace.cardinal_virtues` failed because the runner lacks `CREATE MODEL`.

Those were fixed by:

- using `sys.path` for the workspace source package;
- creating the user-owned `workspace.carepath_model` schema;
- registering the existing MLflow run separately from the training task.

## Training result

```text
Algorithm: field-taxonomy-weak-tfidf-v1
Training rows: 269,930
Test rows: 68,297
Classes: 27
Macro F1: 0.9818
MLflow run: 8209aa33d3e84297ad7b3777d5e81381
```

The split is grouped by `unique_id`, so a facility cannot appear in both train
and test groups.

The metric measures agreement with deterministic weak labels. It is not a
measure of clinical correctness; these labels still require manual review.

## UC model

```text
workspace.carepath_model.model_field_taxonomy@Champion
version: 3
status: READY
alias: champion
source run: 8209aa33d3e84297ad7b3777d5e81381
```

The model has an MLflow signature and is backed by run
`8209aa33d3e84297ad7b3777d5e81381`.

The registered Champion model was loaded successfully on Serverless and
predicted the expected categories for all six smoke-test examples:

```text
hemodialysis procedure       -> therapeutic_procedure
magnetic resonance procedure -> diagnostic_procedure
24x7 emergency capability    -> emergency_availability
NABH accredited hospital     -> accreditation
MRI scanner equipment        -> diagnostic_imaging
wheelchair access            -> accessibility
```

## Output tables

| Table | Rows |
|---|---:|
| `workspace.cardinal_virtues.model_tag_raw_element` | 550,675 |
| `workspace.cardinal_virtues.model_tag_canonical_element` | 550,675 |
| `workspace.cardinal_virtues.model_mapping_review_queue` | 226,164 |
| `workspace.cardinal_virtues.model_field_taxonomy_metrics` | 3 |
| `workspace.cardinal_virtues.model_action_catalog` | 1,930 |
| `workspace.cardinal_virtues.model_condition_action_edge` | 22,098 |
| `workspace.cardinal_virtues.model_action_alias` | 6,681 |
| `workspace.cardinal_virtues.model_facility_action_match` | 6,890 |
| `workspace.cardinal_virtues.model_service_catalog` | 326 |
| `workspace.cardinal_virtues.model_service_action_map` | 308 |

Service catalog result:

```text
service catalog rows: 326
service→action rows: 308
service-level reference tags: 54
reference tags with action links: 31
additional action-backed services: 272
mapped services: 303
capability-only or unmapped services: 23
```

The service catalog retains capability-only entries such as ICU, NICU,
ambulance and blood bank without forcing an incorrect MAxO action.

All action IDs in `model_action_catalog` are in the `MAXO:` namespace.
The imported ontology namespaces in `maxo.obo` were filtered out during the
corrective mapping run.

## MAxO/HPO result

```text
MAxO actions: 1,930
HPO terms parsed: 20,482
Condition/action edges: 22,098
Action aliases: 6,681
Facility/action matches: 6,890
```

Relationship distribution:

```text
phenotype / is_observable_through             19,152
phenotype / is_prenatally_observable_through   2,054
disease / treats                                 728
disease / prevents                               142
disease / unknown                                 10
disease / lack of observed response                6
disease / contraindicated                          3
disease / no_observed_benefit                      2
disease / investigates                             1
```

Pinned inputs:

```text
MAxO: 59b5d75a454fdf6dc06e237fdab92c5b928d4bd3
MAxO annotations: 42edd966faac5229ce7c35fc3848f2e6b3d45bda
HPO: v2026-09-01
```

## Facility match quality

```text
strong_exact: 6,549
context_exact: 341
distinct facilities with any action match: 3,036
distinct actions matched: 327
```

The exact matcher found 397 facilities for the generic MAxO MRI procedure
(`MAXO:0000424`) after adding conservative aliases for MRI and MRI scanner.

Review queue:

```text
review_low_confidence: 173,061
review_high_risk:      53,103
```

The large review queue is expected for the first weak-label pass. The queue must
be reduced through reviewed examples and better lexical aliases before using
this taxonomy as a clinical mapping.

## Independent accuracy review

The weak-label macro F1 is not an independent accuracy estimate. Two separate
manual reviews were completed:

### Field taxonomy

```text
Stratified sample rows: 84
Allowed-category validity: 84/84 = 100%
Manual semantic correctness: 58/84 = 69.0%
capability_arr: 24/30 = 80.0%
equipment_arr: 18/30 = 60.0%
procedure_arr: 13/21 = 61.9%
specialties_std: 3/3 = 100%
```

This sample contains 44 rule-classified and 40 model-classified rows. The
subtype taxonomy is useful for routing but not accurate enough to be the
primary service matcher.

### Service/action matching

```text
Stratified sample rows: 60
Manual correctness: 59/60 = 98.3%
strong_exact: 44/45 = 97.8%
context_exact: 15/15 = 100%
source-table weighted precision estimate: 97.9%
```

The exact action alias path is substantially more reliable than the field
subtype classifier. It remains the strongest route within the service-input
compatibility path:

```text
service text
→ canonical MAXO action
→ exact facility action evidence
→ urgency-aware distance ranking
```

Detailed review records:

- [field_taxonomy_2026-11-21.json](audit/field_taxonomy_2026-11-21.json)
- [action_match_2026-11-21.json](audit/action_match_2026-11-21.json)

## Validation priorities

Direct action evidence remains primary. Subtype predictions and related
treatment text remain secondary. Before production use, expand the
condition/service audit to at least 200 reviewed examples, including English
lay terms, multi-condition text, emergency cases and weak-evidence false positives,
then measure condition-to-service recall and end-to-end hospital precision.

## Condition-input local baseline

Local runtime version: `condition-service-local-v3`.

The local API now supports symptom/disease text before service selection:

```text
condition text
→ urgency
→ condition/action edges
→ service candidates
→ direct facility action evidence
→ weak procedure/capability/equipment evidence
→ urgency-aware distance ranking
```

Observed local snapshot:

```text
condition concepts:       17,940
condition/action edges:   22,098
facility text records:   125,836
unit tests:                   19
```

Checks completed:

- Emergency urgency is derived from condition text before service expansion.
- Clause-aware negation excludes phrases such as `no chest pain` without
  suppressing a separate fever or stroke mention.
- The baseline condition alias set is English-only; Chinese symptom aliases
  have been removed.
- Repeated requests return identical facility order and scores.
- Emergency weak evidence is limited to acute-response services.
- Emergency candidates must also have a recorded 24/7 emergency signal.
- Condition searches are limited to facility records categorised as hospitals.
- The GitHub frontend sends `conditionText` and receives condition/service
  traces, direct/weak evidence and optional phone/website fields.
- Common conditions expand to related condition labels, treatment terms and
  clinical tags (for example pneumonia → chest imaging / PFT, chest pain → ECG /
  angiography, falls → fracture-trauma / X-ray / CT).
- Emergency candidates must have a recorded emergency/critical-care signal.
- Active pneumonia queries do not use vaccination text as treatment evidence.
- Service-input requests remain backward compatible.

This baseline validates the interface, ranking mechanics and failure handling.
It does not establish clinical accuracy. Weak evidence is attribution-limited,
and current availability, capacity and wait times remain unverified.
