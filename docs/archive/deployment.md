# Deployment

## Local (recommended for the prototype)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m tools.synthetic_data_generator.generate --tier demo   # sample data
streamlit run backend/app/dashboard/app.py                      # dashboard :8501
uvicorn backend.app.api.main:app --reload                       # API :8000 (optional)
```

## Docker
```bash
docker compose up --build      # api :8000, dashboard :8501
```

## Notes
- **Storage:** prototype runs fully in-memory (pandas/NetworkX). PostgreSQL is optional and
  scale-triggered — uncomment the `postgres` service in `docker-compose.yml` and set `DATABASE_URL`.
- **Config:** tune `config/settings.yaml` (window W, thresholds) and `config/scoring_rules.yaml`
  without code changes.
- **Data:** never commit real case data — `data/uploads`, `data/outputs`, and `datasets/raw/*` are
  gitignored.
- **Enterprise (future):** Neo4j / Elasticsearch, JWT/RBAC, and observability plug in behind the
  existing service contracts (see `research/07`, `research/10`).
