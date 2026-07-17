# Backend Understanding Summary

## What the System Actually Does

ERakshak is a **forensic intelligence platform** for financial-cybercrime investigators. It takes three types of high-volume, heterogeneous data — **bank statements** (Excel/PDF/CSV), **CDR** (Call Detail Records), and **IPDR** (Internet Protocol Detail Records) — and fuses them into a single investigation-ready picture.

The core value proposition is **cross-dataset fusion**: the decisive evidence in a fraud case lives at the intersection of financial and telecom data. ERakshak automates the process of ingesting → normalizing → resolving entities → correlating on a unified timeline → detecting suspicious patterns → scoring risk → visualizing networks → exporting forensic reports.

### The Pipeline (9 stages)

```
ingest → normalize → resolve entities → build timeline → correlate
       → build money-flow → detect + risk-score → build graph → persist
```

Each stage is a discrete service with store-in/store-out contracts, orchestrated by [pipeline.py](file:///c:/Users/tarun/OneDrive/Documents/E-Rakshak/backend/app/pipeline.py).

### The Fusion Bridge

Bank data and telecom data have no obvious common key. ERakshak bridges them **deterministically** via the registered mobile number on bank statements (links `ACCOUNT_NO ↔ PHONE`). Telecom data links `PHONE ↔ IMEI ↔ IP` through CDR/IPDR co-occurrence. Connected components over this identifier graph merge all related identifiers into a single entity — making the "call + online + transfer within W minutes" signature detectable per person.

**CGNAT Guard**: Public IP is deliberately excluded from merge keys. Carrier-grade NAT means many subscribers share one public IP, so merging on it would wrongly collapse innocent people. A circuit breaker flags entities that merge more than 50 identifiers.

---

## Who the Primary Users Are

| Role | Description |
|------|-------------|
| **Investigator / Analyst** | Primary user. Uploads datasets, explores correlations, reviews anomalies, drills into entities, exports forensic reports |
| **Senior Investigator / Reviewer** | Reviews findings, validates evidentiary timelines, signs off on reports |
| **System Administrator** (optional) | Manages deployment, access control, data retention |

The system is designed for **authorized investigators** working on lawfully obtained data in a single-tenant environment. It is not a multi-tenant SaaS or mass-surveillance tool.

---

## Core Investigation Workflow

1. **Load data** — select a dataset folder; parsers auto-detect format & layout
2. **Review overview** — headline counts + top risk entities with reasons
3. **Explore the network** — money-flow (red) and communication (blue) edges; node color = risk, size = degree
4. **Inspect entities** — drill into resolved identifiers and rule flags with specific reasons
5. **Follow the timeline** — per-entity unified timeline of transactions, calls, IP sessions
6. **Confirm coincidences** — call+IP+transfer coincidences within window W, with evidence and provenance
7. **Search/filter** — by entity, amount range, type, or free text
8. **Export** — forensic report (PDF/Word) with summary, correlation evidence, money-flow findings, STR draft

---

## Backend Strengths

### Architecture
- **Modular monolith** with clean service boundaries; each pipeline stage is independently testable
- **Store-in/store-out** contract per service enables future microservice extraction
- **Configuration-driven**: correlation window W, anomaly thresholds, and field mappings are all externalized in YAML (`config/settings.yaml`, `config/scoring_rules.yaml`, `config/profiles/`)

### Data Pipeline
- **Deterministic entity resolution** via connected components — explainable and forensically defensible
- **Provenance everywhere** — every normalized event retains source file, sheet, row, offset
- **Hybrid detection**: FATF-style rules (structuring, rapid in-out, layering, circular flow, mule, call-transfer coincidence) + Isolation Forest ML anomaly scoring
- **Composite risk score** (0–100): `70% rule + 30% ML`, banded into low/medium/high
- **Bounded compute**: exponential graph algorithms (cycle enumeration, layering DFS) have count and wall-clock caps

### API
- **FastAPI** with versioned `/v1` endpoints, JWT+bcrypt auth, RBAC, audit logging
- **Consistent error schema** (`{error: {code, message}}`)
- **Pipeline caching** via `@lru_cache` keyed on `(dataset, window)`
- **CORS** configured for frontend dev server origins

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Public liveness check |
| `POST` | `/v1/auth/token` | OAuth2 password flow → JWT |
| `GET` | `/v1/datasets` | List available dataset folders |
| `POST` | `/v1/analyze` | Run full pipeline → summary + correlations + top risk |
| `GET` | `/v1/entities/{ds}` | Paginated entities with risk & flags |
| `GET` | `/v1/events/{ds}` | Paginated events with filtering |
| `GET` | `/v1/graph/{ds}` | Network payload `{nodes, edges}` |

### Data Model (SQLAlchemy)
- **`Entity`** — resolved actor (PERSON/ACCOUNT/PHONE/IP), carries `risk_score`
- **`EntityIdentifier`** — single identifier belonging to an entity (ACCOUNT_NO/PHONE/IP/UPI_ID/IMEI/IMSI/BENEFICIARY)
- **`Event`** — unified timeline record (TRANSACTION/CALL/IP_SESSION) with `attributes` JSON and `provenance` JSON
- **`EntityLink`** — graph edge (MONEY_FLOW/COMMUNICATION/SHARED_IDENTIFIER) with weight

### Other Strengths
- **Synthetic data generator** with ground-truth labels for validation
- **Detection recall 1.0** on all 15 demo scenarios
- **18 passing tests** covering API auth, CGNAT regression, parser robustness, persistence
- **CI pipeline** with ruff + pytest + Docker build
- **Forensic report generation** (PDF via ReportLab + Word via python-docx + STR)

---

## Backend Limitations

### API Gaps
1. **No report export API endpoint** — PDF/Word/STR generation exists in the backend but is not exposed via FastAPI. The frontend cannot trigger report downloads.
2. **No file upload endpoint** — the API operates on pre-existing `datasets/raw/` folders. Investigators cannot upload files through the React frontend.
3. **No entity detail endpoint** — there's no `/v1/entities/{ds}/{entity_id}` to get a single entity's full profile, timeline, and connected entities.
4. **No correlation detail endpoint** — correlations are only returned as part of `/v1/analyze` (capped at 100).
5. **No search endpoint** — despite the `search/` module existing in the backend, no search API is exposed.
6. **No configuration endpoint** — window W and thresholds can only be changed per-request, not inspected or modified via API.
7. **No WebSocket/SSE for pipeline progress** — analysis is synchronous; large datasets will timeout.

### Data Access
8. **Pipeline results cached in-memory** with `@lru_cache(maxsize=8)` — results are lost on restart; no persistent query layer.
9. **No cursor-based pagination** — offset pagination with high offsets is inefficient on large datasets.
10. **Events endpoint has no entity filter** — you can filter by `event_type` but not by `entity_id`, making per-entity timelines impossible via API alone.

### Scale
11. **In-memory processing** (pandas/NetworkX) — no streaming or chunked pipeline for very large datasets.
12. **SQLite default storage** — suitable for prototype but not production concurrent access.
13. **Graph payload is returned in full** — no subgraph filtering; large graphs will be expensive to render.

---

## Important Frontend Considerations

### Must-Account-For

1. **Backend starts pipeline on every `/v1/analyze` call** if not cached — expect 5-30 second latency on first request. Frontend must handle long loading states gracefully, ideally with progress indication.

2. **Authentication is JWT bearer tokens** — frontend must persist tokens, handle 401 redirects, and implement token refresh (currently no refresh endpoint — tokens expire; re-login needed).

3. **All data keys use the backend's naming conventions** — `entity_id` (UUID strings), `risk_score` (float 0-100), `rule_flags` (array of `{rule, detail, weight}`), `band` enum. Frontend mappers already translate these.

4. **Provenance is critical for evidentiary value** — every event, flag, and correlation must show its provenance trail (source file → row → profile). This is a legal/forensic requirement, not just a nice-to-have.

5. **Entity types are derived from identifier composition** — an entity with both ACCOUNT_NO and PHONE identifiers is an "individual"; one with only PHONE is a "phone entity". Frontend must handle this derivation.

6. **Graph nodes include `external` boolean and `community` integer** — external entities (counterparties seen in data but not primary subjects) should be visually distinct. Community detection enables cluster highlighting.

7. **Money flow series is returned as `{t: string, inflow: number, outflow: number}`** in crores (÷ 1e7). Frontend must match this unit.

8. **Correlation hits structure is `{entity_id, entity_label, window_minutes, transaction, call, ip_session}`** — each leg has its own time/provenance block. The frontend currently flattens these.

### API Workarounds Needed

9. **No report download**: Show preview + toast "export not wired" (current approach is acceptable for now, but should be wired when API adds the endpoint).

10. **No file upload**: The Upload page should either (a) show instructions for placing files in `datasets/raw/`, or (b) implement a simple file-drop that writes to the backend's filesystem if such an endpoint is added.

11. **Per-entity timeline**: Must be assembled client-side from the `/v1/events/{ds}` response, filtering by `entity_id` in the mapper layer.

### Design Implications

12. **Dense data, not pretty dashboards** — investigators spend hours in the tool. Prioritize information density, keyboard navigation, and fast drill-down over animated cards and decorative whitespace.

13. **Forensic context requires explicit trust signals** — show provenance, methodology, confidence scores, and assumption caveats prominently. Analysts need to know *why* something was flagged, not just *that* it was.

14. **Three-dataset fusion is the differentiator** — the UI must make the Bank↔CDR↔IPDR intersection visually obvious. Color-code by dataset source throughout.

15. **Risk scoring methodology should be transparent** — show the 70/30 rule/ML split, individual rule weights, and ML anomaly scores. Investigators need to defend findings in court.
