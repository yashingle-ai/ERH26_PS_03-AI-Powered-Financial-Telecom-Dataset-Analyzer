# 11 — Question Log

**Project:** AI-Powered Financial & Telecom Dataset Analyzer (Bank, CDR & IPDR Fusion)
**Problem Statement ID:** ERH26_PS_03 · **Domain:** Big Data and Analytics
**Document status:** LIVE — finalized in Batch C · 2026-07-06

> **Direction from PS owner (2026-07-06):** proceed on the **best-feasible answer** for all open items
> and confirm that **CDR/IPDR are structured/delimited files**. Accordingly, high-impact questions are
> marked `ASSUMED` with the adopted default recorded in *Adopted default*; they remain open for the PS
> owner to override, and all defaults are configurable so a later answer applies without rework.

---

## 1. Purpose

Maintain a single, continuously-updated list of clarifications required from the problem-statement
owner, so that assumptions made during planning can be confirmed or corrected before implementation.

## 2. Objective

Convert every unmarked ambiguity in the PS into a tracked question with an owner, status, and the
downstream artifacts it blocks — protecting requirement traceability and preventing rework.

## 3. Scope

Questions arising from interpreting ERH26_PS_03 and from the planning documents (Docs 01–10). Each
question links to the assumption it would confirm/replace.

---

## 4. Status legend

`OPEN` = awaiting answer · `ASSUMED` = proceeding on a stated assumption until answered ·
`ANSWERED` = resolved (record the answer & date) · `CLOSED` = no longer relevant.

## 5. Question Log

| ID | Question | Blocks / Impacts | Adopted default (best-feasible) | Priority | Status |
|----|----------|------------------|--------------------------------|----------|--------|
| Q1 | What are the exact **CDR and IPDR export formats** and field layouts for the target operators (Jio/Airtel/Vi/BSNL)? | FR-2, FR-3, FR-4; parser & data model (Docs 06, 07) | **Confirmed structured/delimited files**; modeled schemas in Doc 06 §6–7 behind a mapping registry; per-operator profiles swapped when real specs arrive | High | ASSUMED |
| Q2 | Which **banks' statement layouts** must be supported at minimum for the demo? | FR-1, FR-4; ingestion scope | Generic auto-detect + 1–2 common layouts (e.g., HDFC/SBI-style) + manual-mapping fallback | High | ASSUMED |
| Q3 | Can **representative sample datasets** be provided, and at what scale (rows/size)? | NFR-1, NFR-3, NFR-5; ML training & perf testing | Build a **synthetic dataset generator** (Phase 0) covering all three types; swap in real data when provided | High | ASSUMED |
| Q4 | What is the **default correlation time window** for "call + IP + transfer"? | FR-9 defaults | Configurable; **default W = 10 min** (per PS bonus example) | Medium | ASSUMED |
| Q5 | What **thresholds/definitions** identify each suspicious pattern (structuring, rapid in-and-out, circular flow, mule)? | FR-11, FR-12, FR-13; NFR-3 | **FATF-style configurable defaults** in `config/scoring_rules.yaml` (Doc 06 §11, Doc 09); tuned with analyst feedback | High | ASSUMED |
| Q6 | Is there a **mandated STR / forensic-report template** to conform to? | FR-16, FR-17 | Generic forensic template; **FIU-IND STR format** as guide for optional STR | Medium | ASSUMED |
| Q7 | What are the **target scale and performance** numbers ("large datasets" = ?)? | NFR-5; DB/graph/search choices | Prototype-scale in-memory (pandas/NetworkX); **Postgres/Neo4j/Elasticsearch** as scale-triggered upgrades | Medium | ASSUMED |
| Q8 | What is the authoritative **source of "location"** for filtering (cell-tower/LBS vs IP-geolocation)? | FR-15 | **Cell-tower/CGI** for CDR, **IP-geolocation** for IPDR where present | Low | ASSUMED |
| Q9 | Are there **data residency, retention, audit-trail, or chain-of-custody** requirements? | NFR-7, NFR-8; security design (Doc 10) | Single-tenant secure workstation; **immutable provenance** retained on every record; security (auth/masking/audit) as optional NFR-8 | Medium | ASSUMED |

**All nine are `ASSUMED`, not `ANSWERED`** — the PS owner may override any at any time; defaults are
configurable so answers apply without rework. No additional blocking questions surfaced during Batch
B/C design.

## 6. Assumptions

- All working assumptions above are provisional; implementation defaults are chosen to be safely
  reversible (configurable) so answers can be applied without rework.

## 7. Dependencies

- Answers to Q1–Q3 are prerequisites for finalizing Docs 06 (data) and 07 (architecture) beyond the
  assumption-based drafts.

## 8. Risks

- Prolonged `OPEN` status on Q1/Q3/Q5 is the top project risk (see `10_risk_analysis.md`): parser and
  ML work proceed on assumptions and may need rework.

## 9. Best Practices

- Every assumption in any document must have a matching question here.
- Re-review this log at the start of each batch and before implementation kickoff.

## 10. Future Considerations

- Convert answered questions into recorded decisions (ADRs) at implementation time.

## 11. References

- `01_problem_statement_analysis.md` (§13–14), `02_requirement_analysis.md`, `03_initial_research.md`.
