# 10 — Risk Analysis Document

**Project:** AI-Powered Financial & Telecom Dataset Analyzer (Bank, CDR & IPDR Fusion)
**Problem Statement ID:** ERH26_PS_03 · **Domain:** Big Data and Analytics
**Document status:** Batch C · Draft 1 · 2026-07-06

---

## 1. Purpose

To identify the risks that could derail delivery or quality — technical, project, data, security, and
performance — and define concrete mitigations, so the team manages them proactively rather than
reactively.

## 2. Objective

Give each risk an owner-actionable mitigation and a residual severity, and connect the top risks to
the open questions (Doc 11) that would retire them.

## 3. Scope

Risks arising from the requirements (Doc 02), data (Doc 06), architecture (Doc 07), and plan
(Doc 08). Excludes organizational/commercial risks outside the build.

---

## 4. Scoring scale

**Likelihood** × **Impact**, each Low/Medium/High → **Severity** (L/M/H/Critical).

## 5. Technical Risks

| ID | Risk | Likelihood | Impact | Severity | Mitigation | Ref |
|----|------|-----------|--------|----------|-----------|-----|
| TR-R1 | Heterogeneous bank PDF/Excel layouts break parsers | High | High | **Critical** | Profile registry + confidence-scored auto-detect + manual mapping fallback; timebox Phase 1; optional OCR for scans | FR-4, Q2 |
| TR-R2 | CDR/IPDR real formats differ from modeled schemas | High | High | **Critical** | Mapping layer isolates format; only a profile changes when specs arrive; validate early with samples | Q1, Doc 06 |
| TR-R3 | Entity resolution over/under-merges identities | Medium | High | High | Deterministic links only; fuzzy candidates flagged for review, never auto-merged | FR-10 |
| TR-R4 | Correlation window mis-tuned → missed/false coincidences | Medium | Medium | Medium | Configurable W (default 10 min); expose in UI; validate on worked example | FR-9, Q4 |
| TR-R5 | In-memory graph/correlation hits memory limits | Medium | High | High | Postgres range joins + Neo4j/ES optional upgrades; chunked processing | NFR-5, Q7 |
| TR-R6 | Frontend graph/timeline complexity overruns | Medium | Medium | Medium | Use Cytoscape.js/sigma.js for graph; Streamlit fallback for demo | NFR-4 |

## 6. Project Risks

| ID | Risk | Likelihood | Impact | Severity | Mitigation | Ref |
|----|------|-----------|--------|----------|-----------|-----|
| PR-R1 | Open questions (Q1/Q3/Q5) stay unanswered | High | High | **Critical** | Proceed on stated assumptions with configurable defaults + synthetic data; re-confirm at each batch | Doc 11 |
| PR-R2 | Scope creep from bonus features (FR-17..19) | Medium | High | High | Bonus is P2, feature-flagged, only after core (Doc 08 §7) | FR-17..19 |
| PR-R3 | Ingestion (Phase 1) underestimated | High | Medium | High | Start earliest; timebox; generic profile + manual mapping as safety net | Doc 08 |
| PR-R4 | Unknown team size/velocity → schedule risk | Medium | Medium | Medium | Relative-complexity plan; vertical-slice-first keeps a demoable build always | Doc 08 |

## 7. Data Risks

| ID | Risk | Likelihood | Impact | Severity | Mitigation | Ref |
|----|------|-----------|--------|----------|-----------|-----|
| DR-R1 | No real sample datasets available | High | High | **Critical** | Synthetic data generator (Phase 0) covers all three types; swap in real data when provided | Q3 |
| DR-R2 | Weak/absent finance↔telecom bridge in real data | Medium | High | High | Rely on time-coincidence + shared phone numbers; surface bridge coverage as a metric; log gap | Doc 06 §8 |
| DR-R3 | CGNAT ambiguity → wrong IP→subscriber attribution | Medium | High | High | Require public IP + port + exact timestamp; caveat attributions in report | RFC 6302 |
| DR-R4 | Data quality (dupes, TZ/format variance, dirty narration) | High | Medium | High | Validation rules + dedup + reject log + narration regex with review flags | Doc 06 §9–12 |
| DR-R5 | Missing/ambiguous anomaly definitions | High | Medium | High | FATF-style configurable defaults; tune with analyst feedback | Q5 |

## 8. Security Risks

| ID | Risk | Likelihood | Impact | Severity | Mitigation | Ref |
|----|------|-----------|--------|----------|-----------|-----|
| SR-R1 | Sensitive PII (accounts/numbers/IPs) exposure | Medium | High | High | PII masking in UI; encryption at rest; access control; audit log (NFR-8) | Q9 |
| SR-R2 | Chain-of-custody / evidentiary integrity gaps | Medium | High | High | Immutable provenance on every record; tamper-evident audit trail | NFR-7 |
| SR-R3 | Unauthorized/mis-scoped use of investigative data | Low | High | Medium | Assume authorized single-tenant use; document authorization requirement; access control | Doc 01 §11 |
| SR-R4 | LLM (optional NL query) leaks data or emits unsafe queries | Low | Medium | Medium | LLM emits validated structured DSL only (never raw SQL); no raw PII in prompts where avoidable | FR-19 |

## 9. Performance Risks

| ID | Risk | Likelihood | Impact | Severity | Mitigation | Ref |
|----|------|-----------|--------|----------|-----------|-----|
| PF-R1 | Slow parsing of large files | Medium | Medium | Medium | Chunked/streaming parse; progress reporting | NFR-5 |
| PF-R2 | Correlation cost grows with event count | Medium | High | High | Indexed range joins; bucket by entity/time; push to Postgres at scale | NFR-2, NFR-5 |
| PF-R3 | Graph algorithms slow on large graphs | Medium | Medium | Medium | Limit to relevant subgraphs; Neo4j GDS optional; cache layouts | FR-14 |
| PF-R4 | Dashboard rendering large graphs janky | Medium | Medium | Medium | Server-side aggregation; progressive/level-of-detail rendering; filters first | NFR-4 |

## 10. Top risks summary (Critical)

1. **TR-R1 / TR-R2** — parsing fragility & unknown formats → *mitigated by mapping registry isolating
   format changes and manual-mapping fallback.*
2. **PR-R1 / DR-R1** — unanswered questions & no sample data → *mitigated by synthetic data + configurable
   assumption-based defaults; re-confirm each batch.*

These four converge on the same root cause (data uncertainty) and the same mitigation strategy:
**isolate format/threshold decisions behind configuration, and unblock with synthetic data.**

## 11. Assumptions

- `[Assumption]` Assumption-based defaults (window W, thresholds, schemas) are acceptable until answers
  arrive (Doc 11).
- `[Assumption]` Single-tenant, authorized-use security posture (Q9).

## 12. Dependencies

- Mitigations depend on Phase 0 synthetic generator and the configurable architecture (Docs 07, 08).
- Retirement of top risks depends on answers to Q1/Q3/Q5 (Doc 11).

## 13. Best Practices

- Re-score risks at each phase gate; promote/demote as reality lands.
- Every assumption maps to a question (Doc 11) and a configurable default so answers apply without rework.
- Prefer explainable/deterministic methods to keep evidentiary and false-positive risk low.

## 14. Future Considerations

- Formal security review + pen test if productionized (beyond hackathon).
- Model-drift monitoring if supervised ML is added later.

## 15. References

- `01_problem_statement_analysis.md`, `02_requirement_analysis.md`, `06_data_understanding.md`,
  `07_architecture_planning.md`, `08_implementation_planning.md`, `11_question_log.md`.
- RFC 6302; FATF money-laundering typologies.
