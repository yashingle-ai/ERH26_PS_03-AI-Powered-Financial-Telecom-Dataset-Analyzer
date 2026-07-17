# ERakshak — AI-Powered Financial & Telecom Dataset Analyzer

**Problem Statement:** ERH26_PS_03 — Bank, CDR & IPDR Fusion · **Domain:** Big Data and Analytics

A forensic intelligence platform that ingests heterogeneous **Bank statements, CDR (Call Detail Records), and IPDR (Internet Protocol Detail Records)**, normalizes them onto a **unified entity + timeline model**, correlates events across datasets, detects suspicious money-flow / communication patterns, and produces investigation-ready forensic output.

---

## Key Features

| Pillar | Description |
|--------|-------------|
| **Multi-format Ingestion** | Auto-detect and parse Bank statements (Excel/PDF/CSV), CDR, and IPDR with per-bank profile mapping |
| **Cross-Dataset Fusion** | Deterministic entity resolution via identifier graph (PHONE ↔ ACCOUNT ↔ IMEI ↔ IP) with CGNAT-safe merge |
| **Anomaly Detection** | FATF-style rules (structuring, layering, mule, circular flow, rapid in-out) + Isolation Forest ML |
| **Risk Scoring** | Composite 0–100 score (70% rules + 30% ML), banded into low / medium / high |
| **Network Visualization** | D3 force-directed graph with money-flow and communication edges |
| **Zoomable Timeline** | D3 swimlane timeline with per-entity filtering and correlation window highlights |
| **Forensic Reports** | PDF / Word export with provenance chains and STR draft |
| **Command Palette** | ⌘K fuzzy search across pages, entities, and actions |

---

## Architecture Overview

```
ingest → normalize → resolve entities → build timeline → correlate
       → build money-flow → detect + risk-score → build graph → persist
```

The backend pipeline ([pipeline.py](backend/app/pipeline.py)) runs 9 stages, each a discrete service with store-in/store-out contracts. The React frontend consumes a versioned FastAPI (`/v1`) with JWT authentication.

| Layer | Stack |
|-------|-------|
| **Data & Parsing** | pandas, numpy, openpyxl, pdfplumber |
| **Schema / Persistence** | SQLAlchemy, pydantic, SQLite (Postgres-ready via `DATABASE_URL`) |
| **Graph & ML** | networkx, scikit-learn (Isolation Forest), joblib |
| **Reporting** | reportlab (PDF), python-docx (Word), Jinja2 |
| **API & Security** | FastAPI, uvicorn, PyJWT, bcrypt, python-multipart |
| **Frontend** | React 19, Vite 8, TanStack Router/Query, D3.js, Tailwind CSS v4, shadcn/ui |
| **Testing** | pytest (backend), vitest + happy-dom (frontend) |
| **Deploy** | Dockerfile + docker-compose |

---

## Quick Start

### 1. Backend API

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix:    source .venv/bin/activate
pip install -r requirements.txt

# Optional: regenerate smoke data
python -m tools.synthetic_data_generator.generate --tier smoke --out datasets/raw/smoke

# Stable local credentials (required for UI login)
# Windows PowerShell:
$env:ERAKSHAK_JWT_SECRET="dev-secret"
$env:ERAKSHAK_ADMIN_PASSWORD="adminpass"
$env:ERAKSHAK_ANALYST_PASSWORD="analystpass"
# Unix:
#   export ERAKSHAK_JWT_SECRET=dev-secret
#   export ERAKSHAK_ADMIN_PASSWORD=adminpass
#   export ERAKSHAK_ANALYST_PASSWORD=analystpass

uvicorn backend.app.api.main:app --reload --port 8000
```

API docs: http://127.0.0.1:8000/docs
Login users: `admin` / `adminpass` or `analyst` / `analystpass`

### 2. Frontend UI

```bash
cd frontend
cp .env.example .env   # Windows: copy .env.example .env
npm install
npm run dev
```

Open the Vite URL (typically http://localhost:5173). Sign in with the API credentials above, then select a dataset (e.g., **smoke**).

### 3. CLI / Streamlit (optional)

```bash
python scripts/run_pipeline.py datasets/raw/smoke
streamlit run backend/app/dashboard/app.py
```

### 4. Docker

```bash
docker compose up --build
# API: http://localhost:8000
# Streamlit: http://localhost:8501
```

---

## Repository Layout

| Path | Purpose |
|------|---------|
| `Research/` | 13 pre-implementation planning docs (00–12): problem analysis, requirements, architecture |
| `artifacts/` | Frontend redesign documentation: backend analysis, TRD, app flow, UI/UX brief, API guide, review, roadmap |
| `config/` | Externalized tunables + source→canonical mapping profiles (YAML) |
| `backend/app/` | Pipeline modules + FastAPI (`api/`) + Streamlit dashboard |
| `backend/tests/` | pytest suite (18 tests — API auth, CGNAT regression, parser robustness, persistence) |
| `frontend/` | React investigator UI (TanStack Router + D3 visualizations) |
| `tools/synthetic_data_generator/` | Labeled synthetic Bank + CDR + IPDR generator with ground-truth |
| `datasets/` | raw / metadata datasets + ground truth |
| `data/` | Runtime DB, fitted models, report outputs (gitignored) |
| `docs/` | Delivered docs + ADRs (architecture, canonical schema, API, deployment) |
| `scripts/` | Dev/ops helpers (CLI pipeline runner) |

---

## Frontend Redesign (Completed)

The React frontend was redesigned across 5 sprints — see [`artifacts/`](artifacts/) for full documentation:

| Sprint | Theme | Highlights |
|--------|-------|------------|
| **1** | Foundation & Network Graph | Type system cleanup, shared components, D3 force-directed graph |
| **2** | Timeline & Entity Workflow | Zoomable D3 swimlane timeline, per-entity filtering, entity detail upgrades |
| **3** | Investigation Flow & Search | ⌘K command palette, detection drill-down, cross-page entity navigation |
| **4** | Polish & Performance | Page-specific skeleton loaders, keyboard shortcuts (G+O/E/T/N/D/R), micro-animations |
| **5** | Reports & Hardening | Print stylesheet for PDF export, upload instructions, vitest setup, accessibility audit |

### Key Frontend Components

- **Network Graph** — D3 force-directed with drag, zoom, pan, edge filtering, force strength slider
- **Timeline Canvas** — D3 swimlane with adaptive axis labels, jitter for overlapping events, correlation windows
- **Command Palette** — `⌘K` / `Ctrl+K` fuzzy search over pages, entities, and actions
- **Skeleton Loaders** — Page-specific loading states mirroring actual layout
- **Keyboard Shortcuts** — Vim-style `G` prefix navigation to all pages

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Public liveness check |
| `POST` | `/v1/auth/token` | OAuth2 password flow → JWT |
| `GET` | `/v1/datasets` | List available dataset folders |
| `POST` | `/v1/analyze` | Run full pipeline → summary + correlations + top risk |
| `GET` | `/v1/entities/{ds}` | Paginated entities with risk & flags |
| `GET` | `/v1/events/{ds}` | Paginated events with filtering |
| `GET` | `/v1/graph/{ds}` | Network payload `{nodes, edges}` |

---

## Detection Rules

| Rule | Description |
|------|-------------|
| **Structuring** | ≥3 credits clustered just below a reporting threshold (smurfing) |
| **Rapid In-Out** | ≥80% of a credit forwarded within an hour (pass-through) |
| **Mule Account** | High counterparty fan-in combined with rapid forwarding |
| **Circular Flow** | A→B→…→A money loops in the transfer graph |
| **Layering** | Funds hopping across ≥3 accounts within a short span |
| **Call-Transfer Coincidence** | Call + IP session + transfer within window W minutes |

Composite score: `70% × rule component + 30% × ML anomaly score`, banded into **low (0–39) / medium (40–69) / high (70–100)**.

---

## Documentation

| Document | Path |
|----------|------|
| Project Overview | [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) |
| Backend Understanding | [`artifacts/01_backend_understanding_summary.md`](artifacts/01_backend_understanding_summary.md) |
| Technical Requirements | [`artifacts/02_technical_requirements_document.md`](artifacts/02_technical_requirements_document.md) |
| App Flow & Navigation | [`artifacts/03_app_flow.md`](artifacts/03_app_flow.md) |
| UI/UX Design Brief | [`artifacts/04_ui_ux_design_brief.md`](artifacts/04_ui_ux_design_brief.md) |
| API Consumption Guide | [`artifacts/05_api_consumption_guide.md`](artifacts/05_api_consumption_guide.md) |
| Frontend Review & Critique | [`artifacts/06_frontend_review_critique.md`](artifacts/06_frontend_review_critique.md) |
| Implementation Roadmap | [`artifacts/07_implementation_roadmap.md`](artifacts/07_implementation_roadmap.md) |
| Frontend Walkthrough | [`artifacts/walkthrough.md`](artifacts/walkthrough.md) |
| Architecture | [`docs/architecture.md`](docs/architecture.md) |
| Canonical Schema | [`docs/canonical_schema.md`](docs/canonical_schema.md) |
| Progress Log | [`docs/progress.md`](docs/progress.md) |
| Changelog | [`docs/changelog.md`](docs/changelog.md) |

---

## License

Internal / hackathon project. Do not commit real case data.

---

## Developed By

- **Yash Ingle** — u23ai062@coed.svnit.ac.in
- **Himal Rana** — u23ai053@coed.svnit.ac.in
- **Ankit Yadav** — u23ai039@coed.svnit.ac.in
- **Tarun Bhutra** — u23ai063@coed.svnit.ac.in
