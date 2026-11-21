# Cardinal Virtues

Healthcare facility discovery and recommendation project.

## Repository layout

- `web/` — React 19, TypeScript, Vite, and Leaflet frontend.
- `pipeline/` — Databricks data pipeline; `build_tags.py` builds the service/condition tag catalog in `data/tags/` (see [`pipeline/README.md`](pipeline/README.md)).
- `api/` — Python ranking service; `api/app/ranking/` is the phase-1 explainable ranker (see [`docs/ranking_model.md`](docs/ranking_model.md)).
- `APP_FRAMEWORK_REQUIREMENTS.en.md` — product, data, API, ranking, and deployment requirements.

## Frontend

```bash
cd web
pnpm install
pnpm dev
```

See [`web/README.md`](web/README.md) for the frontend architecture, demo-data notes, and integration guidance.
