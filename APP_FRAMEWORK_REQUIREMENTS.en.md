# Healthcare Recommendation App Framework Requirements

> Version: 0.2  
> Date: 2026-11-21  
> Status: Technical selection and requirements definition; no implementation has started

## 1. Product Goal

Build a non-technical-user-facing healthcare facility recommendation app with an interaction model similar to Yelp or Dianping.

The user supplies two inputs:

1. **Service needed**: dialysis, emergency C-section, NICU, cardiac surgery, MRI, burn care, and similar services.
2. **User location**: city, district, PIN code, or latitude/longitude.

The system returns the best healthcare facility candidates and explains:

- Why the facility is believed to offer the requested service.
- Why it is a better option than the other candidates.
- Which source fields, text segments, and source URLs support the decision.
- Which information is missing, conflicting, or uncertain.

The product must not describe a service that a website claims a facility offers as a confirmed available service.

## 2. Framework Goals and Constraints

- The app must not be tied to Databricks Apps; the frontend, API, and recommendation service must be independently deployable.
- Prefer raw facility data from Databricks Unity Catalog.
- The browser must never hold Databricks tokens or other backend credentials.
- Recommendations must be explainable rather than returning an opaque score.
- Every important judgment must be traceable to a field, source quote, and source URL.
- Version 1 is read-only and excludes user accounts, reviews, appointments, or write-back.
- The UI is mobile-first and supports a list-plus-map desktop layout.
- The frontend must support an OpenAPI contract and mock data so UI development can proceed before the backend is complete.
- The framework must allow the rule-based ranker to be replaced by an ML ranking model without rewriting the frontend.

## 3. Recommended Technical Framework

### 3.1 Frontend

| Area | Recommended choice |
|---|---|
| Framework | React 19 + TypeScript |
| Build tool | Vite |
| Styling | Tailwind CSS |
| Base UI | shadcn/ui + Radix UI primitives |
| Icons | Lucide React |
| Server state | TanStack Query |
| Forms and validation | React Hook Form + Zod |
| Routing | React Router |
| Map | Leaflet + React Leaflet |
| Unit tests | Vitest + Testing Library |
| End-to-end tests | Playwright |
| Package manager | pnpm |

React/Vite is preferred over Next.js because:

- The product is a highly interactive search application and does not depend on SEO or server-side rendering.
- The frontend can be built as static assets and deployed to a CDN, Databricks Apps, or a self-managed container.
- Data access and recommendation logic remain in a separate API service with clear responsibilities.
- SPA development, testing, and local mocking are simpler.

### 3.2 API and Recommendation Service

| Area | Recommended choice |
|---|---|
| API framework | FastAPI |
| Language | Python 3.12+ |
| Data models | Pydantic |
| Databricks access | Databricks SQL Connector for Python / Databricks SDK |
| Ranking | Explainable rules and weighted scores; optional MLflow Model Serving later |
| Caching | In-process TTL cache initially; add Redis only when needed |
| API documentation | OpenAPI with generated TypeScript clients |

FastAPI responsibilities:

- Normalize service intents and locations.
- Query the Databricks SQL Warehouse.
- Run candidate filtering, distance calculations, and explanatory ranking.
- Assemble evidence, citations, and uncertainty information.
- Keep all SQL and model-service credentials out of the browser.

### 3.3 Databricks Data Layer

| Area | Recommended choice |
|---|---|
| Data warehouse | Databricks SQL Warehouse |
| Governance | Read-only Unity Catalog tables or restricted views |
| Raw facility source | `databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities` |
| Geographic reference | India Post PIN directory and PIN centroids |
| Regional health context | NFHS-5 district indicators, optional |

Primary Version 1 inputs:

- `facilities`
- `india_post_pincode_directory`
- `pincode_centroids`
- `nfhs_5_district_health_indicators` for regional context only

Raw service arrays and numeric-like fields must be parsed. A non-empty field must not be treated as a reliable structured fact.

## 4. Recommended Architecture

```text
┌──────────────────────────────────────────────┐
│ React + TypeScript + Vite                    │
│ Search / result list / map / detail / proof  │
└──────────────────────┬───────────────────────┘
                       │ HTTPS + OpenAPI
┌──────────────────────▼───────────────────────┐
│ FastAPI                                       │
│ Normalize / query / rank / explain / cite    │
└───────────────┬──────────────────┬────────────┘
                │                  │
┌───────────────▼─────────┐  ┌─────▼────────────────┐
│ Databricks SQL Warehouse│  │ MLflow Model Serving │
│ Raw and feature tables  │  │ Optional later       │
└─────────────────────────┘  └──────────────────────┘
```

Databricks Apps is only an optional hosting target and is not an architectural dependency.

## 5. Component Framework

### 5.1 Pages

- `/`: search landing page
- `/search`: result list and map
- `/facilities/:id`: shareable facility detail page

Facility details may initially use a drawer and move to a route when sharing and deep links are required.

### 5.2 Frontend Business Components

- `AppShell`
- `SearchHeader`
- `ServiceCombobox`
- `LocationInput`
- `LocationResolutionCard`
- `SearchActions`
- `RecommendationList`
- `FacilityCard`
- `FacilityMap`
- `MapResultMarker`
- `FacilityDetailDrawer`
- `EvidenceList`
- `EvidenceQuote`
- `ScoreBreakdown`
- `ConfidenceBadge`
- `LocationQualityBadge`
- `UncertaintyNotice`
- `SourceLinkList`
- `EmptyState`
- `ErrorState`
- `LoadingSkeleton`
- `MobileListMapSwitch`

### 5.3 Required Result Card Content

- Rank and total recommendation score.
- Facility name, type, and operator type.
- Address, district, and distance.
- Two or three of the strongest service evidence quotes.
- Fields in which the evidence appeared.
- Source URLs.
- Location confidence.
- Capacity, equipment, or web-activity signals as secondary evidence.
- A clear uncertainty notice.

## 6. User Interaction Flow

1. The user enters a service.
2. The service input suggests synonyms and normalized intents.
3. The user enters a city, district, PIN code, or selects coordinates on the map.
4. The app displays the resolved location and lets the user correct ambiguity.
5. The user submits the query.
6. The system returns 10–20 candidates.
7. Selecting a result in the list highlights its marker on the map and vice versa.
8. The user opens facility details to see complete evidence and sources.
9. The user can copy the explanation or return to modify the search.

## 7. API and IO Contract Requirements

FastAPI should generate OpenAPI, which is then used to generate a TypeScript client.

### 7.1 IO Interaction Layers

| Interaction | Input | Output |
|---|---|---|
| User to frontend | Service text, city, district, PIN code, coordinates, radius, filters | Resolved query and ranked result UI |
| Frontend to API | JSON request over HTTPS | JSON response containing ranking, evidence, sources, and uncertainty |
| API to Databricks | Parameterized read-only SQL | Candidate rows, evidence rows, source rows, and location data |
| API to ranking model | Structured candidate features | Rank, total score, score breakdown, and feature contributions |
| Frontend to map | Result coordinates, rank, confidence, and selected facility ID | Map markers, selected marker, distance overlay, and map-to-list linkage |

The first release uses synchronous HTTP requests. Streaming or WebSocket communication is unnecessary unless recommendation generation later exceeds normal request timeouts.

### 7.2 Endpoint Summary

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/services/search` | `GET` | Service autocomplete and normalization |
| `/api/locations/search` | `GET` | City, district, PIN, and coordinate disambiguation |
| `/api/recommendations` | `POST` | Ranked facility recommendations |
| `/api/facilities/{facility_id}` | `GET` | Complete facility evidence and source details |
| `/api/health` | `GET` | API, warehouse, and optional model health |

The recommendation endpoint is read-only even though it accepts a JSON body.

### 7.3 Service Search

`GET /api/services/search?q=<query>&limit=<n>`

Returns:

- Canonical service ID and display name.
- Matched synonyms and abbreviations.
- Candidate service intents when the input is ambiguous.
- Resolution confidence.

The UI should debounce service lookup and must not call the SQL Warehouse on every keystroke.

### 7.4 Location Search

`GET /api/locations/search?q=<query>&limit=<n>`

Returns:

- City and district candidates.
- State and PIN candidates.
- Latitude and longitude.
- Match type and confidence.

The user must explicitly correct ambiguous locations before a recommendation is requested. Browser geolocation requires explicit user permission and a manual fallback.

### 7.5 Recommendation Query

`POST /api/recommendations`

The request contains:

- `service`
- `location`
- `radius_km` (optional)
- `limit`
- `filters` (optional)
- `ranking_mode` (optional)

Supported ranking modes should include:

- `best_match`
- `nearest`
- `most_evidence`

### 7.6 Facility Details

`GET /api/facilities/{facility_id}`

Returns complete facility details, all supporting and contradicting evidence, all source references, location quality, data completeness, and uncertainty.

### 7.7 Health Check

`GET /api/health`

Returns the status of the API, SQL Warehouse connection, and optional model endpoint.

### 7.8 URL and UI State

Shareable searches should preserve the following in the URL when practical:

- Canonical service.
- Original and resolved location.
- Radius.
- Ranking mode.
- Selected facility.

Map viewport state may remain local and does not need to be shareable.

## 8. Core Data Contracts

### 8.1 Contract Conventions

- JSON uses `snake_case`.
- Coordinates are numeric WGS84 latitude/longitude values.
- Distances use kilometers.
- Scores use a display-friendly `0–100` range unless a field explicitly states otherwise.
- Timestamps use ISO 8601.
- Nullable fields are represented explicitly as `null`.
- Stable machine-readable enum codes are separate from user-facing messages.
- Raw evidence is never replaced by generated text.
- One API response should provide enough data to render a result card without an N+1 request per facility.

### 8.2 RecommendationRequest

- `service_text`
- `service_id` (optional when already selected)
- `location_type`: `city`, `district`, `pincode`, or `coordinates`
- `location_value`
- `latitude` / `longitude` for coordinate input
- `radius_km`
- `limit`
- `filters`
- `ranking_mode`

### 8.3 QueryContext

The response must show what the system understood:

- `request_id`
- `service.canonical_id`
- `service.display_name`
- `service.matched_synonyms`
- `service.confidence`
- `location.type`
- `location.input_value`
- `location.resolved_name`
- `location.city`
- `location.district`
- `location.state`
- `location.pincode`
- `location.latitude`
- `location.longitude`
- `location.confidence`
- `search_parameters.radius_km`
- `search_parameters.limit`
- `search_parameters.filters`

### 8.4 RecommendationResponse

Top-level response fields:

- `query_context`
- `results`
- `metadata`

Response metadata must include:

- `request_id`
- `ranking_version`
- `generated_at`
- `total_candidates`
- `returned_count`
- `is_partial_result`
- `applied_filters`
- `execution_time_ms`
- `warnings`

### 8.5 FacilityRecommendation

Required fields:

- `rank`
- `facility_id`
- `facility_name`
- `facility_type`
- `operator_type`
- `address`
- `district`
- `state`
- `pincode`
- `latitude` / `longitude`
- `distance_km`
- `total_score`
- `confidence_level`
- `recommendation_summary`
- `score_breakdown`
- `evidence`
- `sources`
- `location_quality`
- `data_completeness`
- `uncertainty`

`total_score` and `confidence_level` are distinct concepts. A facility can have a high relative rank while still having low evidence confidence.

### 8.6 EvidenceItem

Every evidence object must include:

- `evidence_id`
- `field_name`
- `matched_service`
- `matched_value`
- `quote`
- `match_type`: `exact`, `synonym`, or `semantic`
- `polarity`: `positive`, `negative`, or `uncertain`
- `strength`: `strong`, `medium`, or `weak`
- `source_id`

Negative statements such as “cardiac surgery is not available” must be retained as negative evidence and must never contribute a positive service score.

### 8.7 SourceReference

Every source must include:

- `source_id`
- `url`
- `domain`
- `source_type`: `official_site`, `government`, `directory`, `social_media`, or `unknown`
- `title`
- `retrieved_at`
- `supports_claims`: a list of related evidence IDs

The frontend must display the source domain and distinguish official, government, directory, and social-media sources.

### 8.8 ScoreBreakdown

Required score components:

- `service_match_score`
- `evidence_score`
- `source_score`
- `distance_score`
- `location_quality_score`
- `capacity_score`
- `penalty_score`
- `total_score`

The response must expose the component scores and their weights so the UI can explain why one facility ranks above another. Distance must not override a lack of service evidence.

### 8.9 Uncertainty

Required fields:

- `level`: `high`, `medium`, or `low`
- `reason_codes`: structured machine-readable reasons
- `messages`: user-facing explanations
- `missing_fields`
- `conflicts`

The initial reason-code vocabulary should include:

- `LOCATION_PIN_CONFLICT`
- `LOW_PIN_CONFIDENCE`
- `SERVICE_ONLY_IN_FREE_TEXT`
- `NEGATED_SERVICE_CLAIM`
- `NO_OFFICIAL_SOURCE`
- `CAPACITY_UNPARSEABLE`
- `STALE_SOURCE`
- `DUPLICATE_FACILITY_CLUSTER`

### 8.10 Minimum Output Guarantee

The first usable release must always provide:

1. The service and location interpretation.
2. Ten to twenty recommendation candidates when available.
3. A total score and component-score breakdown for each candidate.
4. At least one raw evidence item and source for each evidence-backed recommendation.
5. Location confidence and uncertainty for each candidate.
6. Enough information for the UI to distinguish a strong recommendation, a normal match, and a result requiring manual confirmation.

## 9. Recommendation Model Framework

### 9.1 Phase 1: Explainable Rule-Based Ranking

Candidate pipeline:

1. Normalize the service and location.
2. Generate candidates using service keywords.
3. Filter by geographic range.
4. Calculate service, location, source, and completeness scores.
5. Apply penalties for negated semantics, geographic conflicts, and anomalies.
6. Rank candidates and generate explanations.

Initial scoring dimensions:

| Dimension | Purpose |
|---|---|
| Specialty match | Strong evidence |
| Procedure match | Strong evidence |
| Equipment match | Strong evidence, especially for MRI and dialysis |
| Capability description | Medium-strength evidence |
| Multi-field corroboration | Increases confidence |
| Number and type of sources | Increases confidence |
| Distance | Ranking factor |
| Location confidence | Ranking factor and risk notice |
| Scale fields | Secondary signal only; never a hard filter |

### 9.2 Phase 2: Machine-Learning Ranking

A learning-to-rank, LambdaMART, or MLflow model can be introduced later, but its output must include:

- Total score.
- Feature contributions or a readable score breakdown.
- Cited raw evidence.
- Model version.
- Uncertainty.

The frontend API contract must remain stable when the model changes.

## 10. Data Access and Security

- The browser must never access the Databricks SQL Warehouse directly.
- Databricks tokens must be available only to the API service.
- Local development uses environment variables; deployments use a secret manager.
- If the app is deployed independently, backend components hold the credentials.
- If the app is later hosted on Databricks Apps, platform-injected identity may be used, but application logic must not depend on it.
- Queries are read-only and should use controlled views or a restricted service principal.
- Logs must never contain tokens, complete database URLs, or other credentials.

## 11. Deployment Framework

### 11.1 Recommended: One Container or Two Services

Options:

- **One container**: FastAPI serves the API and the built React static assets.
- **Two services**: React is deployed to a CDN and FastAPI runs as a separate service.

Neither option depends on Databricks Apps.

### 11.2 Optional Hosting Targets

- A general container platform.
- A managed cloud runtime.
- A self-managed virtual machine.
- Databricks Apps as a hosting target only.

### 11.3 Environment Separation

- `local`
- `dev`
- `production`

Environment differences are injected through configuration. Workspace IDs, warehouse IDs, and credentials must never be hard-coded.

## 12. Non-Functional Requirements

- Mobile-first; the core flow must work at a 390px viewport width.
- Desktop uses a two-column result-list and map layout.
- Search should return in under three seconds when the SQL Warehouse is warm.
- Map and list views paginate results instead of rendering every facility at once.
- Every interaction provides loading, empty, error, and partial-data states.
- Text and color must meet WCAG contrast requirements.
- Important controls and map markers must support keyboard interaction.
- Source links must be accessible and display the source domain.
- No fake ratings, patient reviews, or unsupported certification claims.

## 13. Framework Comparison

| Option | Advantages | Disadvantages | Decision |
|---|---|---|---|
| React/Vite + FastAPI | Clear separation, natural Python ranking service, flexible deployment | Requires maintaining an application boundary | **Recommended** |
| Next.js full stack | Single repository, integrated routing and API | Python data/model work requires another service or cross-language code | Viable alternative |
| Databricks AppKit | Fast Databricks integration and generated types | Stronger platform coupling and less portable | Alternative |
| Streamlit | Fast early prototypes | Difficult to achieve a polished Yelp-style experience | Prototype only |
| Gradio | Fast form prototype | Limited UI and map customization | Not recommended |

## 14. Suggested Repository Layout

```text
medical-recommender/
├── web/                         # React + Vite
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── features/
│   │   ├── api/
│   │   ├── schemas/
│   │   └── styles/
│   └── tests/
├── api/                         # FastAPI
│   ├── app/
│   │   ├── routes/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── ranking/
│   │   └── schemas/
│   └── tests/
├── contracts/
│   └── openapi.json
├── deploy/
└── docs/
```

## 15. Phased Delivery

### Phase 1: Frontend Framework

- Complete the search page, result list, map, facility cards, and detail drawer.
- Use a mock API with fixed request and response contracts.
- Complete mobile and desktop layouts.

### Phase 2: Read-Only Data API

- Connect to the Databricks SQL Warehouse.
- Implement service and location resolution.
- Return real candidates and raw evidence.

### Phase 3: Recommendation Scoring

- Add distance, service evidence, source quality, location confidence, and uncertainty.
- Expose a readable score breakdown.

### Phase 4: Deployment and Verification

- Choose independent hosting or Databricks Apps as the host.
- Complete permissions, logging, error handling, and end-to-end tests.

## 16. Acceptance Criteria

- A user can request a recommendation using a service plus a city, district, PIN code, or coordinates.
- Results show both a list and a map on desktop and allow switching between them on mobile.
- Every recommendation includes its score, evidence fields, quotes, and sources.
- Low confidence, missing data, and conflicting information are explicitly shown.
- The frontend never has access to Databricks credentials.
- Replacing the ranking model does not require changing the frontend request or response structures.
- The app can be deployed independently of Databricks Apps.

## 17. Open Decisions

1. Should the frontend use the recommended React/Vite stack, or would Next.js be preferred for a full-stack implementation?
2. Is it acceptable to begin frontend development with mock data?
3. Should maps use OpenStreetMap/Leaflet, or is Mapbox required?
4. Is the app public, or available only to workspace users?
5. Does Version 1 need favorites, search history, or user feedback?
6. Will the final recommender remain an explainable SQL/rules system, or is a separately trained ML model planned?

