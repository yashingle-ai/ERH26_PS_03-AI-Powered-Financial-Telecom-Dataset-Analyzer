# 03 — Initial Research Document

**Project:** AI-Powered Financial & Telecom Dataset Analyzer (Bank, CDR & IPDR Fusion)
**Problem Statement ID:** ERH26_PS_03 · **Domain:** Big Data and Analytics
**Document status:** Batch A · Draft 1 · 2026-07-06

---

## 1. Purpose

To research each capability the problem statement requires — and only those — so that architecture
and implementation decisions rest on evidence and industry practice rather than guesswork.

## 2. Objective

For every required topic, establish *what it is, why it is needed (traced to a requirement),
available approaches with pros/cons, a recommended approach with reasoning, and relevant industry
practice*, so Docs 04–08 can adopt recommendations directly.

## 3. Scope

Topics researched are strictly those implied by ERH26_PS_03: multi-format document parsing, CDR/IPDR
formats, canonical data modeling & entity resolution, temporal correlation, graph/network analysis,
anomaly detection (rules + ML), search/indexing, visualization, and forensic reporting. Technology
comparisons are informed by the PS "Suggested Tools" but not limited to them.

> **Note on citations:** URLs are provided where a stable canonical reference exists. This is a
> planning document; any figures should be re-verified against current library docs during
> implementation.

---

## Topic 1 — Multi-Format Bank Statement Parsing (Excel / PDF / CSV)

**What it is.** Extracting tabular transaction data from bank statements delivered as spreadsheets,
PDFs, or CSVs, whose layouts differ by bank. *(Serves FR-1, FR-4, FR-5, NFR-1.)*

**Why it is needed.** Bank statements are a primary input and arrive in heterogeneous layouts; robust
parsing is an explicit evaluation criterion.

**Available approaches.**

| Approach | Tooling | Pros | Cons |
|----------|---------|------|------|
| Spreadsheet parsing | **pandas** + **openpyxl** (xlsx), xlrd (legacy xls) | Mature, fast, handles most Excel | Merged cells / multi-header layouts need handling |
| Text-based PDF tables | **pdfplumber**, **Camelot**, **Tabula** | Good for digitally-generated PDFs with ruled tables | Fails on scanned/image PDFs; layout-sensitive |
| PDF via Java lib | **Apache PDFBox** (PS-suggested) | Robust low-level text extraction | More code; table reconstruction manual |
| OCR fallback | Tesseract / cloud OCR | Handles scanned statements | Slower, error-prone, extra dependency |
| Template/mapping registry | Per-bank column maps + auto-detect | Deterministic, auditable | Needs a mapping per new bank layout |

**Recommended approach.** Use **pandas + openpyxl** for Excel/CSV and **pdfplumber** for text PDFs
(it exposes words *with coordinates*, which helps reconstruct columns), backed by a **per-bank mapping
registry with header auto-detection** that maps any layout into the canonical model (FR-4). Treat OCR
for scanned PDFs as *optional* (Future Consideration), since the PS does not mandate scanned inputs.

**Reasoning.** This matches the PS suggestions (pdfplumber/PDFBox/OpenPyXL), keeps the stack in Python
(consistency with Pandas/ML), and the mapping registry gives the auditability a forensic tool needs.
pdfplumber is preferred over PDFBox to avoid a JVM dependency in an otherwise Python system.

**Industry practice.** Fintech/aggregators (account-aggregator ecosystems, expense tools) universally
combine a parsing library with a per-institution template/mapping layer and a confidence-scored
auto-detector; pure ML table extraction is reserved for truly unknown layouts.

**References.** pdfplumber (github.com/jsvine/pdfplumber), Camelot (camelot-py.readthedocs.io),
openpyxl (openpyxl.readthedocs.io), pandas (pandas.pydata.org).

---

## Topic 2 — CDR & IPDR Formats and Parsing

**What it is.** CDR (Call Detail Records) capture telephony-event metadata (calling/called number,
start time, duration, call type, IMEI/IMSI, cell-tower/LBS location). IPDR (Internet Protocol Detail
Records) capture data-session metadata (subscriber ID/MSISDN, assigned public/private IP + port,
start/end time, bytes, sometimes destination IP). *(Serves FR-2, FR-3, FR-4.)*

**Why it is needed.** These are two of the three required inputs; correlation depends on parsing their
identifiers and timestamps correctly.

**Available approaches.**

| Approach | Pros | Cons |
|----------|------|------|
| Delimited/CSV parsing with per-operator schema map | Simple, fast; fits FR-4 | Requires knowing each operator's columns |
| Schema auto-detection by header/keyword heuristics | Tolerates unknown layouts | Lower confidence; needs validation |
| Fixed-width / vendor binary parsing | Handles legacy exports | Rare for investigative exports; complex |

**Recommended approach.** Model CDR and IPDR as **delimited/tabular inputs behind the same mapping-
registry + auto-detection mechanism used for bank statements** (FR-4), with operator-specific profiles
for Jio/Airtel/Vi/BSNL `[Assumption]`. Normalize phone numbers to E.164, IPs to canonical form, and
timestamps to a single timezone.

**Reasoning.** A single normalization pipeline for all three sources reduces code and enforces one
canonical model (TR-2). **Open gap:** exact operator formats are unknown (M1/Q1) — the mapping layer
isolates this risk so only a profile changes when real specs arrive.

**Industry practice.** Law-enforcement analytics tools (e.g., CDR analysis suites used by Indian LEAs)
ingest operator CSV/Excel exports via configurable column-mapping templates; IPDR analysis hinges on
correctly pairing public IP + port + timestamp to resolve carrier-grade NAT (CGNAT) ambiguity.

**References.** TRAI/DoT IPDR guidelines (general concept); RFC 6302 (logging of internet-facing
servers — IP+port+timestamp identity). *Exact operator schemas: to be supplied (Q1).*

---

## Topic 3 — Canonical Data Model & Entity Resolution

**What it is.** A single internal schema all sources map into, plus resolving which records belong to
the same real-world **entity** (phone number / bank account / IP), linking them via shared identifiers
(UPI ID, IP, IMEI, beneficiary). *(Serves FR-6, FR-10, TR-2.)*

**Why it is needed.** Fusion is impossible without one model and reliable entity linkage — this is the
heart of the PS ("normalize onto a unified entity model").

**Available approaches.**

| Approach | Pros | Cons |
|----------|------|------|
| Deterministic linkage (exact match on IDs) | Precise, explainable, auditable | Misses fuzzy/typo variants |
| Probabilistic/fuzzy linkage (name/address similarity) | Catches variants | False links; harder to defend forensically |
| Graph-based identity resolution (connected components over shared IDs) | Natural for "link accounts & numbers via shared IDs"; scalable | Needs a graph structure |

**Recommended approach.** **Deterministic, graph-based entity resolution**: build a graph where nodes
are identifiers and edges are co-occurrences (same IMEI ↔ number, same UPI ↔ account, same IP ↔
session), then treat connected components as one entity. Keep linkage rules explicit and logged for
evidentiary defensibility (NFR-7). Offer fuzzy matching only as an *optional*, clearly-flagged
assist — never as an unreviewed auto-merge.

**Reasoning.** The PS explicitly frames linkage as "via shared identifiers," which is inherently
deterministic and graph-shaped; explainability is essential in a forensic context. Fuzzy matching's
false positives would hurt NFR-2/NFR-3 and evidentiary trust.

**Industry practice.** Financial-crime / AML entity-resolution and KYC systems favor deterministic
rules with human-reviewed probabilistic candidates; connected-component identity graphs are standard
in fraud-ring detection.

**References.** Fellegi–Sunter record linkage theory; NetworkX connected components docs.

---

## Topic 4 — Temporal Correlation on a Unified Timeline

**What it is.** Placing all events on one time axis and detecting temporal coincidences — e.g., a
**call + IP session + money transfer within a window W**. *(Serves FR-7, FR-8, FR-9, NFR-2.)*

**Why it is needed.** The PS calls the intersection-in-time the "decisive evidence"; this is a core
differentiator and an evaluation criterion.

**Available approaches.**

| Approach | Pros | Cons |
|----------|------|------|
| Windowed join in pandas (sort + `merge_asof` / interval overlap) | Simple, in-memory, fast for moderate data | Memory-bound at very large scale |
| Interval-tree / sweep-line algorithm | Efficient overlap queries | More implementation effort |
| SQL window/range joins (Postgres) | Scales with DB; indexable on time | Join tuning needed |
| Elasticsearch time-range queries | Fast filtered retrieval, good for search/UI | Not ideal for multi-stream coincidence logic |

**Recommended approach.** Compute correlations with a **sort-and-window algorithm** (pandas
`merge_asof` / interval overlap) for the prototype, with a **configurable window W** (NFR-6), backed
by **PostgreSQL range queries** when data exceeds memory. Persist correlation hits with references to
source records (provenance, NFR-7).

**Reasoning.** `merge_asof` directly expresses "nearest event within tolerance" and is the pragmatic
fit for hackathon-scale data; pushing to Postgres range queries is the clean scaling path (NFR-5)
without changing the logical model. Window W must be tunable because the right value is unknown (M4/Q4).

**Industry practice.** SIEM/fraud correlation engines use time-windowed event joins ("events within N
seconds"); this is the canonical pattern for cross-stream coincidence detection.

**References.** pandas `merge_asof` docs; PostgreSQL range types & GiST indexes.

---

## Topic 5 — Graph / Network Analysis (Money-Flow & Communication)

**What it is.** Representing entities and their money transfers / communications as a graph to trace
networks, find communities, and rank importance. *(Serves FR-10, FR-11, FR-14, FR-18.)*

**Why it is needed.** Money-flow and communication *networks* are explicit outputs; patterns like
circular flows and layering are graph phenomena.

**Available approaches.**

| Approach | Pros | Cons |
|----------|------|------|
| **NetworkX** (in-memory graph in Python) | Rich algorithms, zero infra, fits Python stack | Memory-bound; not a persistent DB |
| **Neo4j** (graph database) | Persistent, Cypher queries, scales, great for drill-down | Extra service to run/learn |
| igraph / graph-tool | Very fast on large graphs | C deps; smaller ecosystem |

**Recommended approach.** Use **NetworkX for analytics** (cycle detection for circular flows,
connected components for entity resolution, centrality for key-actor ranking, community detection for
rings). Recommend **Neo4j as an *optional* upgrade** for persistence and interactive drill-down at
scale (FR-14, NFR-5). Both are PS-suggested.

**Reasoning.** NetworkX keeps the prototype dependency-light and in one language while covering every
required algorithm; Neo4j is the right answer if datasets outgrow memory or the demo needs live graph
querying — hence *optional*, decided by scale (M7/Q7).

**Industry practice.** AML "follow-the-money" and fraud-ring tools are graph-native; circular-flow and
layering detection are textbook cycle/path analyses; centrality identifies mule hubs.

**References.** NetworkX docs (cycles, centrality, community); Neo4j graph data science library.

---

## Topic 6 — Anomaly & Pattern Detection (Rules + ML)

**What it is.** Detecting suspicious behavior — layering, rapid in-and-out transfers, structuring
(smurfing), circular flows, mule signatures — and scoring entity risk. *(Serves FR-11, FR-12, FR-13,
NFR-3.)*

**Why it is needed.** Explicit functional requirement; relevance of detections is an evaluation
criterion.

**Available approaches.**

| Approach | Examples | Pros | Cons |
|----------|----------|------|------|
| **Rule-based** | thresholds: amount just below reporting limit (structuring), in-out within T minutes, cycle in graph | Explainable, no training data, defensible | Rigid; misses novel patterns; needs tuning |
| **Unsupervised ML** | Isolation Forest, Local Outlier Factor, autoencoders | Finds unknown anomalies without labels | Less explainable; false positives |
| **Supervised ML** | Gradient boosting / classifiers on labeled fraud | High precision if labeled data exists | Needs labeled data (unavailable — M3) |
| **Graph ML** | GNNs, node2vec + classifier | Captures network structure | Heavy; data-hungry |

**Recommended approach.** A **hybrid, rules-first design**: implement the named patterns as explicit,
configurable rules (they map directly to the PS list and are forensically explainable), and layer
**unsupervised ML (Isolation Forest / LOF)** on engineered entity features to surface anomalies the
rules miss (FR-11). Produce **risk scores by combining rule hits + ML anomaly score** with a
transparent breakdown (FR-12). Defer supervised/graph ML as *optional* pending labeled data (M3/Q3).

**Reasoning.** Rules give immediate, defensible coverage of exactly the patterns the PS names and need
no labeled data; unsupervised ML adds recall without labels. Explainable scoring supports the
evidentiary requirement (NFR-7) and the relevance criterion (NFR-3). scikit-learn covers Isolation
Forest/LOF (PS-suggested); PyTorch (also suggested) is reserved for optional deep models.

**Industry practice.** Production AML/transaction-monitoring blends deterministic typology rules
(FATF-defined structuring/layering) with ML anomaly scoring and analyst review; pure ML is rarely
deployed alone due to explainability/regulatory needs.

**References.** scikit-learn Isolation Forest / LocalOutlierFactor; FATF money-laundering typologies
(structuring, layering); RBI/FIU-IND STR guidance (for FR-17).

---

## Topic 7 — Search & Indexing

**What it is.** Fast filter/search across normalized records by entity, amount, time window, location.
*(Serves FR-15, TR-7, NFR-5.)*

**Available approaches.** PostgreSQL indexes (B-tree/GiST) for structured filters; **Elasticsearch**
for flexible full-text + faceted search; in-memory pandas filtering for small data.

**Recommended approach.** Use **PostgreSQL as the primary store with proper indexes** for
structured filters, and add **Elasticsearch (PS-suggested) as an *optional* layer** for fast
faceted/text search and to back the UI's filter/search when datasets are large (NFR-5).

**Reasoning.** Postgres alone satisfies FR-15 for prototype scale and keeps operations simple; ES
earns its keep only at larger scale or for rich search UX — so it is optional, scale-driven (M7/Q7).

**References.** PostgreSQL indexing docs; Elasticsearch query DSL.

---

## Topic 8 — Visualization (Timeline & Network)

**What it is.** Interactive timeline and network-graph visualizations with drill-down and filtering.
*(Serves FR-14, FR-15, NFR-4.)*

**Available approaches.**

| Approach | Pros | Cons |
|----------|------|------|
| **React + D3.js** (PS-suggested) | Full control, custom forensic UX, drill-down | More dev effort |
| Cytoscape.js / vis.js / sigma.js | Purpose-built graph rendering, less code | Less bespoke styling |
| Python dashboards (Plotly Dash / Streamlit) | Fast to build, no separate frontend | Less polished, weaker large-graph interactivity |

**Recommended approach.** **React + D3.js** for the fusion dashboard (timeline + network) as the
primary UI, optionally using **Cytoscape.js/sigma.js** for the network view to save effort on graph
layout while keeping D3 for the timeline. For a rapid internal demo, **Streamlit/Dash** is an
acceptable *optional* fast path.

**Reasoning.** React + D3 matches the PS suggestion and gives the clarity/drill-down the evaluation
demands (NFR-4); a dedicated graph library reduces risk on the hardest rendering piece. The Python-
dashboard route is a pragmatic fallback if frontend time is short.

**References.** D3.js docs; Cytoscape.js docs; Recharts/visx for React charting.

---

## Topic 9 — Forensic Report Generation & STR

**What it is.** Exporting an investigation-ready report (PDF/Word) with charts + evidentiary timeline,
and (bonus) auto-generating a Suspicious Transaction Report. *(Serves FR-16, FR-17.)*

**Available approaches.** PDF: **ReportLab**, **WeasyPrint** (HTML→PDF). Word: **python-docx**.
Charts embedded as rendered images (matplotlib) or captured from the UI.

**Recommended approach.** Generate reports server-side with **WeasyPrint (HTML→PDF)** for rich,
templated layouts and **python-docx** for Word, embedding charts rendered from the same data as the
dashboard. Every report item carries **provenance** (source file/row) for defensibility (NFR-7). STR
(FR-17) is an *optional* template populated from flagged transactions.

**Reasoning.** HTML templating gives the most control over a professional forensic layout and reuses
the web stack; python-docx satisfies the explicit Word requirement. Provenance is non-negotiable in
forensic output.

**References.** WeasyPrint docs; python-docx docs; ReportLab; FIU-IND STR format (for FR-17).

---

## Topic 10 — Natural-Language Query (Optional, FR-19)

**What it is.** Translating questions like *"show every transfer within 10 minutes of a call to X"*
into structured queries.

**Available approaches.** Template/grammar-based intent parsing; LLM-to-query (LLM emits a structured
filter/DSL that the backend executes).

**Recommended approach (optional).** An **LLM that emits a validated structured query** (not raw SQL)
against the canonical model, executed by the existing correlation/filter engine — safer and more
maintainable than free-form SQL generation. Only pursue after Must requirements are complete.

**Reasoning.** Constraining the LLM to a structured DSL preserves determinism, safety, and provenance
while delivering the NL UX; it reuses FR-9/FR-15 machinery. When building this, use the latest Claude
models (e.g., Claude Opus 4.8 / Sonnet 5) for the NL→DSL step.

**References.** Anthropic tool-use / structured-output docs; text-to-query design patterns.

---

## 4. Consolidated Technology Recommendation (feeds Doc 07)

| Concern | Recommended (core) | Optional / scale upgrade | Reason |
|---------|--------------------|--------------------------|--------|
| Language | Python | — | Unifies parsing, ML, correlation (PS-suggested) |
| Excel/CSV | pandas + openpyxl | — | Mature, PS-suggested |
| PDF | pdfplumber | Camelot; OCR (Tesseract) for scans | Coordinate-aware; avoids JVM |
| Data model / ETL | pandas + explicit mapping registry | — | Auditable auto-detection (FR-4) |
| Correlation | pandas `merge_asof` / interval logic | PostgreSQL range joins | Directly expresses windowed coincidence |
| Graph | NetworkX | Neo4j | All required algorithms; DB at scale |
| Anomaly ML | scikit-learn (Isolation Forest/LOF) + rules | PyTorch / GNN | Explainable + label-free |
| Storage | PostgreSQL | MongoDB (semi-structured), Elasticsearch (search) | Relational fits entities+provenance |
| Search | Postgres indexes | Elasticsearch | Simple first, scale later |
| Frontend | React + D3.js | Cytoscape.js/sigma.js; Streamlit (demo) | PS-suggested; drill-down clarity |
| Reporting | WeasyPrint (PDF) + python-docx (Word) | ReportLab | Templated forensic layout + Word |
| NL query (opt) | LLM→structured DSL (latest Claude) | — | Safe, deterministic NL UX |

## 5. Assumptions

- `[Assumption]` CDR/IPDR are structured/delimited files parseable by the same registry mechanism (M1).
- `[Assumption]` Prototype-scale data fits the pandas/NetworkX in-memory path; DB/graph-DB upgrades are
  scale-triggered (M7).
- `[Assumption]` Scanned-PDF OCR is out of mandatory scope.

## 6. Dependencies

- Sample datasets and format specs (Q1–Q3) needed to validate parsing and ML choices.
- Anomaly definitions/thresholds (Q4–Q5) needed to finalize rule design.

## 7. Risks

- ML relevance (NFR-3) unverifiable without labeled/sample data — mitigated by rules-first design.
- PDF-parsing robustness varies with real layouts — mitigated by mapping registry + optional OCR.
- Graph/search in-memory limits at scale — mitigated by planned Neo4j/ES/Postgres upgrades.

## 8. Best Practices

- Prefer **explainable/deterministic** methods for anything that becomes evidence.
- Keep every heavy dependency (Neo4j, ES, OCR, deep ML) **optional and scale-triggered**.
- Reuse one normalization pipeline and one canonical model across all sources.

## 9. Future Considerations

- Graph ML (GNNs) for ring detection; supervised models once labeled data exists.
- Streaming ingestion; additional dataset types; multi-language OCR.

## 10. References

- Cross-refs: `02_requirement_analysis.md`, `06_data_understanding.md`, `07_architecture_planning.md`.
- Library docs: pdfplumber, pandas, openpyxl, NetworkX, Neo4j GDS, scikit-learn, WeasyPrint,
  python-docx, D3.js, Cytoscape.js, PostgreSQL, Elasticsearch.
- Domain: FATF ML typologies; RFC 6302; FIU-IND STR guidance.
