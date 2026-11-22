# Local condition-input API

This API loads a frozen cloud-model snapshot from
`model/artifacts/cloud_snapshot` and uses the existing local facility cache for
location and coordinates.

Current version: `condition-service-local-v3`.

The primary interface accepts a paragraph containing symptoms and/or diseases:

```text
condition text
→ urgency detection
→ condition/action mapping
→ service candidates
→ direct facility action evidence
→ weak procedure/equipment/capability facility evidence
→ urgency-aware distance ranking
```

Urgency is computed once from the user's condition text before the service map.
Service metadata does not override condition urgency in this mode.

Run:

```bash
backend/.venv/bin/uvicorn model.local_api.main:app \
  --host 127.0.0.1 --port 8002
```

Then start the frontend with:

```bash
cd web
VITE_API_BASE=http://127.0.0.1:8002 pnpm dev --host 127.0.0.1 --port 5175
```

Open `http://127.0.0.1:5175`.

The score is:

```text
final =
100 * ((1 - distance_weight) * condition_evidence_relevance
       + distance_weight * normalized_distance)
```

`distance_weight` is 0.50 for routine, 0.75 for urgent and 0.90 for emergency
services.

Evidence has two tiers:

- Direct: condition/action edges combined with facility action matches.
- Weak: condition synonyms, related-condition labels, treatment-retrieval
  terms or clinical tags found in `procedure_arr`, `capability_arr` or
  `equipment_arr`, mapped through the matching service/tag.

Weak retrieval also expands through developer-curated baseline treatment profiles. For
example, pneumonia can retrieve chest X-ray/CT and pulmonary-function evidence,
chest pain can retrieve ECG/echo/angiography evidence, and falls can retrieve
fracture/trauma, X-ray, CT and physiotherapy evidence. These related terms are
retrieval hints, not treatment plans or diagnostic rules.

Weak evidence is capped and labelled in the API and UI. It expands facility
coverage but does not establish a diagnosis, clinical quality, or current
availability.

Safety restrictions in the local baseline:

- For `emergency` inputs, weak evidence is restricted to acute-response service
  tags such as emergency care, ICU, CT/MRI, ECG/echo, angiography,
  angioplasty, blood bank, cardiac surgery and neurosurgery.
- Emergency candidates must also have a recorded 24/7 emergency signal.
- Preventive `Vaccination` evidence is excluded for active symptom/disease
  queries unless the user explicitly asks for vaccination or prevention.
- Condition searches rank hospital records only; specialist clinics are
  excluded.

Endpoints:

```text
GET  /api/health
GET  /api/conditions?q=chest
GET  /api/locations?q=Mumbai
POST /api/recommendations
```

Example request:

```json
{
  "conditionText": "severe chest pain and shortness of breath",
  "locationText": "Mumbai",
  "radiusKm": 25,
  "limit": 10
}
```

For backward compatibility, service-only clients may still send
`{"serviceText": "MRI", ...}`. Condition input takes precedence when both fields
are present.

Condition responses also populate `queryContext.service` with the matched
condition name so older frontend components can keep rendering. The full
condition-to-service trace is returned in `queryContext.condition` and
`queryContext.services`. Facility results include optional `phone` and
`website` fields used by the newer frontend.

`radiusKm` is accepted as a frontend contract field so selection and request
payloads remain explicit. The current backend may search wider than the user’s
display cap so the frontend can offer a one-click widening action; the browser
applies the selected radius when rendering results.
