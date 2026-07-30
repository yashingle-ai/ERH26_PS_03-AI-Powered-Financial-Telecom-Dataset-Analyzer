# Component status — what works, what was decided, what still needs work

**As of:** 30 Jul 2026, measured on `FIR 65-2024` and `FIR-0006-2025 U`.
**Reproduce:** `python -m scripts.measure_ingestion --input "<case>"`
**Legend:** 🟢 working and verified · 🔵 decided and deliberately closed · 🟡 needs work ·
🔴 blocked on something outside the code · ⚪ needs a decision from the project owner

---

## 1. Ingestion — readers

| Component | Status | Evidence |
|---|---|---|
| `detector.py` — format by magic bytes | 🟢 | Extensions lie constantly in case material; bytes decide. Catches `.xls` that is xlsx, `.xlsx` that is an AppleDouble stub, `.xls` that is a text report |
| `parsers/excel.py` | 🟢 | Reads every sheet, keeps the best-matching one. Reading only sheet 1 lost data |
| `parsers/tabular.py` (CSV/TXT) | 🟢 | Preamble skip, duplicate-label de-collision |
| `parsers/pdf.py` | 🟢 | pdfplumber; **text-layer decision** replaces the blunt size cap |
| `parsers/docx_tables.py` | 🟢 | All tables, not just the first — a single grid dropped 47% of rows |
| `parsers/fixed_width.py` | 🟢 **new** | Printed statements with no delimiter. Two layouts: HDFC-style headerless, and Bank of Baroda ledger reports. **0 → 743 events** across both cases (73 + 670) |
| `parsers/html_tables.py` | 🟢 **new** | Google legal-process exports. **IP_SESSION 69 → 4,133** |
| `parsers/archive.py` | 🟢 | 3-level recursion, 512 MB budget, path-escape refusal; **every loss now reported** |
| `structure.py` — geometry recovery | 🟢 **new** | Broken PDF grids. Complaint folder 14 → 389 events |
| `value_typer.py` — value-based typing | 🔵 | Works, but **+23 events measured**. Kept as the only way to map a headerless statement or recovered region. **Decision: stop investing** |

## 2. Ingestion — coverage decisions

| Item | Status | Decision and evidence |
|---|---|---|
| `.doc` (40 files) | 🔵 | All 40 verified genuine OLE2 by magic bytes — none mislabelled, so no cheap win. Contents are narrative police paperwork (case diaries, I4C mail, press notes, look-out notices, remand reports). **No financial tables.** Low value |
| `.xml` (19 files) | 🔵 | Response manifests naming a PDF, not data. Correctly skipped |
| Images / media (~2,100) | 🔵 | Recorded, not silently dropped. Mostly WhatsApp chat media inside archives |
| Scanned KYC/AOF (~258 + 14 PDFs) | 🔵 | **OCR closed** — see §6 |
| Reference / roster tables (~4,000 rows) | 🔵 | Correctly refused: no timestamps, no transactions. The paths that would "recover" them fabricate identity links |
| `.vcf` (57 cards) | 🔵 | 45 name↔phone pairs, but **name is not a merge key** → zero FR-9 impact. Attribution value only. Deferred |

## 3. Normalization

| Component | Status | Evidence |
|---|---|---|
| `field_mapper.py` | 🟢 | Non-empty beats empty, first-declared alias wins. Fixed `pstd_dt` overwriting `Tran_Date` |
| `normalizers` — timestamps | 🟢 | IST canonical; SAS `11DEC2019:09:07:02`, NCRP `HR:/MIN:/AM-PM`, time-only hazard closed |
| `normalizers` — phone / amount / account | 🟢 | E.164, quote-stripping, `-:` prefix cleaning |
| Dr/Cr orientation | 🟢 | Follows the **balance delta**, not column order. Decided alphabetically it inverted every direction in one file |
| `validation.check_balances` | 🟢 | 31 accounts with ledger breaks flagged on FIR 65-2024 |
| Duplicate event dedupe | 🟢 | Keys on the full session tuple; collapsing concurrent IP sessions was losing evidence |

## 4. Entity resolution

| Component | Status | Evidence |
|---|---|---|
| `resolve` / `assign_entities` | 🟢 | 6,681 core entities on FIR 65-2024 (was 4,132) |
| Merge keys `PHONE / ACCOUNT_NO / IMEI / IMSI` | 🔵 | **Decision: not extending to AADHAAR / PAN / GSTIN.** Simulated: 5 anchored Aadhaar, 30 PAN, 1 GSTIN in text sources → **1 entity merged**. Not worth three identifier types plus a PII policy |
| Officer-phone veto (`has_admin_role_columns`) | 🟢 | 94 of 98 officers have one mobile vs 10 of 32 accounts. Prevents merging mule accounts into police entities |
| Oversized-component circuit breaker | 🟢 | Fired correctly on `E03390` (3,045 identifiers, hub `PHONE +919702000558`) |
| `account+phone = 3` | 🟢 | Genuine and small. The low number **is the guard working**, not a defect |

## 5. Correlation

| Component | Status | Evidence |
|---|---|---|
| `timeline_builder` | 🟢 | Per-entity, bisect-indexed. Uses **primary** semantics |
| `window_correlator` | 🟢 | Uses **participant** semantics (primary ∪ counterparty), documented and intentional |
| STRONG / MEDIUM tiers | 🟢 | Only these two exist in code; there is no WEAK tier |
| **STRONG = 0** | 🔴 | **0 at every window from 1 to 60 min** — not a calibration problem. 7 entities now hold CALL+IP; the missing leg is the transaction, needing a real account↔phone link |
| timeline vs correlator semantics | 🟡 | Inconsistent. `correlate` works around it by re-deriving transactions at `window_correlator.py:86`. Documented, not changed |

## 6. Detection and risk

| Component | Status | Evidence |
|---|---|---|
| 6 rules on `demo` | 🟢 | Fire as designed |
| `high_risk_entities = 0` on real data | 🟡 | **Two independent causes**, not one |
| — cause 1: FATF thresholds tuned for the fixture | 🟡 | F1 open in the fix queue |
| — cause 2: `features` is primary-only | 🟡 | **15,098** entities hold transactions only as counterparty → empty feature vector. `E02650` has 84 transactions, ₹280,700 in / ₹268,508 out, `max_rapid_forward` 1.0 — and `mule_account` cannot fire on it. Simulation: `rapid_in_out` 20 → 120, `mule_account` 0 → 3 |
| MEDIUM hits never reach the risk model | 🟡 | `apply_analysis` passes STRONG only. Harmless while STRONG = 0; a bug the moment it is not. Explains `top_risk_score` flat at 54.3 across all five windows |
| `layering` / `circular_flow` | 🟢 | Read `transfers`, which already carries counterparty flows — unaffected by the above |

## 7. Reject reporting (rule 2: nothing dropped silently)

| Path | Status |
|---|---|
| Row-level mapping failures | 🟢 itemised with a reason |
| Blank / layout rows | 🟢 separated as non-evidentiary (**42,761** on FIR 65-2024) |
| Per-file parse failures | 🟢 reach `Investigation.rejects` |
| Files never opened | 🟢 recorded with a reason, **categorised** so 47 actionable files are not hidden inside 2,571 |
| Over-cap PDFs | 🟢 recorded as `"scanned PDF, no text layer … needs OCR"` |
| PDF parsing disabled | 🟢 recorded |
| Duplicate exhibits | 🟢 parsed once, recorded with `duplicate_of` |
| Archive budget / depth / password / unreadable | 🟢 **all now reject entries.** 534 members unextracted on one archive |
| **Remaining rule-2 gaps** | 🟢 none known |

## 8. Measurement tooling

| Tool | Status | Purpose |
|---|---|---|
| `scripts/measure_ingestion.py` | 🟢 | **Authoritative** ingestion figures; composes rejects exactly as `run_base` does |
| `scripts/census_skipped.py` | 🟢 | Sub-minute pre-flight estimate. **Explicitly not the coverage figure** — one archive level, ignores the budget |
| `scripts/run_pipeline.py` | 🟢 | Full pipeline with `--save` |
| `ERAKSHAK_VALUE_TYPING` / `ERAKSHAK_STRUCTURE_RECOVERY` | 🟢 | Flags so both arms of an A/B run the same build |

---

## 9. Needs work — ranked

Five items from the previous revision are **closed**, and three of the five were closed by
*re-measuring* rather than by engineering — the recorded figure was stale. That is now the
first step for anything on this list.

| # | Item | Size | Why it is not done |
|---|---|---|---|
| 1 | WhatsApp `_chat.txt` | **5,889 rows** — now the single largest recoverable block | ⚪ Blocked on the `MESSAGE` event-type decision, not on code |
| 2 | Detector primary-only semantics | 15,098 entities | ⚪ Needs its own validation baseline — impact already quantified |
| 3 | MEDIUM hits absent from risk model | latent | Small fix, but changes risk output → wants a baseline |
| 4 | F1 threshold calibration | FR-11/12/13 | **Premise weakened — see §9.1.** Needs re-scoping before any gate is touched |
| 5 | Residual "no time anchor" rows | 17,811 rows | Mostly NCRP state rosters that legitimately carry no timestamps, so largely *not* recoverable as events |
| 6 | Residual broken-geometry PDFs | 976 rows | Down from 9,792. Long tail, low value per unit of work |

**Closed since the previous revision:** risk heat map (F5, FR-18 green) · location filter
(F7, FR-15 green) · IPDR row rejects (F6, FR-3 green — figure was stale) · STR content review
(FR-17 green, four defects fixed) · Bank of Baroda ledger layout (**0 → 743 events**).

### 9.1 F1 needs re-scoping, not tuning

F1's premise is that `high_risk_entities = 0` on `FIR 65-2024` means the FATF gates are
mis-calibrated for real money. The first full run of `FIR-0006-2025 U` contradicts that: it
produces **2 high-risk entities and a top score of 85.1 with the identical, unrescaled
scoring**.

So the gates work. `FIR 65-2024` has no entity exhibiting enough typologies, which is a
statement about that case's evidence. Two measured causes of its zero, neither a threshold:

1. that case genuinely lacks the typology coverage — confirmed by a second case reaching 85.1
   on the same config;
2. `detection/features` aggregates by primary entity only, so 15,098 entities holding
   transactions solely as a counterparty carry an empty feature vector at **any** threshold
   (§6).

Rescaling the bands to force a non-zero count on `FIR 65-2024` would have inflated
`FIR-0006-2025 U` and diluted its two genuine highs. Recommendation: replace "calibrate the
thresholds" with the **rule eligibility report** F1 already proposes — per rule, how many
entities were eligible and how many fired — so `eligible=0` and `fired=0` stop looking alike.
That is the part of F1 that is still clearly worth doing.

## 10. Needs a decision from you ⚪

| Question | Consequence either way |
|---|---|
| **Add a `MESSAGE` event type?** | Unlocks 5,148 rows of timestamped WhatsApp chat. Touches the canonical model, correlation, detection, graph and UI — a new baseline. Mapping chat onto `CALL` would put false call records into evidence, so it is this or nothing |
| **Change detector semantics to participant?** | `rapid_in_out` 20 → 120, `mule_account` 0 → 3. Needs a fresh validation baseline; the current design (participant for relationships, primary for an entity's own behaviour) is coherent, just undocumented in its effect |
| **Raise the 512 MB archive budget?** | Would extract 534 more members from one archive, including `00002545-Vivek Aadhar card.pdf`. It is a zip-bomb guard, so this is a security trade-off, not a tuning choice |
| **Request 5 KYC rows from the case officer?** | The only measured path to FR-9 STRONG. Numbers in §11 |

## 11. Blocked on evidence, not code 🔴

**FR-9 STRONG = 0.** Needs verified account↔mobile pairs for five MSISDNs that already have
both call and IP activity:

```
FIR 65-2024     : +919537658408  +919687045370
FIR-0006-2025 U : +919099102222  +919737002222  +919825504222
```

One row each in `entity_map.csv` makes STRONG testable with no new code and no inferred link.
Everything cheaper has been tried and measured: the window is not the problem (0 at 1–60 min),
the scans cannot supply verified pairs (OCR gave 9 of 10 digits with nothing to check it
against), and the one file that looked like the bridge carries the investigating officer's
phone.

---

## 12. Requirement scorecard

**9 green · 9 amber · 1 red.** FR-3 moved red → amber this cycle. FR-9 is the only red, and is
blocked on evidence rather than code. Full detail in `PS_COMPLIANCE_AND_FIX_PLAN.md` §7.

## 13. Headline numbers — `FIR 65-2024`, W=10

| Metric | Before | Now |
|---|---|---|
| Transactions | 35,870 | **39,170** |
| IP sessions | 69 | **4,133** |
| Events | 238,985 | **246,353** |
| Entities | 4,132 | **6,681** |
| `rejected_rows` | 140,040 | **118,836** |
| Rows stranded unrecognised | 23,846 | **16,307** |
| Parse time | 1,043 s | **646 s** |
| Tests | 142 | **215** |

`FIR-0006-2025 U` ingestion: 456,423 events · 344,047 transactions · 202 IP sessions.
Its full-pipeline entity/correlation figures are pending a first run.
