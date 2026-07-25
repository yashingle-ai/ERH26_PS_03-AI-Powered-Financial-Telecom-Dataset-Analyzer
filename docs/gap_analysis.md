# Gap & Edge-Case Analysis vs Problem Statement (ERH26_PS_03)

Assessed against the real case data (FIR 65-2024, FIR-0006-2025 U) and the PS requirements.
Severity: 🔴 correctness/evidentiary · 🟠 functional gap · 🟡 robustness/quality · 🔵 bonus/nice-to-have.

> **STATUS (v1.4.0):** All identified items remediated — A1–A5, B1–B5, C2–C5, D1/D3, E1/E2/
> E4/E5, F1–F3, G1/G2 are DONE (see `docs/changelog.md`).
> Remaining by design (not blockers): D4 (advanced velocity/GNN features), true streaming for
> 10M+ rows (a DB/Spark path — current cap+chunk is the safety valve), and OCR for scanned
> PDFs. These are scale/depth enhancements beyond the PS.

---

## A. Data correctness & integrity (highest priority — a forensic tool must be exact)

| # | Issue | Sev | Evidence | Impact | Fix |
|---|-------|-----|----------|--------|-----|
| A1 | **Timezone mislabelling** — crypto `Time(UTC)` and any UTC source is stamped IST (+5:30) | 🔴 | `parse_dt("2025-01-08 12:32:30") → +05:30`; crypto CSV header says UTC | 5.5-hour skew corrupts the unified timeline & every coincidence involving crypto | Per-source TZ in profile (`source_tz: UTC/IST`); convert to a canonical TZ |
| A2 | **Duplicate ingestion / double counting** — same subscriber present as raw `.csv` AND `- Reports.xlsx` | 🔴 | `9537658408.csv` (18,227 rows) + `9537658408 - Reports.xlsx` (16,557 rows) both ingested; ≥2 dup pairs confirmed | Inflates call counts, risk scores, graph edges; skews detection | Dedup events on natural key (A+B+start+dur) after normalization |
| A3 | **Mixed currency/asset in one money-flow & risk model** — INR bank ₹ and crypto token amounts summed together | 🔴 | crypto `amount` (USDT) and bank `amount` (INR) both feed `transfers`, `total_in/out`, structuring threshold (₹10L) | Structuring/mule thresholds meaningless on crypto; money-flow totals nonsensical across assets | Carry `asset/currency` on Event; segregate graphs & thresholds per asset; no cross-asset sums |
| A4 | **No FX / value normalization** for crypto tokens | 🟠 | token amounts are raw units | Can't rank crypto flows by real value | Optional price lookup; at minimum group by token |
| A5 | **Balance / running-total validation not enforced** on bank statements | 🟡 | `Balance` parsed but never checked against Δ(debit/credit) | Tampered/misparsed statements pass silently (Doc 06 validation rule unimplemented) | Add opening±Σ = closing consistency check, flag breaks |

## B. Ingestion & parsing (FR-1..5, NFR-1)

| # | Issue | Sev | Evidence | Impact | Fix |
|---|-------|-----|----------|--------|-----|
| B1 | **Bank data in PDF/Word not parsed** (many statements, English + Gujarati) | 🟠 | dozens of `*.pdf`, `.docx`, `.doc` bank/CA reports skipped | Misses a large share of the financial evidence | PDF table extraction (pdfplumber/Camelot) + OCR for scans; `.docx` table reader |
| B2 | **Only first Excel sheet read** | 🟠 | `read_excel(sheet_name=0)` | Multi-sheet workbooks lose data | Iterate all sheets |
| B3 | **Massive reject volume unexplained to user** | 🟠 | 177,139 rejects (FIR-6) with only aggregate count | Analyst can't see what was dropped or why (NFR-1 robustness) | Per-file/per-reason reject report surfaced in UI + export |
| B4 | **Unmapped vendor formats** (other bank `.xls`, some CDR variants) fall through | 🟡 | conf 0.0 files (e.g. `3592…s.xls`) | Coverage gaps | Add profiles; ship a manual-mapping UI for low-confidence files |
| B5 | **No manual column-mapping UI** for low-confidence files | 🟠 | `needs_manual_mapping` flag set but no workflow (Doc 04 DP-3) | Analyst can't rescue a near-miss file | Build the mapping screen |
| B6 | **Header/preamble detection window fixed at 30 rows** | 🟡 | `max_preamble_rows` | Files with deeper preamble missed | Scan-until-found with a data-row heuristic |
| B7 | **Amount sign/CR-DR conventions** vary by bank (Dr/Cr columns, signed amounts, "C"/"D" flags) | 🟡 | generic profile handles debit/credit columns only | Some statements' direction misread | Per-profile direction rules |

## C. Cross-dataset fusion (FR-6..10, NFR-2)

| # | Issue | Sev | Evidence | Impact | Fix |
|---|-------|-----|----------|--------|-----|
| C1 | **Finance↔telecom bridge weak in-data** — correlation needs account-holder↔phone | 🔴 | `correlation_hits = 0` both cases; VPA overlap = 1 | FR-9 (the PS's "decisive evidence") rarely fires | Consume KYC/`entity_map.csv` (built); parse CAF; registered-mobile from statements/PDF |
| C2 | **IPDR without MSISDN can't fuse** | 🟠 | `ipdr/1365.xlsx` has IP+time only | IP sessions float free of subscribers | Derive MSISDN from filename/case context; require subscriber column |
| C3 | **No fuzzy / name-based linking** (with review) | 🟡 | deterministic only | Misses same-actor across name variants | Optional, review-flagged fuzzy match |
| C4 | **UPI VPA that is an account (not phone) not linked** | 🟡 | `11161241340@SBIN` ignored as bridge | Loses account↔account UPI links | Map UPI handle→account where resolvable |
| C5 | **Beneficiary-name counterparties are low quality** | 🟡 | positional `parts[-2]` heuristic | Wrong/again-merged counterparties | Structured payee extraction per bank narration grammar |

## D. Detection & risk (FR-11..13, NFR-3)

| # | Issue | Sev | Evidence | Impact | Fix |
|---|-------|-----|----------|--------|-----|
| D1 | **Precision unmeasured on real data; likely high false positives** | 🟠 | dense benign transfer graphs → many `circular_flow`/`layering` flags | Erodes NFR-3 relevance; analyst alert fatigue | Amount/time gates, min-amount for cycles, tune thresholds on labeled real data |
| D2 | **Thresholds are INR-centric, applied to crypto** | 🔴 | see A3 | Crypto detection invalid | Per-asset rule config |
| D3 | **"Dormant account activation", "suspicious comm bursts", "location anomaly", "multi-hop"** (PS-listed) not implemented | 🟠 | only 6 rules | Partial pattern coverage vs PS list | Add the missing typologies |
| D4 | **No cross-entity temporal features** (fan-in bursts, velocity) beyond basic | 🟡 | features are per-entity aggregates | Misses coordinated bursts | Add windowed velocity features |
| D5 | **IsolationForest disabled for <8 entities**, silent | 🟡 | `_ml_scores` early return | Small cases lose ML signal | Surface in UI; use rules-only note |

## E. Visualization & reporting (FR-14..16, NFR-4)

| # | Issue | Sev | Evidence | Impact | Fix |
|---|-------|-----|----------|--------|-----|
| E1 | **Search/filter has no `location`** (PS FR-15 explicitly requires it) | 🟠 | dashboard search = entity/amount/type/text only | Missing required filter dimension | Add cell-tower/location filter (CDR location captured but unused) |
| E2 | **Forensic report has no charts/graph images** (PS wants "charts and the evidentiary timeline") | 🟠 | report is text tables only | Deliverable partially unmet | Embed network + timeline images (matplotlib/plotly static) |
| E3 | **Anomaly flags lack per-record provenance in report** (only correlation hits cite source) | 🟡 | `_str_lines` cites reasons, not source rows | Weaker evidentiary chain (NFR-7) | Attach contributing event provenance to each flag |
| E4 | **Large-graph rendering** not virtualized (16k nodes) | 🟡 | `network_figure` caps to 200 by degree | Analyst can't explore full graph interactively | Server-side subgraph/expand-on-click |
| E5 | **Timeline for very active entity** (18k calls) unusable | 🟡 | plots all points | UI overwhelm | Aggregate/paginate/zoom |

## F. PS-listed features not yet built

| # | Feature (PS) | Sev | Status |
|---|--------------|-----|--------|
| F1 | Natural-language query (bonus) | 🔵 | Not implemented (design ready: LLM→structured DSL) |
| F2 | Automated STR in regulatory format (bonus) | 🔵 | Text draft only, not FIU-IND format |
| F3 | Cross-bank/operator risk **heat map** (bonus) | 🔵 | Not implemented |
| F4 | Investigation "replay" / case management | 🔵 | Not implemented |

## G. Non-functional / ops

| # | Issue | Sev | Note |
|---|-------|-----|------|
| G1 | Full in-memory pipeline | 🟡 | ~300k rows OK (<70s); won't hold 10M+ — needs DB-backed/streaming path |
| G2 | Per-window recompute (no incremental) | 🟡 | dashboard re-runs whole pipeline on window change (cached per window) |
| G3 | Detection on the *deduped* set (A2) | 🔴 | until A2 fixed, all downstream numbers are inflated |
| G4 | No case isolation / per-case RBAC | 🟡 | auth is global, not per-investigation |

---

## Priority order to close (recommended)
1. **A2 dedup** and **A1 timezone** and **A3 per-asset** — these corrupt correctness; everything downstream depends on them.
2. **E1 location filter**, **E2 report charts** — explicit PS requirements currently unmet.
3. **B1 PDF/DOCX bank parsing** and **B3 reject transparency** — recover evidence + trust.
4. **C1 bridge via KYC/CAF** — unlock FR-9 (already have the entity_map mechanism).
5. **D1 precision tuning** + **D3 missing typologies** — relevance (NFR-3).
6. Bonus: **F2 STR format**, **F3 heat map**, **F1 NL query**.
