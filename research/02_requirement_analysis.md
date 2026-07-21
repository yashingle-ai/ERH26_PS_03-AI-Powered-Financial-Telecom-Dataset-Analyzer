# 02 — Requirement Analysis Document

**Project:** AI-Powered Financial & Telecom Dataset Analyzer (Bank, CDR & IPDR Fusion)
**Problem Statement ID:** ERH26_PS_03 · **Domain:** Big Data and Analytics
**Document status:** Batch A · Draft 1 · 2026-07-06

---

## 1. Purpose

To translate the problem statement (see `01_problem_statement_analysis.md`) into a numbered,
traceable requirement set — functional, non-functional, business, and technical — with user roles,
stories, and acceptance criteria that downstream design and implementation documents can reference by
ID.

## 2. Objective

Establish the **stable requirement vocabulary** (`FR-*`, `NFR-*`, `BR-*`, `TR-*`) used across all
later documents, so that every design decision and implementation task is traceable to a specific,
approved requirement rooted in the official problem statement.

## 3. Scope

**In scope:** All requirements derivable from ERH26_PS_03's Key Objectives, Functional Requirements,
Evaluation Criteria, Bonus Points, and Deliverables.

**Out of scope:** Architecture and technology selection (Doc 07), phasing/estimation (Doc 08).
Requirements marked **(Optional)** are recommendations beyond the mandatory statement.

---

## 4. Traceability convention

Each requirement lists a **Source** tracing to the PS section: `KO` = Key Objectives, `FR` = Functional
Requirements, `EC` = Evaluation Criteria, `BP` = Bonus Points, `DL` = Deliverables.

---

## 5. Functional Requirements

### 5.1 Ingestion & Parsing

| ID | Requirement | Source | Priority |
|----|-------------|--------|----------|
| FR-1 | Parse heterogeneous **bank statements** in Excel, PDF, and CSV formats | FR-I.a, KO | Must |
| FR-2 | Parse **CDR** exports from major Indian telecom operators | FR-I.b, KO | Must |
| FR-3 | Parse **IPDR** exports from major Indian telecom operators | FR-I.b, KO | Must |
| FR-4 | Perform **schema mapping / auto-detection** of source layouts into the canonical internal model | FR-I.c | Must |
| FR-5 | Report parse errors/rejected rows with row-level diagnostics | EC (robustness) | Should |

### 5.2 Normalization & Cross-Dataset Fusion

| ID | Requirement | Source | Priority |
|----|-------------|--------|----------|
| FR-6 | Normalize all records onto a **unified entity model** (phone number / bank account / IP) | KO, FR-II | Must |
| FR-7 | Normalize all timestamps onto a **common timeline** (timezone-consistent) | KO, FR-II.a | Must |
| FR-8 | Build a **unified timeline** linking calls, IP sessions, and transactions **per entity** | FR-II.a | Must |
| FR-9 | Detect **temporal coincidences** (e.g., call + IP + transfer within a configurable window) | FR-II.b | Must |
| FR-10 | **Link accounts and numbers** via shared identifiers: UPI ID, IP, IMEI, beneficiary | FR-II.c | Must |

### 5.3 Anomaly & Pattern Detection

| ID | Requirement | Source | Priority |
|----|-------------|--------|----------|
| FR-11 | Detect patterns via **rules + ML**: layering, rapid in-and-out transfers, structuring, circular flows | FR-III.a | Must |
| FR-12 | Compute **risk scores** for accounts and numbers | FR-III.b | Must |
| FR-13 | Detect **mule-account behavioral signatures** | FR-III.c | Must |

### 5.4 Visualization & Reporting

| ID | Requirement | Source | Priority |
|----|-------------|--------|----------|
| FR-14 | Render **money-flow and communication network graphs** with drill-down | FR-IV.a | Must |
| FR-15 | **Filter/search** by entity, amount, time window, or location | FR-IV.b | Must |
| FR-16 | Export a **forensic report (PDF/Word)** with charts and the evidentiary timeline | FR-IV.c, DL | Must |

### 5.5 Bonus / Optional Functional Requirements

| ID | Requirement | Source | Priority |
|----|-------------|--------|----------|
| FR-17 (Optional) | Automated **Suspicious Transaction Report (STR)** generation | BP | Could |
| FR-18 (Optional) | **Cross-bank & cross-operator** network visualization with **risk heat maps** | BP | Could |
| FR-19 (Optional) | **Natural-language query** (e.g., "show every transfer within 10 minutes of a call to X") | BP | Could |

## 6. Non-Functional Requirements

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| NFR-1 | Accuracy | Multi-format parsing must be accurate and robust across varied real-world layouts | EC |
| NFR-2 | Correlation quality | Cross-dataset correlation on the unified timeline must be high-quality (few missed/false links) | EC |
| NFR-3 | Relevance | Detected anomalies must maximize true positives / minimize false positives | EC |
| NFR-4 | Usability | Network and timeline visualizations must be clear and investigator-friendly | EC |
| NFR-5 | Performance & scalability | System must perform on large datasets (thousands of rows and beyond) | EC |
| NFR-6 | Configurability | Correlation windows, thresholds, and scoring rules must be tunable, not hard-coded | Derived (best practice) |
| NFR-7 | Traceability / evidentiary integrity | Every normalized record must retain provenance (source file, row) for forensic defensibility | Derived (forensic context) |
| NFR-8 (Optional) | Security | Sensitive PII (accounts, numbers, IPs) handled with access control, encryption at rest, audit trail | Derived — see Q9 |
| NFR-9 | Maintainability | Parsers, correlation logic, and scoring rules documented (a required deliverable) | DL |
| NFR-10 (Optional) | Extensibility | New parsers/operators added without touching the correlation core | Derived |

## 7. Business Requirements

| ID | Requirement |
|----|-------------|
| BR-1 | Reduce investigator time from manual multi-day cross-referencing to automated correlation |
| BR-2 | Surface decisive evidence at the intersection of financial + telecom data |
| BR-3 | Produce investigation-ready, defensible output usable in a case file |
| BR-4 | Deliver a working prototype/demo ingesting all three dataset types (hackathon deliverable) |

## 8. Technical Requirements

| ID | Requirement |
|----|-------------|
| TR-1 | Support Excel/PDF/CSV parsing (bank) + delimited/structured parsing (CDR/IPDR) |
| TR-2 | Canonical internal data model with entity resolution across identifiers |
| TR-3 | Timeline/temporal-join engine supporting windowed correlation |
| TR-4 | Graph data structure/store for entity-linkage and money-flow networks |
| TR-5 | Rule engine + ML models for anomaly detection |
| TR-6 | Report generation to PDF/Word with embedded charts |
| TR-7 | Searchable index for filter/search by entity/amount/time/location |
| TR-8 (Optional) | NLP layer for natural-language query (FR-19) |

## 9. User Roles

| Role | Description |
|------|-------------|
| **Investigator / Analyst** | Primary user; uploads datasets, explores correlations, reviews anomalies, exports reports |
| **Senior Investigator / Reviewer** | Reviews findings, validates the evidentiary timeline, signs off on reports |
| **System Administrator** (Optional) | Manages deployment, access control, data retention |
| **Data Steward** (Optional) | Manages parser mappings for new bank/operator formats |

## 10. System Actors

- **Human actors:** Investigator, Reviewer, Administrator, Data Steward.
- **System actors:** Ingestion service, Parser/normalizer, Correlation engine, Anomaly detector,
  Graph/visualization service, Report generator, Search index.
- **External inputs:** Bank statement files, CDR files, IPDR files.

## 11. User Stories & Acceptance Criteria

> Format: *As a `<role>`, I want `<capability>` so that `<value>`.* Each maps to FR IDs.

| US | Story | Acceptance Criteria | Maps to |
|----|-------|---------------------|---------|
| US-1 | As an investigator, I want to upload bank/CDR/IPDR files in their native formats so that I don't have to reformat data manually | System accepts Excel/PDF/CSV bank files + CDR + IPDR; parses each; shows a per-file parse summary with row counts and errors | FR-1..5 |
| US-2 | As an investigator, I want records auto-mapped to one model so that fields align regardless of source layout | Auto-detection maps ≥ the mandatory canonical fields; unmapped fields are flagged for manual mapping | FR-4, FR-6 |
| US-3 | As an investigator, I want one timeline per entity so that I can see calls, sessions, and transfers together | Selecting an entity shows a chronological, timezone-normalized timeline of all three event types | FR-7, FR-8 |
| US-4 | As an investigator, I want the tool to flag when a call, IP session, and transfer coincide so that I can spot decisive moments | Given a window W, system lists all (call + IP + transfer) coincidences within W; W is configurable | FR-9, NFR-6 |
| US-5 | As an investigator, I want accounts and numbers linked by shared IDs so that I can see one actor across datasets | Entities sharing UPI ID / IP / IMEI / beneficiary are linked and shown as one node cluster | FR-10 |
| US-6 | As an investigator, I want suspicious patterns detected automatically so that I don't miss layering/structuring | System flags layering, rapid in-and-out, structuring, circular flows; each flag cites the underlying records | FR-11 |
| US-7 | As an investigator, I want risk scores per account/number so that I can prioritize | Each entity has a risk score with contributing factors listed | FR-12, FR-13 |
| US-8 | As an investigator, I want to explore money-flow and communication graphs so that I can trace networks | Graphs render with drill-down; clicking a node/edge reveals underlying records | FR-14 |
| US-9 | As an investigator, I want to filter by entity/amount/time/location so that I can focus | Filters narrow timeline, graph, and lists consistently | FR-15 |
| US-10 | As a reviewer, I want an exportable forensic report so that findings are case-ready | Export produces PDF/Word with charts + evidentiary timeline + provenance | FR-16, NFR-7 |
| US-11 (Optional) | As an investigator, I want an auto-generated STR so that regulatory reporting is faster | STR draft generated from flagged transactions | FR-17 |
| US-12 (Optional) | As an investigator, I want to ask questions in plain language so that I can query without filters | NL query returns correct results for the sample query set | FR-19 |

## 12. Success Criteria

Aligned to the PS evaluation criteria:

- **SC-1:** Prototype ingests all three dataset types end-to-end (DL, BR-4).
- **SC-2:** A worked correlation example is demonstrable on the fusion dashboard (DL).
- **SC-3:** Parsing is accurate/robust on the provided/sample formats (NFR-1).
- **SC-4:** Correlation on the unified timeline is demonstrably correct on the example (NFR-2).
- **SC-5:** Detected anomalies are relevant (measurable true-positive rate on labeled samples) (NFR-3).
- **SC-6:** Visualizations are clear and support drill-down (NFR-4).
- **SC-7:** Acceptable performance on the target large dataset (NFR-5).
- **SC-8:** Sample forensic report and documentation delivered (DL).

## 13. Risks (requirement-level)

- Requirements FR-11/12/13 depend on **anomaly definitions and labeled data** that are not yet
  provided (see M3, M5) — accuracy claims (NFR-3) are at risk until resolved.
- FR-1..4 robustness (NFR-1) depends on the **actual variety of layouts**, unknown until sample data
  arrives (M1, M2).
- Optional FRs (17–19) risk diverting effort from Must requirements.

## 14. Constraints

- Must follow the PS strictly; only FRs 1–16 and NFRs 1–7/9 are mandatory. FR-17..19, NFR-8/10, and
  optional roles are recommendations.
- Suggested tools are non-binding but influence technical requirements (see Doc 07).

## 15. Assumptions

- `[Assumption]` "Large datasets" is interpreted as needing efficient batch processing and indexed
  search; exact scale is pending (M7).
- `[Assumption]` Configurable windows/thresholds (NFR-6) are required to hit the relevance criterion
  (NFR-3), even though the PS does not state configurability explicitly.
- `[Assumption]` Security/audit (NFR-8) is treated as optional-but-recommended given the forensic PII
  context, pending Q9.

## 16. Dependencies

- Depends on `01_problem_statement_analysis.md` for scope.
- Feeds `04`–`08` (all reference these requirement IDs).
- Blocked on Question Log items Q1–Q9 for full precision of FR-9/11/12/13.

## 17. Best Practices

- Keep requirements **atomic and testable**; each has acceptance criteria.
- Maintain **bidirectional traceability**: PS → requirement → design → test.
- Separate **Must / Should / Could** to protect core scope during a time-boxed build.

## 18. Future Considerations

- Requirement extensions for additional datasets or real-time ingestion would enter as new FRs, not
  by mutating existing ones (protects traceability).

## 19. References

- `01_problem_statement_analysis.md`, `03_initial_research.md`, `11_question_log.md`.
- Official Problem Statement **ERH26_PS_03**.
