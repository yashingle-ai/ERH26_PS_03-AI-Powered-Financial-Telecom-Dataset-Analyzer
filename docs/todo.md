# TODO / Roadmap

Phases per `research/08_implementation_planning.md`. ✅ done · 🔄 in progress · ⏳ pending

## Phase 0 — Foundations ✅
- [x] Repo scaffold, deps, config, canonical schema
- [x] Synthetic data generator (Bank/CDR/IPDR + ground truth)
- [x] ADR-0001, canonical_schema.md, progress.md

## Phase 1 — Ingestion & Parsing ⏳
- [ ] Profile registry loader (`config/profiles/**`)
- [ ] Type + format + profile auto-detection (confidence threshold)
- [ ] Parsers: excel, csv, pdf (pdfplumber), delimited
- [ ] Reject log + per-file parse summary
- [ ] Staging persistence + tests on smoke dataset

## Phase 2 — Normalization & Entity Resolution ⏳
- [ ] Value normalizers: phone (E.164), IP, datetime (TZ), amount
- [ ] Narration mining (UPI/UTR/beneficiary/mode)
- [ ] Provenance stamping
- [ ] Identifier graph → connected-component entity resolution

## Phase 3 — Timeline & Correlation ⏳
- [ ] Per-entity unified timeline
- [ ] Windowed correlation (call + IP + transfer within W)
- [ ] Worked correlation example on demo dataset

## Phase 4 — Detection & Risk ⏳
- [ ] Rule detectors (structuring, rapid in/out, layering, circular, mule)
- [ ] Feature builder + Isolation Forest
- [ ] Composite risk scoring with factor breakdown
- [ ] Evaluate against ground_truth.json (precision/recall)

## Phase 5 — Graph ⏳
- [ ] Money-flow + communication graph build
- [ ] Cycles / centrality / communities; drill-down payloads

## Phase 6 — Dashboard (Streamlit first) ⏳
- [ ] Upload center, timeline view, network graph, filters/search, entity detail

## Phase 7 — Reporting ⏳
- [ ] Forensic report (PDF/Word) + charts + evidentiary timeline; optional STR

## Phase 8 — Hardening & Docs ⏳
- [ ] Performance on scale tier; robustness; complete docs/

## Phase 9 — Optional / Enterprise ⏳
- [ ] Auth/RBAC, audit, observability, Neo4j/ES, containerization, NL query, React+D3
