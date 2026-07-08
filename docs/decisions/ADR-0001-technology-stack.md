# ADR-0001 — Core Technology Stack & Build Strategy

- **Status:** Accepted
- **Date:** 2026-07-07
- **Deciders:** Technical Lead (with personas per master prompt)
- **Context refs:** `research/07_architecture_planning.md`, `research/03_initial_research.md`,
  `research/08_implementation_planning.md`

## Context

ERH26_PS_03 requires a forensic platform fusing Bank/CDR/IPDR data. We must pick a stack that
satisfies the requirements (parsing, correlation, graph, ML, viz, reporting) and a build strategy
that reliably reaches the PS deliverables. Two tensions exist: (1) hackathon prototype vs enterprise
platform; (2) breadth of modules vs verified, working core.

## Decision

**Stack (core, prototype):**
- **Python 3.11** backend — unifies parsing/ML/correlation.
- **FastAPI** for the API (later phases).
- **pandas + openpyxl + pdfplumber** for multi-format parsing.
- **SQLAlchemy + PostgreSQL** for the canonical store (SQLite fallback for local dev).
- **NetworkX** for graph analytics.
- **scikit-learn (Isolation Forest) + configurable rules** for detection (rules-first, explainable).
- **WeasyPrint + python-docx** for reports (later phase).
- **Streamlit first**, React + D3 later, for the investigator UI.
- **Optional / scale-triggered:** Neo4j (graph DB), Elasticsearch (search), JWT/RBAC, observability,
  containerization.

**Build strategy:** core-first, incremental with review gates, vertical-slice before breadth.

## Rationale

- One language across parsing/ML/graph minimizes glue and matches the PS "Suggested Tools".
- Rules-first detection is explainable and needs no labeled data — critical for evidentiary use
  (NFR-7) and the relevance criterion (NFR-3).
- Relational store fits the well-structured canonical model + provenance integrity better than a
  document store for the core; Mongo/ES/Neo4j remain optional upgrades gated on scale (Q7).
- Streamlit-first gets a working investigator UI fast to prove fusion, de-risking the demo; React+D3
  is a later polish pass.
- Incremental delivery avoids accumulating unverified code — every increment is run and validated.

## Alternatives considered

- **Neo4j from day one:** richer graph drill-down but adds infra before any scale need — deferred to
  optional.
- **Microservices from the start:** no stated scale/multi-tenant need → modular monolith now, extract
  later (boundaries already defined in `research/05`).
- **React+D3 first:** best UX but slow to first visible result → Streamlit-first chosen.
- **Full autonomous build of all modules:** rejected — high risk of unverified/broken code; replaced
  with vertical-slice + phase gates.

## Consequences

- Fast path to a demoable core; enterprise features are additive, not blocking.
- Some later rework when swapping Streamlit→React and NetworkX→Neo4j; contained by the store-in/
  store-out service contracts (`research/07` §7).

## Related

- Next ADRs to record: canonical model choices (ADR-0002), parser auto-detection strategy (ADR-0003),
  detection rule thresholds (ADR-0004).
