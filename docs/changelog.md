# Changelog

## [1.1.0] — 2026-07-08 — Production-readiness remediation (review board fixes)

### Security & reliability (blockers)
- **C1** Persistence layer: durable canonical store (SQLite default / Postgres via
  `DATABASE_URL`) — `persistence/store.py`, `models/canonical.py` now actually used;
  `pipeline.run(persist=True)`, `run_pipeline --persist`, API `analyze{persist:true}`.
- **C2** AuthN/AuthZ: JWT bearer auth (bcrypt hashes), RBAC, `/v1/auth/token`, all data
  endpoints protected, audit logging, consistent error schema, dashboard login gate.
- **C3** Fixed CGNAT entity over-merge: public IP is no longer a merge key; added a
  component-size circuit breaker. Regression test added.
- **C4** Bounded `simple_cycles` (count + time) and layering DFS (path budget).

### High
- **H1** Structured logging (`core/logging_config.py`); removed silent excepts.
- **H2** Upload hardening: filename sanitization (no path traversal), extension/size/count limits.
- **H3** Correlation optimized from O(T·C) to sorted + binary search.
- **H4** Pinned all dependencies to exact versions.
- **H5** CI workflow (ruff + pytest + docker build); ruff config; lint clean.
- **H6** Tests expanded 8 → 18: API auth, CGNAT regression, parser robustness, persistence.

### Medium
- **M2** `/v1` API versioning. **M3** consistent error schema. **M7** Isolation Forest model
  persisted + versioned (`data/models/`).

## [1.0.0] — 2026-07-08 — Full core pipeline (Phases 0–9)

### Added
- **Phase 0** — repo scaffold, config, canonical SQLAlchemy schema, synthetic data generator
  (entity-first, planted labeled fraud, ground truth).
- **Phase 1** — ingestion: format/type/profile auto-detection; Excel/CSV/PDF parsers; reject log.
- **Phase 2** — normalization (phone/IP/datetime/amount), narration mining, provenance; deterministic
  graph-based entity resolution (bank↔telecom fusion via registered mobile).
- **Phase 3** — per-entity unified timeline; windowed call+IP+transfer correlation.
- **Phase 4** — rules (structuring, rapid in/out, layering, circular flow, mule, coincidence) +
  Isolation Forest + composite risk score; ground-truth evaluation (**recall 1.0** on demo).
- **Phase 5** — money-flow (shared-UTR) + communication graph; centrality/community metrics.
- **Phase 6** — Streamlit investigator dashboard (overview, network, entities, timeline,
  correlations, search, report export).
- **Phase 7** — forensic report (PDF + Word) with STR draft and provenance.
- **Phase 8** — CLI runner, pytest suite (8 tests passing), docs.
- **Phase 9** — FastAPI service, Dockerfile, docker-compose.

### Fixed
- ISO vs dd/mm/yyyy date parsing (dayfirst) — was collapsing transaction times.
- Layering DFS first-hop guard — rule now fires correctly.
- Profile confidence scoring (per-field, not per-alias) — removed spurious manual-mapping flags.
