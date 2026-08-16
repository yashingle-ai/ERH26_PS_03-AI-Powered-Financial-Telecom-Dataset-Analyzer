# ERakshak — AI-Powered Financial & Telecom Dataset Analyzer

**Problem statement:** [ERH26_PS_03](research/01_problem_statement_analysis.md) — Bank, CDR & IPDR Fusion  
**Domain:** Big Data and Analytics · **Hackathon:** ERakshak / ERH26

A forensic intelligence platform that **ingests bank statements, CDR and IPDR**, fuses them onto **one entity + timeline model**, correlates cross-domain coincidences (call + IP session + money transfer), scores risk, and produces investigation-ready PDF/DOCX reports.

Evaluators can run the full product locally in under 15 minutes using the synthetic `demo` / `smoke` datasets that ship in this repo. No real case data is required — and none is committed.

| Surface | URL | What it is |
|---------|-----|------------|
| **React console** | http://localhost:8080 | Product UI — overview, entities, detections, timeline, network, reports |
| **Streamlit workbench** | http://localhost:8501 | Analyst tools — mapping, data quality, heat map, NL query |
| **FastAPI** | http://127.0.0.1:8000/docs | 17 authenticated endpoints + Swagger |
| **Health** | http://127.0.0.1:8000/health | Public liveness |

---

## Contents

1. [What it does](#what-it-does)
2. [Prerequisites](#prerequisites)
3. [Setup and installation](#setup-and-installation)
4. [Run the application](#run-the-application)
5. [Project folder structure](#project-folder-structure)
6. [System architecture](#system-architecture)
7. [API documentation](#api-documentation)
8. [Database schema](#database-schema)
9. [Dependencies](#dependencies)
10. [Deployment](#deployment)
11. [Tests](#tests)
12. [Documentation index](#documentation-index)

A longer walkthrough of every screen is in **[GETTING_STARTED.md](GETTING_STARTED.md)**.

---

## What it does

```
Bank statements + CDR + IPDR
        │
        ▼
  ingest → normalise → resolve entities → timeline
        │
        ├─ correlate  (call + IP + transfer inside window W)
        ├─ detect     (8 typologies + Isolation Forest)
        ├─ graph      (money-flow + communications)
        └─ report     (PDF / DOCX / STR draft)
```

- **Ingestion** — Excel, CSV, PDF, HTML, archives, fixed-width print statements. Format is detected from magic bytes, not the file extension.
- **Fusion** — phones, accounts, IMEI/IMSI merge into one entity; all three domains share one timeline.
- **Correlation (FR-9)** — STRONG = call + IP + transfer in window `W`; MEDIUM = call + transfer.
- **Detection** — eight FATF-style rules (mule, structuring, layering, rapid in/out, …) plus Isolation Forest. Composite risk = `0.7 · rules + 0.3 · ML`.
- **Search** — structured filters and optional natural-language query (Gemini sees a **schema and a question, never case rows**).
- **Output** — network graph, risk heat map, forensic PDF/DOCX, STR draft.

Verified end to end on two real FIR case folders (not in git) and on the tracked `demo` / `smoke` fixtures. **429 tests**, ruff clean, `tsc` clean.

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | **3.11+** (CI pins 3.11; 3.13 works) |
| Node.js | **20+** (tested on 22) |
| npm | comes with Node |
| Docker | optional — only for container deploy |

```bash
python --version && node --version && npm --version
```

---

## Setup and installation

```bash
git clone <this-repo>
cd ERH26_PS_03-AI-Powered-Financial-Telecom-Dataset-Analyzer
```

### 1. Backend

Create a **fresh** virtualenv (do not reuse a copied `.venv` from another OS).

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Prove the pipeline (no servers)

From the **repo root**:

```bash
python scripts/run_pipeline.py --input datasets/raw/smoke
```

Expected summary (numbers may differ slightly): `files ≈ 19`, `events ≈ 547`, `correlation_hits ≥ 1`, `rejected_rows = 0`.

On PowerShell, stderr logs print in red even on success. Check `$LASTEXITCODE` — `0` means it worked.

### 3. Frontend

```bash
cd frontend
npm install
```

### 4. Environment (recommended)

```bash
cp .env.example .env
```

Set at least these in `.env` (or export them) so login is stable across restarts:

```
ERAKSHAK_JWT_SECRET=local-dev-secret-at-least-32-characters-long
ERAKSHAK_ANALYST_PASSWORD=devpass123
ERAKSHAK_ADMIN_PASSWORD=devadmin123
```

If they are unset, the API generates a **random password per boot** and logs it once. That is deliberate — no default credential ships in the Docker image.

---

## Run the application

You need **two terminals** for the product UI. Run every backend command from the **repo root**.

### Terminal 1 — API

**Windows (PowerShell)**

```powershell
$env:ERAKSHAK_ANALYST_PASSWORD = "devpass123"
$env:ERAKSHAK_ADMIN_PASSWORD   = "devadmin123"
$env:ERAKSHAK_JWT_SECRET       = "local-dev-secret-at-least-32-characters-long"
python -m uvicorn backend.app.api.main:app --reload --port 8000
```

**macOS / Linux**

```bash
export ERAKSHAK_ANALYST_PASSWORD=devpass123
export ERAKSHAK_ADMIN_PASSWORD=devadmin123
export ERAKSHAK_JWT_SECRET=local-dev-secret-at-least-32-characters-long
python -m uvicorn backend.app.api.main:app --reload --port 8000
```

- Health: http://127.0.0.1:8000/health → `{"status":"ok"}`
- Swagger: http://127.0.0.1:8000/docs

### Terminal 2 — React console

```bash
cd frontend
npm run dev
```

Open **http://localhost:8080**

| Field | Value |
|-------|-------|
| Username | `analyst` |
| Password | `devpass123` |

Pick dataset **`demo`** in the top bar. First analyse of `demo` takes ~20 seconds; `smoke` is faster.

### Optional — Streamlit workbench

No API required (it calls the pipeline in-process):

```bash
python -m streamlit run backend/app/dashboard/app.py --server.address 127.0.0.1
```

http://localhost:8501 — same analyst credentials. Bind to loopback so a loaded case is not exposed on the LAN.

### Optional — Docker (API + Streamlit)

```bash
cp .env.example .env          # set JWT secret + passwords
docker compose up -d --build
docker compose ps             # api and dashboard should be healthy
```

API **:8000** · Streamlit **:8501**. The React UI is **not** in Compose — still `cd frontend && npm install && npm run dev`.

---

## Project folder structure

```text
ERH26_PS_03-…/
├── README.md                 ← this file
├── GETTING_STARTED.md        ← full setup + screen-by-screen walkthrough
├── CLAUDE.md                 ← agent brief (rules, traps, commands)
├── requirements.txt          ← pinned Python dependencies
├── pyproject.toml            ← ruff + pytest config
├── Dockerfile                ← multi-stage image (API + Streamlit)
├── docker-compose.yml        ← api :8000 + dashboard :8501
├── .env.example              ← env template (no secrets)
│
├── backend/
│   ├── app/
│   │   ├── pipeline.py       ← orchestrator (run_base → apply_analysis)
│   │   ├── api/              ← FastAPI + JWT/RBAC
│   │   ├── ingestion/        ← detectors, parsers, reject log
│   │   ├── normalization/    ← canonical Event mapping
│   │   ├── entity_resolution/← identifier graph → entities
│   │   ├── correlation/      ← timeline + window correlator (FR-9)
│   │   ├── detection/        ← 8 rules + Isolation Forest
│   │   ├── graph/            ← money-flow + comms graph
│   │   ├── search/           ← NL query (schema only to the LLM)
│   │   ├── reporting/        ← PDF / DOCX / STR
│   │   ├── dashboard/        ← Streamlit workbench
│   │   ├── models/           ← SQLAlchemy canonical schema
│   │   └── persistence/      ← optional SQLite / Postgres store
│   └── tests/                ← 429 tests
│
├── frontend/                 ← React 19 + TanStack + Tailwind + D3
├── config/                   ← settings, scoring rules, source profiles
├── scripts/                  ← run_pipeline, measure_ingestion
├── tools/synthetic_data_generator/
├── datasets/raw/demo|smoke/  ← tracked synthetic fixtures only
├── data/                     ← uploads, reports, analysis cache (gitignored)
├── docs/                     ← architecture, API, data model, runbook
└── research/                 ← problem statement + planning docs 00–12
```

Real FIR folders under `datasets/` are gitignored on purpose. Never commit case evidence.

---

## System architecture

Modular monolith. One pipeline, three UIs (React, Streamlit, CLI).

```
parse ─► normalise ─► resolve entities ─► timeline ─┬─► correlate ──► detect ──► graph
                                          transfers ┘
        └──────────── run_base() ──────────────────┘└──── apply_analysis() ────┘
             window-independent (cached)                 re-runs per window W
```

| Layer | Stack |
|-------|--------|
| API | FastAPI, JWT + RBAC (`analyst` / `admin`) |
| Pipeline | Python 3.11, pandas, NetworkX, scikit-learn |
| Persistence | In-memory `Investigation` (hot path); optional SQLite / Postgres |
| Product UI | React 19, TanStack Router/Query, Tailwind 4, D3 — port **8080** |
| Analyst UI | Streamlit — port **8501** |
| Config | `config/settings.yaml`, `config/scoring_rules.yaml`, `config/profiles/**` |

**Contracts (what each stage guarantees):** [`docs/handbook/ARCHITECTURE.md`](docs/handbook/ARCHITECTURE.md)  
**Module map:** [`docs/architecture.md`](docs/architecture.md)

---

## API documentation

Base path `/v1`. JWT bearer. Interactive docs at **http://127.0.0.1:8000/docs**.

Full verified catalogue (17 endpoints, request/response keys, caching): **[`docs/handbook/API.md`](docs/handbook/API.md)**

| Method | Path | Role | Purpose |
|--------|------|------|---------|
| `GET` | `/health` | public | Liveness |
| `POST` | `/v1/auth/token` | public | Login (`username`, `password`) → `access_token` |
| `POST` | `/v1/auth/refresh` | public | Refresh token |
| `GET` | `/v1/datasets` | analyst | Available datasets + cached analyses |
| `POST` | `/v1/analyze` | analyst | Full run: summary, correlations, top risk. Body: `dataset`, `window_minutes`, `force` |
| `GET` | `/v1/analyze/progress/{ds}` | analyst | Live stage / percent / ETA |
| `GET` | `/v1/entities/{ds}` | analyst | Ranked risk rows |
| `GET` | `/v1/events/{ds}` | analyst | Fused timeline (filterable) |
| `GET` | `/v1/graph/{ds}` | analyst | Network nodes + edges |
| `GET` | `/v1/data-quality/{ds}` | analyst | Rejects, balance breaks, parsed files |
| `GET` | `/v1/rule-eligibility/{ds}` | analyst | Per-rule enabled / eligible / fired |
| `GET` | `/v1/risk-heatmap/{ds}` | analyst | Entities × typologies matrix |
| `GET` | `/v1/document-mentions/{ds}` | analyst | Narrative paperwork by identifier |
| `GET` | `/v1/suggestions/{ds}` | analyst | Review-only same-actor candidates |
| `POST` | `/v1/query/{ds}` | analyst | Natural-language query |
| `POST` | `/v1/report/{ds}` | analyst | Stream PDF or DOCX |
| `POST` | `/v1/upload/{ds}` | analyst | Upload evidence (`demo` / `smoke` refused) |

Health is **`/health`**, not `/v1/health`. Timeline and correlation hits live inside `POST /v1/analyze`. Rejects are at `GET /v1/data-quality/{ds}`.

Quick smoke (after the API is up with the passwords above):

```bash
curl -s -X POST http://127.0.0.1:8000/v1/auth/token \
  -d "username=analyst&password=devpass123"
```

---

## Database schema

The **hot path is in-memory**. Every parser maps onto one canonical model (`Event`, `Entity`, transfers, risk, rejects). That live contract — dumped from a real `demo` run — is **[`docs/handbook/DATA_MODEL.md`](docs/handbook/DATA_MODEL.md)**.

Optional durability is SQLAlchemy (`backend/app/models/canonical.py`) written by `backend/app/persistence/store.py`. Default: **SQLite** at `data/erakshak.db`. Postgres is scale-triggered (`DATABASE_URL`); the service is commented out in `docker-compose.yml`.

| Table | Role |
|-------|------|
| `entity` | Resolved actor (connected component of identifiers) |
| `entity_identifier` | ACCOUNT_NO / PHONE / IMEI / IMSI / IP / UPI_ID / BENEFICIARY |
| `event` | Unified timeline row: TRANSACTION / CALL / IP_SESSION (+ provenance JSON) |
| `entity_link` | Graph edges: money-flow / communication / shared-identifier |
| `risk_assessment` | Per-entity score, band, rule flags, ML score |
| `correlation_hit` | Call+IP+transfer (or call+transfer) coincidence inside `W` |
| `analysis_snapshot` | Index row for a pickled `Investigation` under `data/analysis_cache/` |

There is no Alembic tree. Schema is created on first persist; one additive column migration lives in `persistence/store.py`.

---

## Dependencies

**Backend** — pinned in [`requirements.txt`](requirements.txt):

| Area | Packages |
|------|----------|
| Parse | pandas, openpyxl, xlrd, pdfplumber |
| Model | pydantic, SQLAlchemy |
| Graph / ML | networkx, scikit-learn |
| API | fastapi, uvicorn, PyJWT, bcrypt, python-multipart |
| Report | reportlab, python-docx |
| UI (workbench) | streamlit, plotly |
| Optional NL | google-genai (unset → offline planner) |
| Dev | pytest, ruff, httpx |

**Frontend** — [`frontend/package.json`](frontend/package.json): React 19, TanStack Router/Query, Tailwind 4, Vite, D3.

**Config (no code change):** `config/settings.yaml` (window `W`, merge keys), `config/scoring_rules.yaml` (rule thresholds), `config/profiles/**` (bank / CDR / IPDR layouts).

---

## Deployment

| Mode | Command | Serves |
|------|---------|--------|
| Local (recommended for evaluation) | uvicorn + `npm run dev` as above | API :8000, React :8080 |
| Docker | `docker compose up -d --build` | API :8000, Streamlit :8501 |
| CLI only | `python scripts/run_pipeline.py --input datasets/raw/demo` | no servers |

Image details: multi-stage `Dockerfile`, runtime user **uid 10001**, no compiler in the final image, Streamlit telemetry off. Compose health-checks `/health` (API) and Streamlit’s `_stcore/health`.

Production notes:

- Copy `.env.example` → `.env`. Set `ERAKSHAK_JWT_SECRET` (≥32 chars) and both passwords. Unset passwords → a random one is logged once per boot.
- `datasets/` and `data/` are volume-mounted; **do not bake real evidence into the image** (`.dockerignore` denies `datasets/` by default).
- After a code or profile change, pass `"force": true` on `/v1/analyze` or delete `data/analysis_cache/` — durable snapshots outlive a restart.

Operator commands and failure modes: **[`docs/handbook/RUNBOOK.md`](docs/handbook/RUNBOOK.md)**.

There is no Kubernetes / cloud chart. Evaluation target is local or Compose.

---

## Tests

From the repo root, with the venv activated:

```bash
# Backend
python -m pytest backend/tests -p no:warnings --tb=short
python -m ruff check backend/ scripts/

# Frontend
cd frontend
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/vite build
```

On Windows use `.\.venv\Scripts\python.exe` if `python` is not the venv interpreter. CI (`.github/workflows/ci.yml`) runs ruff, pytest, and `docker build` on Python 3.11.

---

## Documentation index

Start at **[`docs/README.md`](docs/README.md)** — it marks which files are live vs archived.

| Document | What evaluators get |
|----------|---------------------|
| [GETTING_STARTED.md](GETTING_STARTED.md) | Setup, three UIs, feature checklist, troubleshooting |
| [docs/handbook/ARCHITECTURE.md](docs/handbook/ARCHITECTURE.md) | Pipeline stage contracts |
| [docs/handbook/API.md](docs/handbook/API.md) | All 17 endpoints, verified |
| [docs/handbook/DATA_MODEL.md](docs/handbook/DATA_MODEL.md) | Canonical Event / Entity / transfer / risk shapes |
| [docs/handbook/RUNBOOK.md](docs/handbook/RUNBOOK.md) | Commands, timings, failure modes |
| [docs/PS_COMPLIANCE_AND_FIX_PLAN.md](docs/PS_COMPLIANCE_AND_FIX_PLAN.md) | 19 problem-statement requirements with measured evidence |
| [research/](research/) | Original problem statement and planning docs 00–12 |

`docs/archive/` is history only and must not be used as status.

---

## License

Internal / hackathon project. **Do not commit real case data**, `.env`, or `*.db` files.
