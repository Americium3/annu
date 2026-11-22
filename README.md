# Cardinal Virtues

Healthcare facility discovery and recommendation project.

## Repository layout

- `web/` — React 19, TypeScript, Vite, and Leaflet frontend.
- `backend/` — live FastAPI serving path, defaulting to cross-encoder relevance + distance after eligibility filtering (see [`backend/README.md`](backend/README.md)).
- `pipeline/` — Databricks data pipeline; `build_tags.py` builds the service/condition tag catalog in `data/tags/` (see [`pipeline/README.md`](pipeline/README.md)).
- `api/` — standalone phase-1 rule ranker, not the frontend's serving entry point (see [`docs/ranking_model.md`](docs/ranking_model.md)).
- `experiments/` — high-recall service candidates + rules/TF-IDF/BM25/bi-encoder/cross-encoder comparisons, independent qrels metrics and map outputs (see [`experiments/README.md`](experiments/README.md)).
- `notebooks/100_two_stage_experiments.py` — Databricks Free Edition experiment entry point.
- `APP_FRAMEWORK_REQUIREMENTS.en.md` — product, data, API, ranking, and deployment requirements.

## Frontend

```bash
cd web
pnpm install
pnpm dev
```

See [`web/README.md`](web/README.md) for the frontend architecture, demo-data notes, and integration guidance.
