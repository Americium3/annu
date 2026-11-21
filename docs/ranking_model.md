# Recommendation model: phase 1 (explainable rules)

Status: implemented in `api/app/ranking/` as `rules-v0.1`. Not yet tuned. Every weight
below is a starting value, to be adjusted against an evaluation set (see
[Next steps](#next-steps)).

## Framing

This is **query-dependent search ranking**, not collaborative filtering. There are no user
accounts, interaction logs or ratings to learn tastes from. For each query (service +
location), facilities are ranked by how strongly the evidence shows they provide the
service, and how practical they are to reach.

## Pipeline

```text
query (service tag, lat/lon, radius, mode)
  │
  ├─ Stage 1: retrieval (hard filters)
  │    has evidence for the tag (any TF-IDF class) OR lists a fallback specialty
  │    facility type fits (no dentists for non-dental services, no pharmacies)
  │    within radius; widen 25 → 50 → 100 → 200 km until ≥ 10 results (warning RADIUS_WIDENED)
  │    collapse records sharing cluster_id
  │
  └─ Stage 2: scoring
       total = clamp(100 × G × F − P, 0, 100)
```

**A facility with no evidence is never shown just because it is close.**

### G: evidence gate

| Match type | G | When |
|---|---|---|
| `strong` | 1.0 | Regex match and TF-IDF probability ≥ 0.5 |
| `mention_with_specialty` | 0.8 | Mention, plus the facility lists a fallback specialty |
| `mention` | 0.6 | Regex match, low probability (named in passing) |
| `specialty_only` | 0.5 | No evidence sentence, but a fallback specialty is listed |
| `suggested` | 0.35 | TF-IDF only, no regex match |
| `specialty_query` | 1.0 | The user searched for a specialty itself |

G multiplies everything, so distance, size and source quality can't lift a weakly
evidenced facility above its gate. The specialty fallback list (`SPECIALTY_FALLBACK`) is
deliberately tight. A unit or equipment service such as dialysis, MRI or NICU has no
fallback, because listing nephrology or radiology says nothing about having the machine.

### F: weighted components (each 0–1)

| Component (API field) | Weight | Built from |
|---|---|---|
| `service_match_score` | 0.20 | Match type, plus whether a matching specialty is also listed |
| `evidence_score` | 0.20 | 0.5 × TF-IDF probability + 0.3 × fields that agree (procedure / capability / equipment / specialty) + 0.2 × sentence count (log) |
| `distance_score` | 0.30 | exp(−road_km / decay_km), road_km ≈ straight-line × 1.3 |
| `capacity_score` | 0.10 | Beds, doctors and specialties (log-scaled); **missing counts as 0.5**, implausible values are ignored |
| `source_score` | 0.10 | Official website, number of source URLs, recency of web page or social post (1-year half-life) |
| `location_quality_score` | 0.10 | `location_confidence`: high 1.0, medium 0.7, low 0.3 |

`decay_km` depends on how urgent the service is:

| Urgency | decay_km | Examples |
|---|---|---|
| emergency | 10 | C-section, delivery, NICU, burns, snakebite, stroke, trauma, 24×7 emergency, ICU |
| recurring | 15 | Dialysis, chemotherapy, radiotherapy, physiotherapy |
| routine | 20 | Default: fever, skin, ENT, dental, diabetes |
| diagnostic | 25 | MRI, CT, lab, ultrasound |
| elective | 60 | IVF, transplants, cardiac surgery, joint replacement, cataract |

### P: penalties (points, capped at 20)

| Flag | Points |
|---|---|
| `flag_coord_pin_conflict` (15.7% of facilities) | 5 |
| `flag_implausible_scale` | 5 |
| `flag_address_nothing_agrees` | 5 |
| A negated or "planned" sentence for the service ¹ | 10 |

¹ The pipeline skips negated sentences but doesn't yet export a per-facility count. The
loader reads a `negated_sentence_count` column in `facility_tag_scores.csv` once one is added.

### Confidence (separate from score)

- **high**: `strong` evidence, at least 2 corroborating fields, high location confidence,
  no coordinate–PIN conflict, no negated claim.
- **low**: `specialty_only` or `suggested` match, or low location confidence.
- **medium**: everything else.

`uncertainty.level` is the inverse (confidence high → uncertainty low). Each result carries
reason codes (`SPECIALTY_ONLY_MATCH`, `SERVICE_MENTION_ONLY`, `MODEL_SUGGESTED_MATCH`,
`NEGATED_SERVICE_CLAIM`, `LOCATION_PIN_CONFLICT`, `LOW_PIN_CONFIDENCE`, `ADDRESS_INCONSISTENT`,
`NO_OFFICIAL_SOURCE`, `STALE_SOURCE`, `CAPACITY_UNPARSEABLE`, `DUPLICATE_FACILITY_CLUSTER`),
user-facing messages and a list of missing fields.

### Ranking modes

- `best_match`: by total score.
- `nearest`: by distance, among facilities with G ≥ 0.6 (`mention` or better).
- `most_evidence`: by G × evidence score.

Ties break on distance, then `unique_id`, so results are deterministic.

## Built for data that is still changing

The cleaned tables are still being prepared, and new facilities and columns will arrive.

- **Only `unique_id`, `best_lat` and `best_lon` are required.** Every other column is
  optional. A missing column or unparseable value becomes "unknown", which scores
  **neutral**, never as bad.
- `check_schema()` and the CLI list the expected columns a table is missing, so a refresh
  that drops a column is noticed instead of silently scoring neutral.
- The Databricks loader selects only the expected columns that currently exist, and ignores
  new ones.
- New `flag_*` columns are picked up automatically. They only affect the score once given a
  penalty in `config.py`.
- New service tags inherit their group's urgency (or `routine`). New TF-IDF class values are
  treated as `mention`.
- Specialties are normalized with the pipeline's own `specialty_key`, so a raw spelling that
  first appears in a later refresh maps the same way the catalog does.
- Evidence for a facility that isn't in the facility table yet is skipped and counted in
  `stats`.

## Not used, and why

- **Ratings and reviews**: none in the dataset. Google Places ratings could be shown
  live for display only, but their terms forbid storing them. They also skew toward
  urban private hospitals, so they stay out of the score. Better candidates for a quality
  signal: NABH accreditation and PM-JAY empanelment lists (not yet checked for access).
- **Followers, likes, engagements**: these measure marketing reach, not quality. Only the
  *recency* of a social post is used, as a "still operating" signal.
- **`has_3plus_sources`**: true for 97% of facilities, so it barely tells them apart. The
  continuous `n_source_urls` is used instead.

## Next steps

1. **Evaluation set.** About 30 services × 15 locations, top 20 per query graded 0–3 by a
   clinician (or an LLM judge with the evidence shown, then spot-checked). Measure NDCG@10.
   Tune `config.py` against it.
2. **Evidence text.** The API joins `evidence_refs` (`field:item_idx`) to
   `model_evidence_items` to show quotes, and the source URLs from `source_urls`.
3. **Road distance.** Replace the 1.3 detour factor with OSRM or a similar routing engine.
4. **Phase 2: learning-to-rank.** Once the app logs calls, direction requests and "this
   helped" feedback, train LightGBM LambdaRank on the same features. Expose SHAP
   contributions as the score breakdown, so the frontend contract doesn't change.

## Running

```bash
cd api
python -m pytest
python -m app.ranking.cli --service kidney-dialysis --lat 20.296 --lon 85.825 \
    --from-databricks --facilities /tmp/model_facilities.tsv   # first run: query + cache
python -m app.ranking.cli --service kidney-dialysis --lat 20.296 --lon 85.825 \
    --facilities /tmp/model_facilities.tsv                     # later runs: cache only
```

The CLI needs `data/tags/facility_tag_scores.csv` (from `pipeline/tfidf_classify.py`). It
also uses `data/tags/facility_tags.csv` (from `pipeline/build_tags.py`) when present.
