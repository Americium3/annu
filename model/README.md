# CarePath Condition-to-Hospital Model

Status: **local condition-input baseline implemented and connected to the web
frontend**

Current local runtime version:

```text
condition-service-local-v4
```

The current model accepts symptoms or disease names, determines urgency from
that text, maps the condition to related clinical actions/services, and ranks
facilities using cited facility evidence plus urgency-weighted distance.

This is a discovery and comparison tool. It is not a diagnosis, a treatment
plan, or proof that a service is currently available.

## Quick start

Start the local API:

```bash
backend/.venv/bin/uvicorn model.local_api.main:app \
  --host 127.0.0.1 --port 8002
```

Start the GitHub frontend against it:

```bash
env VITE_API_BASE=http://127.0.0.1:8002 \
  pnpm --dir web dev --host 127.0.0.1 --port 5175
```

Open `http://127.0.0.1:5175`.

Health check:

```bash
curl http://127.0.0.1:8002/api/health
```

## Model interfaces

### Primary input

```json
{
  "conditionText": "pneumonia",
  "locationText": "Bhubaneswar, Odisha",
  "radiusKm": 25,
  "limit": 10
}
```

`conditionText` can contain one or more symptoms or diseases. The baseline
symptom alias set is English-only and supports comma/conjunction-separated
concepts and clause-aware negation.

Examples:

```text
severe chest pain and shortness of breath
no chest pain, fever for three days
falls
```

### Compatibility input

Service-only clients, including the frontend emergency route, may send:

```json
{
  "serviceText": "emergency",
  "locationText": "Mumbai",
  "coordinates": {
    "latitude": 19.076,
    "longitude": 72.8777
  }
}
```

`conditionText` takes precedence when both input fields are present.

### Output

The response includes:

- canonical matched conditions and inferred related conditions;
- treatment-retrieval terms and related clinical tags;
- service candidates and route type;
- facility rank, score and distance;
- direct versus weak evidence;
- exact facility text quotes, source links and uncertainty;
- optional phone and website for frontend actions.

For frontend compatibility, condition responses also populate
`queryContext.service.displayName` with the matched condition name. The full
trace remains in `queryContext.condition` and `queryContext.services`.

## Runtime pipeline

```text
condition text
→ urgency detection
→ condition identification and related-condition expansion
→ action and service expansion
→ direct facility action evidence
→ weak procedure/capability/equipment evidence
→ hospital eligibility and safety filters
→ stage 1 high-recall candidate pool
→ stage 2 structured evidence reranker
→ ranking and evidence selection
```

### 1. Urgency before service mapping

Urgency is calculated once from the original condition input:

```text
routine
urgent
emergency
```

Negation is clause-aware. For example, `"no chest pain, fever"` uses Fever but
not Chest pain for urgency.

Distance weights:

| Urgency | Distance weight |
|---|---:|
| Routine | 0.50 |
| Urgent | 0.75 |
| Emergency | 0.90 |

Condition urgency is not overridden by service-level urgency.

### 2. Condition identification

The deterministic resolver uses:

- normalized HPO/MAxO condition labels;
- curated English lay terms;
- longest non-overlapping phrase matches;
- clause-aware negation;
- fuzzy fallback only for short, close labels.

It returns up to four direct condition matches and up to sixteen inferred
related conditions.

Examples of related-condition expansion:

```text
Pneumonia → subtypes/variants with chest imaging, PFT or infectious-disease actions
Chest pain → pleuritic chest pain
Stroke → ischemic/lacunar/MCA stroke
Falls → frequent falls
```

Related-condition evidence is weaker than an exact condition match.

### 3. Condition to service/action mapping

Relations come from `condition_action_edge` and are weighted by predicate:

```text
treats                           1.00
investigates                     0.90
is_observable_through            0.65
is_prenatally_observable_through 0.50
prevents                         0.40
```

Contraindicated, no-benefit and unknown relations are excluded.

Because common conditions often only map to generic actions such as
`clinical assessment`, the model also uses developer-curated treatment-retrieval
profiles:

| Condition | Related retrieval examples |
|---|---|
| Pneumonia | chest X-ray, chest CT, PFT, pulmonology, respiratory infection |
| Chest pain | ECG, echocardiography, angiography, angioplasty |
| Fever | infection, general physician, blood test, pathology |
| Falls | fracture, trauma, X-ray, CT, physiotherapy |
| Stroke | stroke unit, thrombolysis, thrombectomy, neurointensive care |
| Asthma | spirometry, pulmonary function, bronchodilator |
| Diabetes mellitus | HbA1c, insulin, endocrinology, blood sugar |
| Abdominal pain | abdominal ultrasound/CT, endoscopy, gastroenterology |

These terms are retrieval hints, not clinical treatment plans.

The resolver can also map conditions to existing clinical tags such as
`fever-infections`, `asthma-copd`, `stroke`, `diabetes`, `fracture-trauma` and
`heart-disease`.

### 4. Facility evidence

Evidence has two tiers.

#### Direct

A condition/action edge is joined to a facility through
`facility_action_match`.

Characteristics:

- strongest evidence path;
- uses the action relation weight and facility match strength;
- supports strong or medium confidence;
- may still require current-availability confirmation.

#### Weak

Weak evidence connects a condition to facility text through related conditions,
treatment terms or clinical tags.

Sources:

- `procedure_arr`;
- `capability_arr`;
- `equipment_arr`.

Characteristics:

- broader facility coverage;
- explicitly labelled `weak_bridge`;
- capped below direct evidence;
- cannot establish a diagnosis, capacity or current availability;
- is rejected when the service/tag is incompatible with the condition profile.

### 5. Eligibility and safety filters

For condition searches:

- only facility records categorised as `hospital` are ranked;
- specialist clinics and dental/physiotherapy clinics are excluded;
- emergency candidates require a recorded 24/7 emergency signal;
- emergency weak evidence is limited to acute-response service tags;
- vaccination-only evidence is excluded from active disease queries unless the
  user explicitly asks about vaccination or prevention;
- facilities without valid coordinates are excluded.

Emergency-specific examples:

- stroke weak evidence must contain acute stroke, stroke-unit, thrombolysis,
  thrombectomy, neurointensive or related acute context;
- chest-pain weak evidence must be linked to emergency/acute cardiac services;
- falls emergency weak evidence must reference trauma, fracture or emergency
  care.

## Two-stage ranking

### Stage 1: high-recall candidate generation

The first stage gathers every supported hospital candidate produced by:

- direct condition/action facility matches;
- related-condition action matches;
- condition text and treatment-term evidence;
- related clinical tags;
- hospital and emergency eligibility filters.

For each radius, candidates receive a preliminary evidence-and-distance score.
The best 200 are passed to stage 2. This avoids returning distance-only
facilities before evidence quality is considered.

### Stage 2: structured evidence reranking

The second stage computes three normalized features:

| Feature | Meaning |
|---|---|
| Text match | Combined direct/weak condition relevance |
| Evidence quality | Directness, route specificity, field, strength, corroboration and source count |
| Distance | Normalized distance within the selected radius |

Final weights depend on urgency:

| Urgency | Text | Evidence | Distance |
|---|---:|---:|---:|
| Routine | 0.35 | 0.15 | 0.50 |
| Urgent | 0.20 | 0.05 | 0.75 |
| Emergency | 0.08 | 0.02 | 0.90 |

The final score is:

```text
final_score =
  100 × (
    text_weight × text_match
    + evidence_weight × evidence_quality
    + distance_weight × normalized_distance
  )
```

Weak evidence is capped at 75/100 in the evidence-quality feature. Direct action
evidence receives a higher specificity floor and can reach 100.

The API returns:

```text
metadata.candidatePoolSize
metadata.rerankedCount
facility.reranking.textScore
facility.reranking.evidenceScore
facility.reranking.distanceScore
facility.reranking.totalScore
facility.reranking.weights
facility.reranking.bestEvidenceRef
facility.reranking.bestEvidenceText
facility.reranking.stageOneRank
facility.reranking.stageOneScore
```

The result order is by descending reranked score, then evidence quality,
distance and facility name.

The score measures evidence-and-distance match only. It does not measure
clinical quality, safety, health outcomes, wait time or current capacity.

## Data snapshot

The local API uses the frozen files in `artifacts/cloud_snapshot/` plus the
local facility cache in `backend/.cache/snapshot.pkl`.

Current local scale:

| Asset | Count |
|---|---:|
| Condition concepts | 17,940 |
| Condition/action edges | 22,098 |
| Facility text evidence records | 125,836 |
| Product services | 326 |
| Service/action links | 308 |
| Facility/action matches | 6,890 |
| Facilities with any action match | 3,036 |

Pinned ontology inputs:

```text
MAxO: 59b5d75a454fdf6dc06e237fdab92c5b928d4bd3
MAxO annotations: 42edd966faac5229ce7c35fc3848f2e6b3d45bda
HPO: v2026-09-01
```

The field taxonomy model is
`workspace.carepath_model.model_field_taxonomy@Champion`, version 3. Its
0.9818 macro-F1 is agreement with deterministic weak labels, not independent
clinical accuracy.

## Local API

```text
GET  /api/health
GET  /api/conditions?q=chest
GET  /api/services
GET  /api/locations?q=Mumbai
POST /api/recommendations
```

Example:

```bash
curl -X POST http://127.0.0.1:8002/api/recommendations \
  -H 'Content-Type: application/json' \
  -d '{
    "conditionText": "pneumonia",
    "locationText": "Bhubaneswar, Odisha",
    "limit": 10
  }'
```

See [local_api/README.md](local_api/README.md) for the HTTP interface and
[TAXONOMY_AND_ALGORITHMS.md](TAXONOMY_AND_ALGORITHMS.md) for algorithm details.

## Code map

```text
src/carepath_model/condition_service.py
  condition aliases, related-condition expansion, treatment profiles,
  clinical tags and condition-to-service routes

src/carepath_model/query.py
  urgency detection, clause-aware negation and distance weights

local_api/main.py
  evidence indexing, facility matching, safety filters, scoring and HTTP API

notebooks/
  Serverless field-taxonomy, MAxO, service-catalog and export jobs

artifacts/cloud_snapshot/
  frozen local condition/action, service and facility-action data
```

## Current validation

```text
unit tests:                    21
frontend typecheck/build:      passing
desktop browser test:          passing
390px mobile browser test:     passing
emergency browser test:        passing
repeated condition queries:    deterministic
```

Observed behavior:

- Falls in Bhubaneswar returns hospital records through fracture/trauma,
  X-ray, CT and emergency evidence rather than relying on the word “falls” in a
  facility quote.
- Pneumonia in Bhubaneswar can retrieve chest imaging/PFT evidence.
- Chest pain expands to ECG, echo, angiography and angioplasty.
- Stroke emergency results are limited to hospitals with an emergency signal
  and acute stroke/critical-care evidence.
- Condition results expose first-stage candidate-pool size and second-stage
  `textScore`, `evidenceScore`, `distanceScore`, weights and best evidence.

## Known limitations

- Treatment profiles are a developer-curated baseline, not clinically reviewed
  or comprehensive medical knowledge.
- Weak evidence can still produce low-confidence but imperfect matches.
- Source URLs are generally attached at facility-record level; an exact
  quote-to-URL pointer is not available for every extracted quote.
- The condition vocabulary is deterministic and does not yet use a full
  ontology synonym graph or validated semantic embedding.
- No field confirms current bed availability, wait time or real-time emergency
  capacity.
- The model has not passed a clinical gold-set evaluation and must not be used
  as medical advice.

## Next validation work

1. Build a reviewed symptom/disease gold set covering common conditions,
   multiple languages, negation and emergency cases.
2. Measure condition-to-service recall and facility precision separately.
3. Audit weak-evidence profiles for false positives and safety exclusions.
4. Add quote-level source attribution.
5. Refresh the frozen cloud snapshot after algorithm or data changes.
