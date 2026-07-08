# API Reference (Phase 9, optional)

FastAPI service. Run: `./.venv/bin/uvicorn backend.app.api.main:app --reload` · Swagger at `/docs`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness → `{"status":"ok"}` |
| GET | `/datasets` | List dataset folders under `datasets/raw/` |
| POST | `/analyze` | Body `{dataset, window_minutes}` → summary + correlation hits + top risk |
| GET | `/entities/{ds}?window&limit&offset` | Paginated entities with risk & flags |
| GET | `/graph/{ds}?window` | Network payload `{nodes, edges}` |

Results are cached per `(dataset, window)`. This API is optional — the dashboard and CLI cover the
core workflow; the API exists for programmatic/integration use.
