# ERakshak — AI-Powered Financial & Telecom Dataset Analyzer

**Problem Statement:** ERH26_PS_03 — Bank, CDR & IPDR Fusion · **Domain:** Big Data and Analytics

A forensic intelligence platform that ingests heterogeneous **Bank statements, CDR, and IPDR**,
normalizes them onto a **unified entity + timeline model**, correlates events across datasets, detects
suspicious money-flow / communication patterns, and produces investigation-ready forensic output.

> **Planning docs:** see [`research/`](research/) (Docs 00–12). The build follows the phased plan in
> [`research/08_implementation_planning.md`](research/08_implementation_planning.md) and the layout in
> [`research/09_folder_structure.md`](research/09_folder_structure.md).

## Status

Backend pipeline + FastAPI (`/v1`) + React investigator UI (`frontend/`). Streamlit dashboard still available. See [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) and [`docs/progress.md`](docs/progress.md).

## Quick start (end-to-end)

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
#   $env:ERAKSHAK_JWT_SECRET="dev-secret"
#   $env:ERAKSHAK_ADMIN_PASSWORD="adminpass"
#   $env:ERAKSHAK_ANALYST_PASSWORD="analystpass"
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

Open the Vite URL (often http://localhost:8080 or :5173). Sign in with the API credentials above, then open dataset **smoke**.

### 3. CLI / Streamlit (optional)

```bash
python scripts/run_pipeline.py datasets/raw/smoke
streamlit run backend/app/dashboard/app.py
```

## Repository layout

| Path | Purpose |
|------|---------|
| `research/` | Pre-implementation planning documents (00–12) |
| `config/` | Externalized tunables + mapping profiles (window W, thresholds, layouts) |
| `backend/app/` | Pipeline + FastAPI (`api/`) + Streamlit dashboard |
| `frontend/` | React investigator UI (Lovable / TanStack Start) |
| `tools/synthetic_data_generator/` | Labeled synthetic Bank + CDR + IPDR generator |
| `datasets/` | raw / metadata datasets + ground truth |
| `data/` | runtime DB / models / reports (local outputs gitignored) |
| `docs/` | delivered docs + ADRs (`docs/decisions/`) |
| `scripts/` | dev/ops helpers |

## License

Internal / hackathon project. Do not commit real case data.

## the project is developed by :-
Yash Ingle - u23ai062@coed.svnit.ac.in
Himal Rana -  u23ai053@coed.svnit.ac.in
Ankit Yadav -  u23ai039@coed.svnit.ac.in
Tarun bhutra -  u23ai063@coed.svnit.ac.in
