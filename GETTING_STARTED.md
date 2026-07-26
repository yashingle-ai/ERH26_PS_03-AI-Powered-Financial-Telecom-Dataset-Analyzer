# Getting started — run and test ERakshak locally

Everything in this guide was run on a clean checkout before it was written. Commands
are given for **Windows (PowerShell)** and **macOS / Linux (bash)** where they differ.

If you only have five minutes, do [Quick start](#quick-start) then
[Journey 1](#journey-1-the-react-console-main-ui).

---

## Contents

- [What you're running](#what-youre-running)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Read this first — four things that will trip you up](#read-this-first--four-things-that-will-trip-you-up)
- [Journey 1: the React console (main UI)](#journey-1-the-react-console-main-ui)
- [Journey 2: the Streamlit dashboard (analyst workbench)](#journey-2-the-streamlit-dashboard-analyst-workbench)
- [Journey 3: the CLI (no servers needed)](#journey-3-the-cli-no-servers-needed)
- [Journey 4: the API directly](#journey-4-the-api-directly)
- [Feature test checklist](#feature-test-checklist)
- [Running the test suites / CI locally](#running-the-test-suites--ci-locally)
- [Working with your own data](#working-with-your-own-data)
- [Troubleshooting](#troubleshooting)
- [Known gaps](#known-gaps)

---

## What you're running

ERakshak fuses **bank statements, CDR and IPDR** onto one entity + timeline model,
correlates events across them, scores risk, and produces investigation output.

There are **three** front doors onto the same pipeline. Pick by what you're testing:

| Surface | URL | What it's for |
|---|---|---|
| **React console** | `http://localhost:8080` | The product UI — dashboards, network graph, timeline |
| **Streamlit dashboard** | `http://localhost:8501` | Analyst workbench — has features the React app doesn't, incl. file upload |
| **CLI** | — | Fastest way to prove the pipeline works; no servers |

The React console talks to the **FastAPI** backend on `http://127.0.0.1:8000`.
Streamlit and the CLI call the pipeline in-process — they do **not** need the API running.

---

## Prerequisites

- **Python 3.11+** (CI pins 3.11; 3.13 also works)
- **Node.js 20+** (tested on 22)
- **Docker** — optional, only for the container build
- ~2 GB free disk for dependencies

```bash
python --version && node --version && npm --version
```

---

## Quick start

```bash
git clone https://github.com/yashingle-ai/ERH26_PS_03-AI-Powered-Financial-Telecom-Dataset-Analyzer.git
cd ERH26_PS_03-AI-Powered-Financial-Telecom-Dataset-Analyzer
```

### 1. Backend

**Do not use the `.venv` folder that ships in the repo** — see
[gotcha #1](#1-the-venv-in-the-repo-is-not-usable-on-windows). Make your own:

<details open>
<summary><b>Windows (PowerShell)</b></summary>

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
</details>

<details>
<summary><b>macOS / Linux</b></summary>

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
</details>

### 2. Prove it works before starting any server

```bash
python scripts/run_pipeline.py --input datasets/raw/smoke
```

Expected — a JSON summary on stdout:

```json
{
  "files": 19, "events": 547, "transactions": 305, "calls": 121,
  "ip_sessions": 121, "rejected_rows": 0, "reject_entries": 0,
  "entities": 8, "correlation_hits": 2, "transfers": 142,
  "high_risk_entities": 1
}
```

> On PowerShell this also prints a wall of **red text**. That is not an error —
> see [gotcha #2](#2-red-text-in-powershell-is-not-a-failure).

### 3. Frontend

```bash
cd frontend
npm install
```

---

## Read this first — four things that will trip you up

### 1. The `.venv` in the repo is not usable on Windows

The committed `.venv/` is a **POSIX-layout** virtualenv (`bin/`, not `Scripts/`) — it was
created on Linux/macOS. On Windows `.\.venv\Scripts\python.exe` does not exist. Create
your own as shown above. (It's gitignored, so yours won't be committed.)

### 2. Red text in PowerShell is not a failure

The app logs to **stderr**. PowerShell 5.1 wraps *any* stderr from a native command in a
red `NativeCommandError` block — even on success. Check the exit code, not the colour:

```powershell
python scripts/run_pipeline.py --input datasets/raw/smoke
echo "exit: $LASTEXITCODE"      # 0 means it worked
```

To silence it: append `2>$null`, or use Git Bash / WSL.

### 3. The analyst password is regenerated on every boot unless you set it

Start the API with no env vars and it logs something like:

```
WARNING ERAKSHAK_ANALYST_PASSWORD not set — generated a random analyst password: zZGHGiCxKQtfrnm-
WARNING ERAKSHAK_JWT_SECRET not set — using an EPHEMERAL secret (dev only).
```

A **new password each restart**, and all tokens invalidate. This is the single most common
reason "login is broken". Set them (see [step 1 of Journey 1](#journey-1-the-react-console-main-ui)).

### 4. Run backend commands from the repo root

Config paths in `config/settings.yaml` are resolved relative to the working directory.
Model output is anchored to the repo root, but config loading is not — so `cd` to the
repo root before running the CLI, the API or Streamlit.

---

## Journey 1: the React console (main UI)

You need **two terminals**.

### Terminal 1 — API

<details open>
<summary><b>Windows (PowerShell)</b></summary>

```powershell
$env:ERAKSHAK_ANALYST_PASSWORD = "devpass123"
$env:ERAKSHAK_ADMIN_PASSWORD   = "devadmin123"
$env:ERAKSHAK_JWT_SECRET       = "local-dev-secret-at-least-32-characters-long"
python -m uvicorn backend.app.api.main:app --reload --port 8000
```
</details>

<details>
<summary><b>macOS / Linux</b></summary>

```bash
export ERAKSHAK_ANALYST_PASSWORD=devpass123
export ERAKSHAK_ADMIN_PASSWORD=devadmin123
export ERAKSHAK_JWT_SECRET=local-dev-secret-at-least-32-characters-long
python -m uvicorn backend.app.api.main:app --reload --port 8000
```
</details>

Check it: <http://127.0.0.1:8000/health> → `{"status":"ok"}`
Interactive API docs: <http://127.0.0.1:8000/docs>

### Terminal 2 — frontend

```bash
cd frontend
npm run dev
```

Opens on **<http://localhost:8080>**. The API base URL defaults to `http://127.0.0.1:8000`;
override it with `frontend/.env` if you changed the port:

```
VITE_API_BASE_URL=http://127.0.0.1:8000
```

### The walkthrough

Follow these in order — each step depends on the last.

| # | Screen | What to do | What you should see |
|---|---|---|---|
| 1 | **Login** | `analyst` / `devpass123` | Redirect into the console. Wrong password → inline red error, no crash |
| 2 | **Topbar** | Open the dataset dropdown | `demo` and `smoke` listed. Pick **`demo`** — it's the larger set |
| 3 | **Overview** | — | Stat tiles populate. **Money flow** area chart with a legend (Inflow teal / Outflow orange). **Risk distribution** bars. Top-entities table |
| 4 | **Theme** | Click the sun/moon in the topbar | Light / Dark / System. Flip between them — every surface should follow, including the graph HUD and command palette |
| 5 | **Entities** | Sort by risk; click a row | Detail panel: identifiers, rule flags, features |
| 6 | **Detections** | — | Rule-flagged entities grouped by band. Click a rule to filter |
| 7 | **Timeline** | Scrub / zoom | Transactions, calls and IP sessions as three colour-coded tracks |
| 8 | **Network graph** | Drag nodes, scroll to zoom | D3 force graph. Node colour = risk band. Toolbar + minimap. Try fullscreen |
| 9 | **Correlations** | — | Money-movement events that coincide with a call/IP session inside window `W` — this is the core fusion result |
| 10 | **Reports** | — | Print-preview styled report. **Stays light in dark mode on purpose** — it simulates paper. Ctrl/Cmd+P to check print CSS |
| 11 | **Command palette** | `Ctrl/Cmd + K` | Jump to any page or entity |
| 12 | **Upload & Ingest** | — | Shows "HTTP upload is not available yet" — [expected](#known-gaps), not a bug |
| 13 | **Sign out** | User menu → Sign out | Back to login; protected routes redirect |

**Accessibility spot-check:** tab through with the keyboard — focus rings should be
visible on every control. If your OS is set to reduced motion, animations should be off.

---

## Journey 2: the Streamlit dashboard (analyst workbench)

This surface has features the React console doesn't — including **file upload** and the
mapping/quality tooling. No API server needed.

```bash
python -m streamlit run backend/app/dashboard/app.py --server.address 127.0.0.1
```

Opens on **<http://localhost:8501>**. Sign in with the same analyst credentials.

> **Pass `--server.address 127.0.0.1`.** Streamlit binds to *all* interfaces by default and
> advertises a Network and External URL — anyone on your LAN could reach the dashboard, and
> with a real case loaded that is an evidence exposure. Binding to loopback prevents it.

Sidebar: pick the dataset, set **correlation window W (minutes)**, toggle **Parse PDFs**
(slow on real cases), or upload bank/CDR/IPDR files directly.

Eleven tabs, each worth a look:

| Tab | What to check |
|---|---|
| 📊 **Overview** | Counts + top-risk table |
| 🕸️ **Network** | Graph with min-risk / min-degree filters and 1-hop focus |
| 🧑 **Entities** | Resolved entities and their identifiers |
| ⏱️ **Timeline** | Fused event timeline |
| 🎯 **Correlations** | The bank↔CDR↔IPDR coincidences, with explanations |
| 🔎 **Search** | Structured filtering |
| 📄 **Report** | Generates PDF/DOCX into `data/outputs/` |
| 🔥 **Heat map** | Activity by hour/day |
| 🗣️ **Ask** | Natural-language query — try the examples [below](#natural-language-query-f1) |
| 🧪 **Quality** | Ingestion rejects (B3), balance breaks (A5), fuzzy link suggestions (C3) |
| 🛠 **Mapping** | Manual column mapping for low-confidence files (B5) |

**Try changing W** (e.g. 10 → 60 minutes) and watch the correlation count move. That is
the central tunable of the whole system.

---

## Journey 3: the CLI (no servers needed)

Fastest way to confirm the pipeline is healthy.

```bash
# Basic run
python scripts/run_pipeline.py --input datasets/raw/smoke

# Wider correlation window
python scripts/run_pipeline.py --input datasets/raw/demo --window 60

# Score against the planted ground truth (synthetic sets only)
python scripts/run_pipeline.py --input datasets/raw/smoke --eval

# Write results to the database
python scripts/run_pipeline.py --input datasets/raw/demo --persist

# Save the summary
python scripts/run_pipeline.py --input datasets/raw/demo --save out.json
```

`--eval` is the one to run if you want evidence the detection logic is actually correct:
it compares detections against `ground_truth.json` shipped with the synthetic datasets.

### Generating a fresh synthetic dataset

```bash
python -m tools.synthetic_data_generator.generate --tier smoke --out datasets/raw/smoke
python -m tools.synthetic_data_generator.generate --tier demo  --out datasets/raw/demo
```

---

## Journey 4: the API directly

Easiest via the Swagger UI at **<http://127.0.0.1:8000/docs>** — click **Authorize**,
enter `analyst` / `devpass123`, then try any endpoint.

By curl:

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/v1/auth/token \
  -d "username=analyst&password=devpass123" | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"
```

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness (public) |
| `POST /v1/auth/token` | Login → bearer token |
| `GET /v1/datasets` | List available datasets |
| `POST /v1/analyze` | Full run: summary, file counts, money-flow series, correlations, top risk |
| `GET /v1/entities/{ds}` | Ranked entities (paginated) |
| `GET /v1/events/{ds}` | Fused events (paginated, filter by `event_type`) |
| `GET /v1/graph/{ds}` | Network graph payload |
| `GET /v1/data-quality/{ds}` | Balance breaks + ingestion rejects |
| `GET /v1/suggestions/{ds}` | Review-only same-actor candidates |
| `POST /v1/query/{ds}` | Natural-language query |

```bash
curl -s -H "$H" http://127.0.0.1:8000/v1/datasets
curl -s -H "$H" -X POST http://127.0.0.1:8000/v1/analyze \
  -H "Content-Type: application/json" -d '{"dataset":"demo","window_minutes":10}'
curl -s -H "$H" "http://127.0.0.1:8000/v1/data-quality/demo"
curl -s -H "$H" "http://127.0.0.1:8000/v1/suggestions/demo?threshold=0.75"
```

### Natural-language query (F1)

Rule-based and offline — deterministic and auditable, no API key needed.

```bash
curl -s -H "$H" -X POST http://127.0.0.1:8000/v1/query/demo \
  -H "Content-Type: application/json" -d '{"q":"transfers over 100000"}'
```

Supported phrasings:

| Query | Returns |
|---|---|
| `transfers over 100000` | Transactions ≥ threshold |
| `high risk entities` | Entities in a risk band (`high` / `medium` / `low`) |
| `calls to 9099102222` | Calls involving that number |
| `events on 2026-06-01` | Everything on that date |
| `transfers within 10 minutes of a call` | Correlation coincidences |

Anything it can't parse returns a helpful message with examples rather than an error.

---

## Feature test checklist

Tick these off and you've covered the product.

**Ingestion & normalization**
- [ ] Mixed formats parse — CSV, XLSX and PDF bank statements all land as events
- [ ] `rejected_rows` is 0 on the synthetic sets
- [ ] `/v1/data-quality/{ds}` lists parsed files and any rejects

**Entity resolution**
- [ ] Entity count is far lower than event count (identities were actually merged)
- [ ] An entity shows multiple identifier kinds (phone + account + IMEI)
- [ ] `/v1/suggestions/` returns review-only candidates and **never auto-merges**

**Correlation — the core feature**
- [ ] `correlation_hits > 0` on `demo`
- [ ] Raising `W` increases hits; lowering it reduces them
- [ ] Each hit explains itself (which transaction, which call, which IP session)

**Detection & risk**
- [ ] Entities carry a 0–100 score and a low/medium/high band
- [ ] Rule flags list the contributing factors (explainability)
- [ ] `--eval` scores sensibly against ground truth

**Visualization**
- [ ] Network graph renders, drags, zooms
- [ ] Timeline shows all three event types distinctly
- [ ] Money-flow chart has a legend and does **not** use the risk amber for a series

**Reporting**
- [ ] Streamlit → Report tab produces a file in `data/outputs/`
- [ ] React → Reports print preview looks right in Ctrl/Cmd+P

**Theming (new)**
- [ ] Light / Dark / System all work and persist across reload
- [ ] No white flash on refresh in dark mode
- [ ] Graph HUD, command palette and investigation bar follow the theme

**Security**
- [ ] Unauthenticated request to `/v1/datasets` → 401
- [ ] Bad password → 401, no stack trace
- [ ] Errors come back as `{"error": {"code": …, "message": …}}`

**Hygiene**
- [ ] After browsing the whole app, `git status` is still **clean**

---

## Running the test suites / CI locally

CI runs exactly three steps. You can run all of them:

```bash
# 1. Lint
ruff check backend tools scripts

# 2. Backend tests  → expect "82 passed"
pytest backend/tests -q

# 3. Container build
docker build -t erakshak:ci .
```

Frontend:

```bash
cd frontend
npx tsc --noEmit     # typecheck
npx vitest run       # unit tests → expect "2 passed"
npm run build        # production build
```

---

## Running in Docker

The image is multi-stage: the compiler toolchain needed to install the scientific stack
stays in the build stage, so the runtime image ships no `gcc`.

**Both services at once** — API on 8000, Streamlit dashboard on 8501:

```bash
cp .env.example .env          # then set ERAKSHAK_JWT_SECRET + the two passwords
docker compose up --build
docker compose ps             # both should read "healthy"
```

Without a `.env` the compose defaults are `analyst` / `analyst` and a placeholder JWT
secret — fine for a local demo, **not** for anything holding real case data.

**Just the API:**

```bash
docker build -t erakshak:ci .
docker run --rm -p 8000:8000 \
  -e ERAKSHAK_ANALYST_PASSWORD=your-password \
  -e ERAKSHAK_JWT_SECRET=a-long-random-string \
  -v "$PWD/datasets:/app/datasets" -v "$PWD/data:/app/data" \
  erakshak:ci
```

Notes worth knowing:

- **Leave the password env vars unset and the API generates a random one** and logs it
  once at startup. That is deliberate — no default credential ships in the image — but
  under compose nobody reads that log, so set them explicitly.
- `datasets/` and `data/` are **bind-mounted, never copied in**. `.dockerignore` keeps
  case evidence out of the build context, so the image stays ~4 MB of application code.
- Streamlit's usage telemetry is switched off in the image. A forensic tool should not
  report on its own sessions.
- No `GEMINI_API_KEY` → `/v1/query` falls back to the offline rule-based engine. The
  container never requires network access.

---

## Working with your own data

1. Create a folder under `datasets/raw/<your_case>/`
2. Put files in subfolders by kind — `bank/`, `cdr/`, `ipdr/`
3. Run it:
   ```bash
   python scripts/run_pipeline.py --input datasets/raw/your_case --window 10
   ```
4. If columns aren't recognised, add a profile under `config/profiles/` (see the
   existing bank/CDR/IPDR profiles), or use the Streamlit **🛠 Mapping** tab.
5. To link an account to a phone/wallet manually, copy
   `datasets/entity_map.template.csv` to `entity_map.csv` in your dataset folder.

> ### If you get zero correlation hits on a real case, read this
> The call+IP+transfer correlation only fires when **one entity** owns all three event
> types. Bank statements are keyed by account number and CDR/IPDR by phone, so unless
> something links them the two halves of the case never meet and the hit count is
> legitimately zero — no error is raised.
>
> On the real FIR case in this repo, entity resolution produces 4,987 phone-only
> entities and 131 account-only entities, and **zero** that carry both. Correlation is
> therefore structurally impossible until the bridge exists.
>
> Three ways an account gets bridged to a phone:
> 1. The statement carries a registered mobile in its header block (parsed automatically).
> 2. A UPI narration contains a phone-based VPA, e.g. `UPI/…/9876543210@ybl/…`
>    (mined automatically).
> 3. **You supply it** — the usual case. Investigators hold this from KYC/CAF. Drop an
>    `entity_map.csv` in the dataset folder:
>    ```csv
>    account_no,phone,wallet,upi_id
>    50200099412403,9876543210,,
>    ```
>    No code change needed; the pipeline merges the identifiers into one entity.
>
> Check where you stand before blaming the correlator: if `/v1/entities/{ds}` shows no
> entity with both an `ACCOUNT_NO` and a `PHONE` identifier, you need the map.

> ### ⚠️ Real case data
> `datasets/` is **deny-by-default** in both `.gitignore` and `.dockerignore` — a new case
> folder is ignored automatically, so you cannot accidentally commit evidence or bake it
> into an image. Generated reports (`data/outputs/`), uploads and `data/*.db` are ignored
> for the same reason: they are derived from case data and inherit its sensitivity.
>
> If you add a new output location, add it to **both** ignore files.

---

## Troubleshooting

| Symptom | Cause & fix |
|---|---|
| Red `NativeCommandError` wall in PowerShell | Not an error — stderr logging. Check `$LASTEXITCODE`; append `2>$null` |
| Login fails every restart | `ERAKSHAK_ANALYST_PASSWORD` not set — a new random one is generated each boot. Set it |
| `401` on every API call | Token expired (default 60 min) or the server restarted with an ephemeral JWT secret. Set `ERAKSHAK_JWT_SECRET` |
| Frontend loads but all data is empty | API not running, or wrong `VITE_API_BASE_URL`. Check <http://127.0.0.1:8000/health> |
| CORS errors in the browser console | Frontend on an unexpected port. Defaults allow 5173, 8080, 4173 — otherwise set `ERAKSHAK_CORS_ORIGINS` |
| `.\.venv\Scripts\python.exe` not found | The shipped `.venv` is POSIX-layout. Create your own |
| `ModuleNotFoundError: backend...` | Run from the repo root |
| `docker build` hangs for minutes | You're on a checkout predating `.dockerignore`. Pull `main` |
| `ruff check` fails on import order | `ruff check --fix backend tools scripts` |
| Streamlit port busy | `--server.port 8502` |

---

## Known gaps

Honest list — these are **not** bugs to report:

- **No HTTP file upload.** The API has no upload route; the React "Upload & Ingest" page
  says so. Use the Streamlit uploader, or drop files into `datasets/raw/<name>/`.
- **The three newest endpoints have no UI yet.** `/v1/data-quality`, `/v1/suggestions` and
  `/v1/query` are implemented and typed in `frontend/src/lib/api.ts`, but no React screen
  calls them. Use Streamlit, `/docs`, or curl. The Streamlit **🧪 Quality** and **🗣️ Ask**
  tabs cover the same ground.
- **NL query has two engines.** With `GEMINI_API_KEY` set, a question is translated into
  a validated query object and executed locally; without it, the offline rule-based
  interpreter handles the five canned phrasings. The model only ever receives the question
  plus field names — never case records. Get a free key at
  <https://aistudio.google.com/apikey>.
- **Model persistence is opt-in.** Set `ERAKSHAK_PERSIST_MODEL=1` to write
  `data/models/`. Off by default so that browsing the app never rewrites a tracked
  artifact. Override the location with `ERAKSHAK_MODEL_DIR`.
- **`Research/` vs `research/`.** The repo uses capital-R `Research/`. Avoid creating a
  lowercase twin — it collides on case-insensitive filesystems.
