# Progress Log

Build strategy: **core-first · Streamlit-first UI**. Phases per `research/08_implementation_planning.md`.

---

## ✅ ALL PHASES COMPLETE (0–9) — 2026-07-08

| Phase | Status | Verification |
|-------|--------|--------------|
| 0 Foundations + synthetic data | ✅ | smoke/demo/scale tiers generate; xlsx/pdf/csv valid |
| 1 Ingestion & parsing | ✅ | 3 sources detected, avg confidence 0.98, 0 manual-mapping |
| 2 Normalization & entity resolution | ✅ | bank↔telecom fusion: 8 persons → 8 fused entities |
| 3 Timeline & correlation | ✅ | planted call+IP+transfer coincidences found |
| 4 Detection & risk | ✅ | **recall 1.0** on all 15 demo scenarios |
| 5 Graph service | ✅ | 104 nodes / 1536 edges, centrality + communities |
| 6 Streamlit dashboard | ✅ | boots, HTTP 200, health OK |
| 7 Reporting | ✅ | PDF + Word + STR generate |
| 8 CLI + tests + docs | ✅ | 8/8 pytest passing |
| 9 FastAPI + Docker | ✅ | /health, /datasets, /analyze, /graph respond |

### Run it
```bash
source .venv/bin/activate
python -m tools.synthetic_data_generator.generate --tier demo
python -m scripts.run_pipeline --input datasets/raw/demo --window 10 --eval
streamlit run backend/app/dashboard/app.py          # UI :8501
uvicorn backend.app.api.main:app                    # API :8000
pytest backend/tests/ -q                            # tests
```

## ✅ v1.1 — Review-board remediation (2026-07-08)

All 7 blockers + high/medium items from the production-readiness review closed:

| Fix | Status | Evidence |
|-----|--------|----------|
| C1 Persistence | ✅ | SQLite/Postgres store; durable across processes; `test_persistence_roundtrip` |
| C2 Auth/RBAC/audit | ✅ | JWT+bcrypt, `/v1` protected, 401 verified, audit log; API tests |
| C3 CGNAT over-merge | ✅ | IP removed from merge keys + circuit breaker; regression test |
| C4 Graph bounds | ✅ | cycle count/time caps + DFS path budget |
| H1 Logging | ✅ | `core/logging_config.py`; no silent excepts |
| H2 Upload hardening | ✅ | basename + ext/size/count limits |
| H3 Correlation perf | ✅ | sorted + bisect (was O(T·C)) |
| H4 Pinned deps | ✅ | exact versions in requirements.txt |
| H5 CI + lint | ✅ | `.github/workflows/ci.yml`; ruff clean |
| H6 Tests | ✅ | 8 → 18 passing |
| M2/M3/M7 | ✅ | `/v1`, error schema, model versioning |

Updated production checklist: ✅ persistence, ✅ auth, ✅ audit log, ✅ logging, ✅ CI,
✅ pinned deps, ✅ upload hardening, ✅ error schema. Still open (documented): metrics/alerting,
backup/DR runbook, precision measurement on non-synthetic data, load test at scale tier.

## Known limitations / next
- Schemas modeled (research/06), not real operator/bank exports (Q1–Q3 still ASSUMED).
- Detection precision tunable via `config/scoring_rules.yaml`; benign entities in dense transfer
  graphs can trip circular_flow — raise thresholds or add amount gates for real data.
- Enterprise (auth/RBAC, Neo4j/ES, observability, React+D3) intentionally deferred behind service
  contracts (research/07 §15).
