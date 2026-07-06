# 09 — Folder Structure Planning

**Project:** AI-Powered Financial & Telecom Dataset Analyzer (Bank, CDR & IPDR Fusion)
**Problem Statement ID:** ERH26_PS_03 · **Domain:** Big Data and Analytics
**Document status:** Batch C · Draft 1 · 2026-07-06

---

## 1. Purpose

To define a scalable, self-documenting project structure that maps one-to-one onto the modules in the
architecture (Doc 07) and the phases (Doc 08), so developers know exactly where each piece of code and
artifact belongs.

## 2. Objective

Provide a directory layout that separates concerns (ingestion, fusion, detection, graph, reporting,
API, frontend), isolates configuration and data, and supports testing and documentation.

## 3. Scope

The full repository layout for backend, frontend, data, docs, and ops. Runtime data samples are
illustrative; real datasets are managed outside version control.

---

## 4. Proposed Structure

```text
ERakshak/
├── research/                         # THIS planning doc set (Docs 00–11)
├── README.md                         # Project overview, setup, demo instructions
├── docker-compose.yml                # App + PostgreSQL (+ optional Neo4j/Elasticsearch)
├── .env.example                      # Env var template (no secrets committed)
├── pyproject.toml / requirements.txt # Backend deps
│
├── config/                           # Externalized tunables (NFR-6)
│   ├── settings.yaml                 # Correlation window W, thresholds, feature flags
│   ├── profiles/                     # Mapping profiles for bank/CDR/IPDR layouts (FR-4)
│   │   ├── banks/                    #   e.g. hdfc.yaml, sbi.yaml, generic.yaml
│   │   ├── cdr/                      #   e.g. jio.yaml, airtel.yaml, generic.yaml
│   │   └── ipdr/                     #   e.g. jio.yaml, airtel.yaml, generic.yaml
│   └── scoring_rules.yaml            # Anomaly thresholds & risk weights (FR-11/12)
│
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI entrypoint
│   │   ├── api/                      # Routes, request/response schemas
│   │   │   ├── routes/               #   ingestion, analysis, graph, search, report
│   │   │   ├── orchestrator.py       #   thin pipeline sequencing
│   │   │   └── schemas.py            #   Pydantic models
│   │   ├── core/                     # Config loader, logging, provenance, db session
│   │   ├── models/                   # ORM/canonical model (Entity, Event, Link) — Doc 06
│   │   │
│   │   ├── ingestion/                # FR-1..5  (Phase 1)
│   │   │   ├── type_detector.py
│   │   │   ├── format_detector.py
│   │   │   ├── profile_registry.py
│   │   │   ├── parsers/              #   excel.py, pdf.py, csv.py, delimited.py
│   │   │   └── reject_log.py
│   │   │
│   │   ├── normalization/            # FR-4,6,7 / NFR-7 (Phase 2)
│   │   │   ├── field_mapper.py
│   │   │   ├── normalizers/          #   phone.py, ip.py, datetime.py, amount.py
│   │   │   ├── narration_extractor.py
│   │   │   └── provenance.py
│   │   │
│   │   ├── entity_resolution/        # FR-10 (Phase 2)
│   │   │   ├── identifier_extractor.py
│   │   │   ├── identity_graph.py
│   │   │   └── component_resolver.py
│   │   │
│   │   ├── correlation/              # FR-8,9 (Phase 3)
│   │   │   ├── timeline_builder.py
│   │   │   └── window_correlator.py
│   │   │
│   │   ├── detection/                # FR-11,12,13 (Phase 4)
│   │   │   ├── rules/                #   layering.py, rapid_inout.py, structuring.py,
│   │   │   │                         #   circular_flow.py, mule.py
│   │   │   ├── ml/                   #   feature_builder.py, isolation_forest.py
│   │   │   └── risk_scorer.py
│   │   │
│   │   ├── graph/                    # FR-14,18 (Phase 5)
│   │   │   ├── network_builder.py
│   │   │   └── algorithms.py         #   cycles, centrality, communities
│   │   │
│   │   ├── search/                   # FR-15,19 (Phase 6/9)
│   │   │   ├── query_builder.py
│   │   │   ├── filters.py
│   │   │   └── nl_query.py           #   optional (LLM→DSL)
│   │   │
│   │   └── reporting/                # FR-16,17 (Phase 7)
│   │       ├── report_builder.py
│   │       ├── templates/           #   HTML/Word templates
│   │       ├── pdf_renderer.py       #   WeasyPrint
│   │       ├── docx_renderer.py      #   python-docx
│   │       └── str_generator.py      #   optional
│   │
│   ├── migrations/                   # DB migrations (Alembic)
│   └── tests/                        # Mirrors app/ structure; unit + integration
│       ├── fixtures/                 #   small canonical fixtures
│       └── ...
│
├── frontend/                         # React + D3.js SPA (Phase 6)
│   ├── src/
│   │   ├── components/               #   TimelineView, NetworkGraph, Filters, EntityDetail
│   │   ├── pages/                    #   Dashboard, ReportExport
│   │   ├── api/                      #   backend client
│   │   ├── hooks/ · state/ · utils/
│   │   └── theme/
│   ├── public/
│   └── package.json
│
├── data/                            # NOT for real case data in VCS
│   ├── samples/                      #   synthetic Bank/CDR/IPDR for dev/demo (Phase 0)
│   ├── uploads/                      #   runtime uploads (gitignored)
│   └── outputs/                      #   generated reports (gitignored)
│
├── tools/                           # Utilities
│   └── synthetic_data_generator/     #   Phase 0 dataset generator
│
├── docs/                            # Delivered documentation (Phase 8)
│   ├── parsers.md                    #   PS deliverable
│   ├── correlation_logic.md          #   PS deliverable
│   ├── scoring_rules.md              #   PS deliverable
│   └── architecture.md               #   derived from research/07
│
└── scripts/                         # dev/ops helpers (run, seed, lint, test)
```

## 5. Folder purpose reference

| Path | Purpose | Maps to |
|------|---------|---------|
| `research/` | Pre-implementation planning (this set) | Docs 00–11 |
| `config/` | All externalized tunables & mapping profiles | NFR-6, FR-4 |
| `backend/app/ingestion/` | Parse & detect formats | FR-1..5 |
| `backend/app/normalization/` | Canonical mapping + provenance | FR-4,6,7 / NFR-7 |
| `backend/app/entity_resolution/` | Link identifiers into entities | FR-10 |
| `backend/app/correlation/` | Timeline + windowed coincidence | FR-8,9 |
| `backend/app/detection/` | Rules + ML + risk scoring | FR-11..13 |
| `backend/app/graph/` | Network build + algorithms | FR-14,18 |
| `backend/app/search/` | Filter/search/NL query | FR-15,19 |
| `backend/app/reporting/` | Forensic report + STR | FR-16,17 |
| `frontend/` | Fusion dashboard | FR-14,15 / NFR-4 |
| `data/samples/` | Synthetic datasets to unblock dev | Phase 0 / Q3 |
| `tools/synthetic_data_generator/` | Generate realistic samples | Phase 0 |
| `docs/` | Delivered documentation | PS deliverable |
| `tests/` | Mirrors modules; fixtures | NFR-9 |

## 6. Conventions

- **`tests/` mirrors `app/`** so every module has an obvious test home.
- **Module = architecture component** (Doc 07 §6) = **phase deliverable** (Doc 08) → one consistent
  mental model across all three docs.
- **No secrets or real case data in VCS**; `data/uploads` and `data/outputs` are gitignored.
- **Optional features live in their expected module** behind feature flags (e.g., `nl_query.py`,
  `str_generator.py`) so enabling them needs no restructuring.

## 7. Assumptions

- `[Assumption]` Python backend + React frontend as recommended in Doc 07; if a Streamlit-only demo is
  chosen, `frontend/` collapses into a `backend/app/dashboard/` Streamlit module.
- `[Assumption]` Single repository (monorepo) for prototype simplicity.

## 8. Dependencies

- Mirrors module breakdown in `07_architecture_planning.md` and phases in `08_implementation_planning.md`.

## 9. Risks

- Structure drift if modules are added ad hoc — mitigated by the module=component=phase convention.

## 10. Best Practices

- Keep the tree shallow and predictable; one responsibility per package.
- Co-locate templates/config with the code that uses them where sensible, but keep tunables in `config/`.

## 11. Future Considerations

- Split `backend/` into services if the monolith is later decomposed (Doc 07 §15).
- Add `infra/` for IaC if cloud deployment is introduced.

## 12. References

- `07_architecture_planning.md`, `08_implementation_planning.md`.
