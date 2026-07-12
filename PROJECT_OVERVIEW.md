# ERakshak — Project Overview

**AI-Powered Financial & Telecom Dataset Analyzer** · Problem Statement `ERH26_PS_03` (Bank, CDR & IPDR Fusion) · Domain: Big Data and Analytics

---

## 1. What this project is

ERakshak is a **forensic intelligence platform** for financial-cybercrime investigators. Its job is to take three kinds of high-volume, messy, real-world data and fuse them into a single investigation-ready picture:

| Dataset | What it holds | Source |
|---------|---------------|--------|
| **Bank statements** | Money movement (transactions) | Banks — Excel / PDF / CSV, layouts vary bank-to-bank |
| **CDR** (Call Detail Records) | Who called whom, when, how long | Indian telecom operators (Jio, Airtel, Vi, BSNL) |
| **IPDR** (Internet Protocol Detail Records) | Which subscriber used which IP, when | Indian telecom operators |

The decisive evidence in a fraud case usually lives at the **intersection** of these three sources — e.g. *a scammer calls a victim, is online at the same time, and a transfer leaves the victim's account within minutes*. Correlating that by hand across thousands of rows is impractical. ERakshak automates it: it **ingests → normalizes → resolves entities → correlates on a timeline → detects suspicious patterns → scores risk → visualizes networks → exports a forensic report.**

### The five capability pillars
1. **Multi-format ingestion & parsing** — heterogeneous bank layouts (Excel/PDF/CSV) + CDR + IPDR, with schema auto-detection into a canonical model.
2. **Cross-dataset fusion** — one entity model (account/phone/IP) and one timeline; detect temporal coincidences; link accounts and numbers via shared identifiers (UPI ID, IP, IMEI, beneficiary).
3. **Anomaly & pattern detection** — rules + ML for structuring, rapid in-and-out, layering, circular flows, mule accounts; per-entity risk scoring.
4. **Visualization & reporting** — money-flow and communication network graphs, timeline drill-down, filter/search, exportable PDF/Word forensic report.
5. **(Bonus)** — automated Suspicious Transaction Report (STR), risk heat maps, natural-language query.

---

## 2. How it works — the pipeline

The heart of the system is an orchestrated pipeline ([backend/app/pipeline.py](backend/app/pipeline.py)) that runs a directory of Bank/CDR/IPDR files through nine stages and produces one `Investigation` object that the dashboard and reports consume. Each stage stores its output so it stays independently testable ("store-in / store-out").

```
ingest → normalize → resolve entities → build timeline → correlate
       → build money-flow → detect + risk-score → build graph → (persist)
```

| Stage | Module | What it does |
|-------|--------|--------------|
| **Ingestion** | [ingestion/](backend/app/ingestion/) | Detects a file's format/type/bank-profile, parses `.xlsx` / `.csv` / `.pdf`, logs rejects. Parsers live in `parsers/` (`excel.py`, `pdf.py`, `tabular.py`). |
| **Normalization** | [normalization/](backend/app/normalization/) | Maps every source into the canonical model; normalizes phone (E.164 `+91`), IP, datetime (→ Asia/Kolkata), amount; mines narration text; attaches provenance. |
| **Entity resolution** | [entity_resolution/service.py](backend/app/entity_resolution/service.py) | Deterministic identifier-graph → connected components = resolved real-world entities (the "fusion"). |
| **Correlation** | [correlation/](backend/app/correlation/) | Builds a per-entity timeline, then finds windowed **call + IP + transfer** coincidences. |
| **Money-flow** | [graph/money_flow.py](backend/app/graph/money_flow.py) | Turns transactions into directed transfers (shared UTR/beneficiary). |
| **Detection** | [detection/](backend/app/detection/) | Rules + Isolation Forest → composite 0–100 risk score per entity. |
| **Graph** | [graph/service.py](backend/app/graph/service.py) | Builds money-flow + communication graph with centrality/community metrics. |
| **Reporting** | [reporting/service.py](backend/app/reporting/service.py) | Generates the forensic PDF/Word report + STR. |
| **Dashboard** | [dashboard/](backend/app/dashboard/) | Streamlit investigator UI (timeline, network, search, report). |

### The fusion bridge (the clever bit)
Bank data and telecom data have no obvious common key. ERakshak bridges them **deterministically** via the **registered mobile number on the bank statement** — that links `ACCOUNT_NO ↔ PHONE`. Telecom data then links `PHONE ↔ IMEI ↔ IP` through co-occurrence in CDR/IPDR. Running connected-components over that identifier graph merges a person's bank account, phone, device, and IP sessions into a single entity — so the "call + online + transfer within W minutes" signature becomes detectable per person.

**Important safety design (CGNAT guard):** Public IP is deliberately **excluded** from merge keys. Carrier-grade NAT means many unrelated subscribers share one public IP, so merging on it would wrongly collapse innocent people into one entity. Only `PHONE`, `ACCOUNT_NO`, `IMEI`, `IMSI` create merge edges. A **circuit breaker** flags any entity that merges more than `max_component_size` (50) identifiers as a likely bad/aliased key needing review.

---

## 3. The canonical data model

Everything maps into one model ([backend/app/models/canonical.py](backend/app/models/canonical.py), SQLAlchemy):

- **`Entity`** — a resolved real-world actor (PERSON/ACCOUNT/PHONE/IP), carries the final `risk_score`.
- **`EntityIdentifier`** — a single identifier (account no, phone, IP, UPI ID, IMEI, IMSI, beneficiary) belonging to an entity; makes linkage first-class.
- **`Event`** — the unified timeline record, one row per parsed source record. Types: `TRANSACTION`, `CALL`, `IP_SESSION`. Type-specific fields live in an `attributes` JSON blob; every event carries an immutable **`provenance`** block (source file, sheet, row, offset, profile) for evidentiary trust.
- **`EntityLink`** — a graph edge (MONEY_FLOW / COMMUNICATION / SHARED_IDENTIFIER).
- **`RiskAssessment`** / **`CorrelationHitRow`** — persisted results with contributing factors and evidence.

---

## 4. Detection & risk scoring

Detection is **rules-first (explainable, defensible)** blended with **unsupervised ML** ([detection/service.py](backend/app/detection/service.py)). Every flag cites its reason; no thresholds are hard-coded — they live in [config/scoring_rules.yaml](config/scoring_rules.yaml).

**Rule detectors** ([detection/rules.py](backend/app/detection/rules.py)):
- **Structuring** — ≥3 credits clustered just below a reporting threshold (smurfing).
- **Rapid in-out** — ≥80% of a credit forwarded within an hour (pass-through).
- **Mule account** — high counterparty fan-in combined with rapid forwarding.
- **Circular flow** — A→B→…→A money loops in the transfer graph.
- **Layering** — funds hopping across ≥3 accounts within a short span.
- **Call-transfer coincidence** — the signature call + IP + transfer fusion pattern.

**ML detector** — an `IsolationForest` over 11 behavioral features (txn counts, in/out totals, fan-in/out, IP/IMEI counts, night ratio, rapid-forward ratio, coincidence count). It surfaces anomalies the rules miss. Fitted models are versioned and persisted to `data/models/` for reproducibility.

**Composite score (0–100)** = `70% × rule component + 30% × ML component`, banded into **low (0–39) / medium (40–69) / high (70–100)**.

Graph algorithms that are worst-case exponential (cycle enumeration, layering DFS) are **bounded** by count and wall-clock caps (`config/settings.yaml → graph:`) so a dense graph can't hang the pipeline — results are marked partial if a cap trips.

---

## 5. Interfaces

- **Streamlit dashboard** ([dashboard/app.py](backend/app/dashboard/app.py)) — the primary investigator UI: timeline, network graph, search, report export. (React + D3 is a later upgrade.)
- **FastAPI service** ([backend/app/api/main.py](backend/app/api/main.py)) — versioned (`/v1`), JWT-authenticated, RBAC-protected (`analyst` role), consistent error schema, audit logging. Key endpoints: `POST /v1/auth/token`, `GET /v1/datasets`, `POST /v1/analyze`, `GET /v1/entities/{ds}`, `GET /v1/graph/{ds}`. `GET /health` is public.
- **CLI** — [scripts/run_pipeline.py](scripts/run_pipeline.py) runs the pipeline directly on a folder.

---

## 6. Configuration-driven design

A core principle (NFR-6): **no tunables hard-coded**. Everything is externalized:

- [config/settings.yaml](config/settings.yaml) — correlation window `W` (default 10 min), timezone, entity-resolution merge keys, upload limits, graph caps, persistence URL, target operators.
- [config/scoring_rules.yaml](config/scoring_rules.yaml) — FATF-style rule thresholds + risk weights + ML config.
- [config/profiles/](config/profiles/) — per-source (bank / cdr / ipdr) field-mapping profiles that tell parsers how each layout maps into the canonical model.

---

## 7. Synthetic data

Because no real case data is available (and shouldn't be committed), a **synthetic data generator** ([tools/synthetic_data_generator/](tools/synthetic_data_generator/)) produces realistic, fused, *labeled* Bank + CDR + IPDR datasets with a `ground_truth.json` — so detectors can be validated (true vs. false positives) and the demo has believable material. Datasets live under [datasets/raw/](datasets/raw/) in tiers (`smoke`, `demo`).

```bash
python -m tools.synthetic_data_generator.generate --tier smoke --out datasets/raw/smoke
```

---

## 8. Technology stack

| Layer | Tools |
|-------|-------|
| Data & parsing | pandas, numpy, openpyxl, pdfplumber, python-dateutil |
| Schema / persistence | SQLAlchemy, pydantic, SQLite (default; Postgres via `DATABASE_URL`) |
| Graph & ML | networkx, scikit-learn (Isolation Forest), joblib |
| Reporting | reportlab (PDF), python-docx (Word), Jinja2 |
| API & security | FastAPI, uvicorn, PyJWT, bcrypt |
| UI | Streamlit, plotly, matplotlib |
| Dev / test | pytest, httpx, ruff |
| Deploy | Dockerfile + docker-compose |

The architecture is a **modular monolith** — clean service boundaries so Neo4j (graph) and Elasticsearch (search) can be swapped in behind the same contracts if scale demands it, without a rewrite.

---

## 9. Repository layout

| Path | Purpose |
|------|---------|
| [Research/](Research/) | 13 pre-implementation planning docs (00–12): problem analysis, requirements, architecture, risk, etc. |
| [config/](config/) | Externalized tunables + source→canonical mapping profiles |
| [backend/app/](backend/app/) | All pipeline modules + API |
| [backend/tests/](backend/tests/) | pytest suite (pipeline, normalizers, API/persistence, security/parsing) |
| [tools/synthetic_data_generator/](tools/synthetic_data_generator/) | Labeled synthetic dataset generator |
| [datasets/](datasets/) | raw / metadata datasets + ground truth |
| [data/](data/) | Runtime DB, fitted models, report outputs (gitignored) |
| [docs/](docs/) | Delivered docs + ADRs (architecture, canonical schema, API, deployment, investigation workflow) |
| [scripts/](scripts/) | Dev/ops helpers (CLI pipeline runner) |

---

## 10. How to run

```bash
# Setup
python -m venv .venv
.venv\Scripts\activate            # Windows (source .venv/bin/activate on Unix)
pip install -r requirements.txt

# Generate demo data
python -m tools.synthetic_data_generator.generate --tier smoke --out datasets/raw/smoke

# Run the pipeline on a folder
python scripts/run_pipeline.py datasets/raw/smoke

# Launch the investigator dashboard
streamlit run backend/app/dashboard/app.py

# Or the API
uvicorn backend.app.api.main:app --reload   # docs at http://localhost:8000/docs
```

---

## 11. Design principles worth remembering

- **Fusion is deterministic and explainable** — no black-box entity merging; every link traces to a shared identifier.
- **Provenance everywhere** — every normalized event remembers exactly which file/row/offset it came from, so findings are evidentiary.
- **Config over code** — windows, thresholds, and mappings are data, not source; tunable without redeploy.
- **Bounded compute** — exponential graph algorithms have hard count/time caps so large datasets stay safe.
- **Privacy-aware** — CGNAT-aware IP handling avoids false merges; the tool assumes lawful, authorized use on legally obtained data.
