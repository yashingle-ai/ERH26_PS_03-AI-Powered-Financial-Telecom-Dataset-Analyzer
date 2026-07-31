# Architecture (as-built)

Implements `research/07_architecture_planning.md`. Modular monolith (Python) + Streamlit UI.

> This is the module map. For each stage's **contract** — what it guarantees, the cross-stage
> invariants, and why each parsing fallback exists — see `yash development/ARCHITECTURE.md`.

## Pipeline stages (backend/app/)

```
ingestion → normalization → entity_resolution → correlation → graph(money_flow)
          → detection → graph(service) → dashboard / reporting
```

| Module | Responsibility | Key files |
|--------|----------------|-----------|
| `ingestion/` | Detect format/type/profile; parse xlsx/csv/pdf; reject log | `detector.py`, `service.py`, `parsers/` |
| `normalization/` | Map to canonical model; normalize phone/IP/datetime/amount; mine narration; provenance | `service.py`, `field_mapper.py`, `narration.py`, `normalizers/` |
| `entity_resolution/` | Deterministic identifier-graph → connected-component entities (fusion) | `service.py` |
| `correlation/` | Per-entity timeline; windowed call+IP+transfer coincidence | `timeline_builder.py`, `window_correlator.py` |
| `graph/` | Money-flow (shared-UTR) + communication graph; centrality/community | `money_flow.py`, `service.py` |
| `detection/` | Rules + Isolation Forest → composite risk; ground-truth eval | `rules.py`, `features.py`, `service.py`, `evaluate.py` |
| `reporting/` | Forensic PDF/Word + STR | `service.py` |
| `dashboard/` | Streamlit investigator UI (timeline, network, search, report) | `app.py`, `viz.py` |
| `core/` | Config loader (settings, scoring rules, profiles) | `config.py` |
| `models/` | SQLAlchemy canonical schema | `canonical.py` |
| `pipeline.py` | Orchestrator: runs all stages → `Investigation` | |

## Data model
See `docs/canonical_schema.md`. Entity ← EntityIdentifier; Event(TRANSACTION/CALL/IP_SESSION) with
provenance; EntityLink for graph edges.

## Fusion bridge
Bank↔telecom is bridged deterministically via the **registered mobile** on the statement (links
ACCOUNT_NO ↔ PHONE) and the phone↔IMEI↔IP co-occurrence in CDR/IPDR — connected components merge them
into one person. The signature evidence (call+IP+transfer within W) is then detectable per entity.

## Config-driven (NFR-6)
`config/settings.yaml` (window W, timezone, thresholds), `config/scoring_rules.yaml` (FATF-style
rules + risk weights), `config/profiles/**` (source→canonical maps). No thresholds hard-coded.

## Optional / enterprise (Phase 9)
`backend/app/api/` (FastAPI), `Dockerfile` + `docker-compose.yml`. Neo4j/Elasticsearch remain
scale-triggered upgrades behind the same service contracts.
