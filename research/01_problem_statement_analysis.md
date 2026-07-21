# 01 — Problem Statement Analysis

**Project:** AI-Powered Financial & Telecom Dataset Analyzer (Bank, CDR & IPDR Fusion)
**Problem Statement ID:** ERH26_PS_03 · **Domain:** Big Data and Analytics
**Document status:** Batch A · Draft 1 · 2026-07-06

---

## 1. Purpose

To decompose the official problem statement ERH26_PS_03 into an unambiguous, structured understanding
of what must be built, what data flows in and out, what constrains the solution, and what information
is still missing — before any requirements or design work begins.

## 2. Objective

Produce a single source of truth for *"what problem are we solving and why"*, so that every downstream
document (requirements, architecture, implementation plan) traces back to a verified reading of the
official statement rather than to assumptions.

## 3. Scope

**In scope:** Interpretation of the problem statement text — background, problem, key objectives,
functional requirements, evaluation criteria, suggested tools, bonus points, and deliverables.

**Out of scope:** Solution design, technology selection, and effort estimation (covered in Docs 03,
07, 08). Nothing here adds capabilities beyond the official statement.

---

## 4. Problem Breakdown

The problem statement describes a **forensic data-fusion tool** for financial-cybercrime
investigators. The core difficulty it names is that the decisive evidence lives at the *intersection*
of three high-volume, heterogeneous datasets, and correlating them by hand across thousands of rows is
an overwhelming data-science task for a standard investigator.

The three input datasets:

| Dataset | What it is | Origin |
|---------|-----------|--------|
| **Bank statements** | Financial transactions (money movement) | Banks; Excel / PDF / CSV, layouts vary by bank |
| **CDR** — Call Detail Records | Telephony metadata: who called whom, when, how long | Indian telecom operators; exported files |
| **IPDR** — Internet Protocol Detail Records | Internet-session metadata: which subscriber used which IP, when | Indian telecom operators; exported files |

The tool must **ingest all three, normalize them onto a common timeline and entity model, and
automatically surface correlations, anomalies, and money-flow networks** — turning a manual
cross-referencing chore into an automated, investigation-ready output.

The problem statement decomposes into five capability pillars (derived directly from *Key Objectives*
and *Functional Requirements*):

1. **Multi-format ingestion & parsing** — heterogeneous bank layouts (Excel/PDF/CSV) + CDR + IPDR
   from major Indian telecom operators, with schema mapping/auto-detection to a canonical model.
2. **Cross-dataset fusion** — unified entity model (number/account/IP) and unified timeline; detect
   temporal coincidences (e.g., *call + IP + transfer within a window*); link accounts and numbers
   via shared identifiers (UPI ID, IP, IMEI, beneficiary).
3. **Anomaly & pattern detection** — rules + ML for layering, rapid in-and-out transfers, structuring,
   circular flows; risk scoring for accounts/numbers; mule-account behavioral signatures.
4. **Visualization & reporting** — money-flow and communication network graphs with drill-down;
   filter/search by entity, amount, time window, or location; exportable forensic report (PDF/Word)
   with charts and the evidentiary timeline.
5. **(Bonus)** — automated Suspicious Transaction Report (STR) generation; cross-bank/cross-operator
   network visualization with risk heat maps; natural-language query.

## 5. Understanding of Objectives (from *Key Objectives*)

| # | Objective (verbatim intent) | Interpretation |
|---|-----------------------------|----------------|
| O1 | Ingest and parse bank statements (Excel/PDF/CSV), CDR, and IPDR from multiple provider formats | Robust, format-tolerant parsers with auto-detection |
| O2 | Normalize records onto a unified entity (number/account/IP) and time model | A canonical schema + entity resolution + timezone-normalized timestamps |
| O3 | Automatically correlate events across the three datasets on a common timeline | Temporal join / windowed correlation engine |
| O4 | Detect suspicious patterns and visualize money-and-communication networks | Rules + ML detectors feeding graph visualizations |
| O5 | Produce an investigation-ready report | Exportable forensic report with charts + evidentiary timeline |

## 6. Inputs

| Input | Format(s) | Notes |
|-------|-----------|-------|
| Bank statements | Excel (.xlsx/.xls), PDF, CSV | Heterogeneous layouts across banks |
| CDR files | Operator exports (format unspecified — `[Assumption]` CSV/Excel/text) | From major Indian telecom operators |
| IPDR files | Operator exports (format unspecified — `[Assumption]` CSV/Excel/text) | From major Indian telecom operators |
| User query parameters | UI inputs | Entity, amount, time window, location filters; (bonus) natural-language query |

## 7. Outputs

| Output | Description |
|--------|-------------|
| Unified timeline | Calls, IP sessions, and transactions per entity on one time axis |
| Correlation results | Temporal coincidences (call + IP + transfer within a window) |
| Entity linkage graph | Accounts/numbers linked via UPI ID, IP, IMEI, beneficiary |
| Anomaly / pattern findings | Layering, rapid in-and-out, structuring, circular flows |
| Risk scores | Per account / per number |
| Network visualizations | Money-flow + communication graphs with drill-down; (bonus) risk heat maps |
| Forensic report | Exportable PDF/Word with charts + evidentiary timeline |
| (Bonus) STR | Automated Suspicious Transaction Report |

## 8. Constraints

- **Fidelity to source formats:** Parsers must handle heterogeneous, real-world bank/telecom exports
  (varied layouts, headers, encodings) — accuracy and robustness are explicit evaluation criteria.
- **Performance & scalability:** Must perform on *large* datasets ("thousands of rows" and beyond) —
  an explicit evaluation criterion.
- **Correlation quality:** Cross-dataset correlation on the unified timeline is judged on quality,
  and anomalies on true-vs-false-positive relevance.
- **Evidentiary usability:** Output must be *investigation-ready* — clarity of visualizations and a
  defensible evidentiary timeline matter (forensic context).
- **Technology guidance (non-binding):** PS suggests Python/Pandas, NetworkX/Neo4j, scikit-learn/
  PyTorch, pdfplumber/Apache PDFBox, OpenPyXL, Elasticsearch, PostgreSQL/MongoDB, React.js + D3.js.

## 9. Expected Deliverables (verbatim from PS)

- Working prototype/demo ingesting all three dataset types.
- Fusion dashboard with a worked correlation example.
- Sample forensic report and visual exports.
- Documentation (parsers, correlation logic, scoring rules).

## 10. Evaluation Criteria (verbatim from PS)

- Accuracy and robustness of multi-format parsing.
- Quality of cross-dataset correlation on the unified timeline.
- Relevance of detected anomalies (true vs. false positives).
- Clarity of network and timeline visualizations.
- Performance and scalability on large datasets.

## 11. Assumptions

All assumptions below are provisional and logged in `11_question_log.md` for confirmation.

- `[Assumption]` CDR and IPDR are supplied as structured files (CSV/Excel/delimited text); the PS does
  not name their exact format.
- `[Assumption]` Timestamps across datasets are in Indian Standard Time (IST) or carry a resolvable
  timezone; normalization is required regardless.
- `[Assumption]` "Major Indian telecom operators" implies Jio, Airtel, Vi (Vodafone Idea), and BSNL
  export formats as the target set.
- `[Assumption]` The tool is used by authorized investigators on lawfully obtained data (an
  authorization/consent context is assumed, not a public/mass-surveillance tool).
- `[Assumption]` "Location" in filters refers to cell-tower / LBS location fields present in CDR, or
  IP-geolocation for IPDR — the PS does not define the location source.
- `[Assumption]` Deployment target is a single-tenant investigative workstation or secure server; no
  multi-tenant SaaS requirement is stated.

## 12. Dependencies

- Availability of representative **sample datasets** for all three types (currently none provided).
- Format specifications / documentation for CDR & IPDR exports from the target operators.
- Definitions of "provider formats" for bank statements (which banks to support first).
- Clarity on report template requirements (any mandated STR/forensic format).

## 13. Missing Information

| # | Gap | Impact |
|---|-----|--------|
| M1 | Exact CDR / IPDR file formats & field lists | Blocks parser design (Docs 06, 07) |
| M2 | Which banks / statement layouts to support first | Affects ingestion scope & effort |
| M3 | Sample datasets (volume, realism) | Blocks validation, ML training, performance testing |
| M4 | Correlation "window" definition (default minutes for call+IP+transfer) | Affects correlation engine defaults |
| M5 | Anomaly thresholds & what counts as "suspicious" per pattern | Affects detector tuning & false-positive rate |
| M6 | Mandated STR / forensic report template (if any) | Affects reporting module |
| M7 | Scale targets (rows/day, total dataset size, concurrent users) | Affects architecture & DB choice |
| M8 | Location data source (cell tower vs IP geolocation) | Affects filter/search feature |
| M9 | Data residency / retention / audit requirements | Affects security & storage design |

## 14. Questions for Clarification

These are mirrored in `11_question_log.md` (Q1–Q9):

1. What are the exact CDR and IPDR export formats and field layouts for the target operators?
2. Which banks' statement formats must be supported at minimum for the demo?
3. Can representative sample datasets be provided, and at what scale (rows/size)?
4. What is the default correlation time window for "call + IP + transfer"?
5. What thresholds/definitions define each suspicious pattern (structuring, rapid in-and-out, etc.)?
6. Is there a mandated STR or forensic-report template to conform to?
7. What are the target scale and performance numbers ("large datasets" = ?)?
8. What is the authoritative source of "location" for filtering?
9. Are there data residency, retention, audit-trail, or chain-of-custody requirements?

## 15. Risks (problem-level)

- **Ambiguous input formats** → parser rework if assumed formats are wrong (see M1).
- **No sample data** → ML detectors and performance claims cannot be validated (see M3).
- **Vague "suspicious" definitions** → high false-positive rate hurting the *relevance* evaluation.
- **Scope creep from bonus items** → risk of under-delivering the core pillars.

## 16. Best Practices

- Lock the **canonical data model** early; treat every parser as a mapping *into* it.
- Keep correlation windows and anomaly thresholds **configurable**, not hard-coded.
- Preserve **provenance** (source file, row, offset) on every normalized record for evidentiary trust.
- Build with a **small, realistic synthetic dataset** first to unblock development while awaiting real
  data.

## 17. Future Considerations

- Additional dataset types (crypto-exchange logs, KYC records, device/app logs) — *optional*.
- Multi-language OCR for scanned PDF statements — *optional*.
- Real-time / streaming ingestion — *optional* (PS implies batch).

## 18. References

- Official Problem Statement **ERH26_PS_03** (PS owner `.docx`).
- Cross-refs: `02_requirement_analysis.md`, `06_data_understanding.md`, `11_question_log.md`.
