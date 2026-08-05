# API Reference (Phase 9, optional)

FastAPI service. Run: `./.venv/bin/uvicorn backend.app.api.main:app --reload` · Swagger at `/docs`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness → `{"status":"ok"}` |
| GET | `/v1/data-quality/{ds}` | Ledger breaks + per-file ingestion rejects |
| POST | `/v1/query/{ds}` | Body `{q, window_minutes, engine?}` → `{answer, explanation, rows, total, spec, …}`. `answer` is composed locally from the plan + rows; case data never goes to the LLM. |

Results are cached per `(dataset, window)`. This API is optional — the dashboard and CLI cover the
core workflow; the API exists for programmatic/integration use.
