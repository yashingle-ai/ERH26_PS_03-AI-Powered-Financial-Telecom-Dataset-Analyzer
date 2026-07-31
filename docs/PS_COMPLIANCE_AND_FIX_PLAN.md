# ERakshak — problem-statement compliance and fix plan

**Problem statement:** ERH26_PS_03 — AI-Powered Financial & Telecom Dataset Analyzer
(Bank, CDR & IPDR Fusion)
**Assessed:** 28 Jul 2026 against `fir-65-2024`; **re-validated 30 Jul 2026 against two full
case folders** — `FIR 65-2024` (2.0 GB) and `FIR-0006-2025 U` (2.1 GB). §7 carries the current
figures; §1 rows are updated to match.
**Method:** every figure measured on this machine. Nothing carried over from a prior report.
Ingestion figures reproduce with `python -m scripts.measure_ingestion --input <case>`.

This file is the working tracker. Each fix below gets implemented, tested, and its row
updated with before/after numbers. A fix that does not move its number stays open and says
so.

---

## 1. Scorecard

19 requirements from `research/02_requirement_analysis.md`.

| FR | Requirement | Status | Measured evidence |
|---|---|---|---|
| 1 | Parse bank statements (Excel/PDF/CSV) | 🟡 works, lossy | **140** BANK tables → **39,170 txns** (was 122 / 36,281). Fixed-width print statements and broken-geometry portal PDFs now read |
| 2 | Parse CDR | 🟢 works | 91 tables → **203,050 calls**; 24% rejects are mostly true duplicates. `calls` invariant across five builds on `FIR-0006-2025 U` (112,174) — see §7.3 |
| 3 | Parse IPDR | 🟢 **works** | **59** IPDR tables → **4,133 sessions** (was 12 / 69). Every IPDR file present now parses with **zero row rejects** — TRAI 21/21 and 54/54, iprange 7/7 (F6 closed 30 Jul). `FIR-0006-2025 U` carries no telecom IPDR at all; its 202 sessions are all Google legal-process HTML, which is a property of that case rather than a parser gap |
| 4 | Schema mapping / auto-detection | 🟡 improving | **658 of 951 unrecognised** (was 712 of 939). Rows stranded in unrecognised tables **23,846 → 16,307**; 101 tables claimed on values, all flagged for review |
| 5 | Row-level reject diagnostics | 🟢 works | **118,836** rows itemised (was 139,534), split **42,761 non-evidentiary / 76,075 unmapped**; plus **467 files never opened** and **21 duplicate exhibits**, both previously invisible |
| 6 | Unified entity model | 🟡 partial | **6,681** entities (was 4,182); **ACCOUNT_NO+PHONE = 3** (was 1). 25,695 counting external counterparty singletons — the two figures are not interchangeable, see §7.7 |
| 7 | Timestamp normalisation | 🟢 works | IST canonical; time-only hazard closed 28 Jul |
| 8 | Unified timeline | 🟢 works | per-entity, bisect-indexed |
| 9 | **Temporal coincidence (flagship)** | 🔴 STRONG = 0 | **0 at every window from 1 to 60 min** — not a calibration problem. MEDIUM 2 → 6 as W widens. **7 entities now hold CALL+IP** (was 6 with any IP at all); the missing leg is the transaction, i.e. the account↔phone bridge. The original "no IP evidence exists" proof covered only the IPDR files — see §7 |
| 10 | Link via UPI / IP / IMEI / beneficiary | 🟡 partial | UPI 2,852 · BENEFICIARY 10,413 · PHONE 9,246 · IMEI 30 · IMSI 32 · **IP 18** (was 6) · **ACCOUNT_NO 3,022** (was 549) · **account↔phone 3** (was 1) |
| 11 | Rules + ML detection | 🟡 **causes now settled** | All 8 rules fire on `demo`, scenario recall **15/15**. On `fir-65-2024` 6 of 8 fire (148 flags). Seven detection defects fixed 30 Jul — §8 — including one regression that had moved every observed entity's ML score by up to 12.4 points. `0 high-risk on real` is now explained per rule rather than open |
| 12 | Risk scores | 🟡 **saturation instrumented** | demo 3 high / 14 med / 87 low. Enabled weights sum to **1.2** against a component capped at **1.0**, so 6 and 8 typologies can tie; `typologies_fired` / `rule_weight_raw` / `rule_component_saturated` added as ranking tiebreaks. **No entity on either fixture exceeds 1.0** — preventive, not an observed mis-ranking. `ml_scored` now separates "found nothing unusual" from "never had a profile" |
| 13 | Mule-account signatures | 🟡 **eligible = 6, not 9,996** | Counterparty-side flows fixed, so rules can now see an account visible only as somebody else's payee: `mule_account` eligibility on `demo` 30 → 64. It still fires 0 on both real cases, and that is **correct on the evidence** — a counterparty-only entity is a terminal payee, so `max_rapid_forward` is 0 by definition. Six entities in 7,358 reach fan-in ≥ 5; none forwards. The fix's actual yield was elsewhere: **`structuring` 9 → 23 on `FIR-0006-2025 U`**, 14 counterparty accounts each receiving ≥3 credits in [₹9L, ₹10L) — the accounts money was structured *into* |
| 14 | Money-flow + comms graphs, drill-down | 🟢 works | 8,435 nodes on real data, HTTP 200 |
| 15 | Filter / search (entity, amount, time, location) | 🟢 **works** | all four on **both** paths: the DSL via `/v1/query`, and `/v1/events` directly (`entity`, `location`, `min_amount`/`max_amount`, `start`/`end`) as of 30 Jul. `location` matches tower location or cell id on both, so they answer the same question |
| 16 | Forensic report (PDF/Word) | 🟢 **works** | `POST /v1/report/{ds}` streams PDF (`%PDF`, 92,935 B) and DOCX (`PK`, 123,073 B); bad fmt → 400 |
| 17 | STR generation (bonus) | 🟢 **works, reviewed** | read against real output 30 Jul; four problems found and fixed — grounds were **silently truncated** at 5 and 3, the subject was named only by `label` (a bare account number on real data), there were no transaction particulars, and every high **and medium** entity was told to "freeze/monitor" down to a score of 48.6. Action is now graded by band and no entry recommends a freeze |
| 18 | Risk heat maps (bonus) | 🟢 **works** | `GET /v1/risk-heatmap/{ds}` returns the entities × typologies matrix; rendered on the React **Detections** page as an accessible table, plus the original Streamlit view. Verified on `demo`: 6 typologies × 5 entities, matrix aligned to both axes, ordered by risk score |
| 19 | Natural-language query (bonus) | 🟢 works | Gemini 6/6 planned; offline fallback; plain-text answers |

**11 green · 7 amber · 1 red** (was 8 / 7 / 4 at the start of the fix work, 9 / 8 / 2 on
28 Jul).

Moved to green on 30 Jul: **FR-3** (every IPDR file present parses with zero row rejects —
the "11 of 18" figure was stale, F6), **FR-15** (all four filters now on `/v1/events`, not
only the DSL, F7), **FR-18** (heat map exposed over HTTP and rendered in React, F5), and
**FR-17** (STR section read against real output; four defects fixed, including grounds of
suspicion that were being silently truncated).

Three of those four were closed by **re-measuring** rather than by new code — the recorded
figure was obsolete. That is now the first step for any remaining item.

Remaining red: **FR-9 only**, and it is blocked on evidence rather than code — STRONG is 0 at
every window from 1 to 60 minutes, so no threshold or parser change reaches it. The narrowest
unblock is five KYC rows from the case officer; see §7.6.

---

## 2. Fix queue

Ordered by how much each unblocks, not by effort. Status updated as work lands.

| # | Fix | FRs | Status |
|---|---|---|---|
| F3 | Expose the forensic report over HTTP | 16, 17 | 🟢 **DONE** `7d20672` — valid PDF (`%PDF`, 92,935 B) + DOCX (`PK`, 123,073 B); bad fmt → 400 |
| F4a | Header-block mobile lost to a space | 6, 10 | 🟢 **DONE** `7d20672` — country-code-only extractions **3-of-4 → 0** |
| F2a | NCRP / Cyber Police Portal profile | 1, 4 | 🟢 **DONE** `f9fb19e` — matches real portal exports; mapping verified field by field |
| F2b | Split stacked tables inside one grid (gap G3) | 4, 1 | 🟢 **DONE** `f9fb19e` — sections +9 (not +127); cleared its baseline |
| F2c | Profile may claim a file it can demonstrably map | 4 | 🟢 **DONE** `f9fb19e` — unrecognised **747 → 712**, BANK files **78 → 122** |
| F8 | Blank layout rows recorded under their own reason | 5 | 🟢 **DONE** `f9fb19e` — correct, but **not the win it was billed as**; see the correction below |
| F1 | Calibrate detection thresholds + eligibility report | 11, 12, 13 | 🟠 **RE-SCOPED 30 Jul — the calibration half is withdrawn.** `FIR-0006-2025 U` produces **2 high-risk entities, top score 85.1, on the identical unrescaled config**, so the gates are not mis-calibrated; `fir-65-2024` simply has no entity with enough typologies. Rescaling to force a non-zero count there would have inflated this case and diluted its two genuine highs. The **eligibility report** half stands and is the remaining work: `eligible=0` and `fired=0` must stop looking alike. A second measured cause of the zero is unrelated to thresholds — see §7.7 |
| F4b | Account↔phone bridge from complaint tables | 6, 10, 9 | **OPEN** — now off zero (1 entity), see below |
| F5 | Risk heat map in the API + React | 18 | 🟢 **DONE** 30 Jul — `GET /v1/risk-heatmap/{ds}` returns the entities × typologies matrix; React renders it on the Detections page as an accessible table (no new charting dependency). Empty state distinguishes "no typology fired" from "nothing evaluated" via `entities_scored` vs `entities_with_a_fired_rule` |
| F6 | IPDR row rejects (11 of 18) | 3 | 🟢 **DONE — the figure was stale.** Re-measured 30 Jul: the TRAI files parse **21/21 and 54/54 rows with zero rejects**, `ipdr_iprange` 7/7. The one remaining unrecognised IPDR-named file is `IPDR - Common IMEI Report.xlsx`, which is a report rather than session data and is handled by its own path (`er_common_imei`, 10 IMEI↔PHONE links). Closed by the timestamp and value-typing work, not by a targeted fix |
| F7 | Location filter on `/v1/events` | 15 | 🟢 **DONE** 30 Jul — all four FR-15 filters added: `entity`, `location`, `min_amount`/`max_amount`, `start`/`end`. `location` matches tower location **or** cell id, the same two fields the DSL reads, so the endpoint and `/v1/query` cannot disagree about one event. Naive time bounds are read as IST, not UTC — otherwise a `start=2024-05-15` would shift the window 5.5 h. Verified on `smoke`: 547 → 121 by type, 299 by `min_amount`, 242 by `max_amount`, 0 by `end`; a malformed bound narrows nothing instead of 500-ing |
| — | FR-9 STRONG correlation | 9 | ⚫ **CLOSED — evidence gap, not a defect** |

### Cumulative effect of the fixes above — `fir-65-2024`, W=10

| Metric | Session start | After F2/F3/F4a | Change |
|---|---|---|---|
| Transactions | 35,870 | **36,281** | +411 |
| Transfers | 12,616 | **12,845** | +229 |
| Events | 238,985 | **239,396** | +411 |
| Entities | 4,132 | **4,182** | +50 |
| Entities with `ACCOUNT_NO` | 499 | **549** | +50 |
| **Entities with account AND phone** | **0** | **1** | first non-zero all week |
| Unrecognised files | 747 | **712** | −35 |
| BANK files recognised | 78 | **122** | +44 |
| `rejected_rows` | 140,040 | **139,534** | −506 |
| Correlation STRONG / MEDIUM | 0 / 2 | **0 / 2** | unchanged (expected) |
| Tests | 142 | **146** | +4 |

**On the account↔phone bridge reaching 1.** One entity is not a result. It matters only
because every prior measurement read exactly 0, so it is the first evidence the bridge
works end to end on real evidence without a fabricated link. MEDIUM stayed at 2 — the
bridged entity has no call and transaction inside the same window.

**Two bugs of mine, caught by measuring rather than asserting.** Worth recording because
both would have shipped as improvements:

1. The stacked-table splitter first measured **−420 transactions**. Sections after the
   first were stranded without the document's account block, and `_norm_bank` drops a row
   with no account, so "recovery" was destroying data. Fixed by having every section
   inherit the preamble.
2. It also reported `SOA.pdf: split into 40 stacked tables` — one multi-page statement
   repeating its column header per page. Fixed by merging consecutive identical headers.

### The recoverable-rows figure, corrected twice — final measured answer

Recorded in full because the reasoning error is instructive, not to pad the file.

1. First claim: **27,713 recoverable rows** in the unrecognised files.
2. Then, after opening one 1,909-row NCRP export and finding 1,268 blank rows in it, I
   revised that to "two thirds is padding, the real ceiling is far lower".
3. **Both were wrong.** Measured across all 778 unrecognised files:

```
rows in unrecognised files : 25,537
  entirely blank           :    181   (1%)
  carry content            : 25,356   <-- the real recoverable ceiling
blank rows across ALL files:    185 of 378,812
```

The blank rows were peculiar to the single file I sampled. Generalising from one file was
the mistake — the same trap as trusting a count a feature reports about itself.

**Consequence for F8:** its premise was overstated. `rejected_rows` is *not* inflated by
padding — 185 rows out of 378,812. The blank-row reason is still correct to record and
costs nothing, but it is bookkeeping hygiene, not the honesty fix it was billed as. The
~140k rejects are overwhelmingly genuine mapping failures, which makes F2 (profile
coverage) the real work.

---

## 3. Diagnoses

### F1 — detection is calibrated for the synthetic fixture, not real money

Six rules fire on `demo` and yield 3 high-risk entities. On the real case, with **13× more
transactions**, high-risk is **0**.

`config/scoring_rules.yaml` states its own problem in the header:

> FATF-style configurable defaults (Q5 = ASSUMED). Tune with analyst feedback / real data.

Nobody tuned them. The gates are absolute rupee amounts:

```yaml
structuring:    reporting_threshold_inr: 1000000   # 10 lakh
layering:       min_amount_inr: 10000
circular_flow:  min_amount_inr: 10000
mule_account:   min_fan_in: 5
```

`demo`'s synthetic transactions reach ₹200,979. Real ICORE rows inspected by hand were
₹5,000 / ₹39,000 / ₹51,000. If the real distribution sits below these gates, three rule
families are **silently inert** — and the system reports "0 high-risk entities", which an
investigator reads as "nothing suspicious here" rather than "the detector never ran".

That is the same failure class as the silent row drops fixed earlier this week: success
reported, work not done.

**Production-grade fix**

1. Do not hand-pick new constants — they would be wrong for the next case. Derive gates
   from the dataset's own amount distribution (percentile-based), with the absolute values
   kept as configurable floors for genuine regulatory thresholds.
2. Add a **rule eligibility report**: per rule, how many entities were *eligible* and how
   many *fired*. `eligible=0` and `fired=0` must be visibly different states. This is the
   deliverable that makes the calibration auditable.
3. Regression test: a rule with zero eligible entities must be reported as not-run, never
   as a clean pass.

**Verify:** rule-by-rule eligible/fired counts on `fir-65-2024`, and a non-zero high-risk
count that survives manual inspection of the top entity. If a rule still cannot fire on
real data, say which and why.

### F2 — 80% of files never classified

722 of 905. Upstream of almost everything: an unclassified file yields no transactions, no
accounts, and no `registered_mobile`, so it starves FR-6, FR-10 and FR-12 at once.

**Production-grade fix:** cluster the headers of unrecognised files that *do* carry parsed
rows, build profiles from the real clusters, and add a coverage gate so a regression in
classification fails loudly instead of quietly shrinking the evidence base.

**Verify:** unrecognised share before/after; transactions and `ACCOUNT_NO` count before/after.

### F3 — the forensic report is built but unplugged

`reporting.generate(data, out_dir, fmt)` produces real files — 93 KB PDF and 123 KB DOCX
generated during this assessment. But the API exposes **11 routes and none is a report
route**, so only the Streamlit dashboard can reach it. The React app — the primary UI —
cannot produce the problem statement's headline deliverable.

It also requires the caller to inject `window` and `dataset` keys that are not part of the
`Investigation` dataclass. That coupling belongs behind the endpoint, not in every caller;
it is why the first three call attempts failed with `KeyError: 'window'`.

**Production-grade fix:** `POST /v1/report/{ds}` returning a streamed file with the correct
content type, payload assembly inside the endpoint, plus a React action. Generated reports
land in `data/outputs/`, which is gitignored and dockerignored — they are derived from case
data and inherit its sensitivity.

**Verify:** endpoint returns a valid PDF and DOCX for a real dataset; file opens; the
evidentiary timeline and charts are present.

### F4 — account↔phone identities never merge

```
entities with ACCOUNT_NO : 499
entities with PHONE      : 9,241
entities with BOTH       : 0
```

Proof this is the ceiling and not a symptom: transactions went 1,800 → 8,414 → 21,052 →
35,870 (**20×**) while MEDIUM correlation stayed at **2** throughout.

Three routes, cheapest first:

1. `datasets/entity_map.template.csv` filled from KYC. **Requires real account↔mobile pairs
   that must come from the case officer.** These must never be fabricated — an invented
   link between an account and a phone manufactures evidence and could place an innocent
   person inside a correlation hit.
2. `header_identity.registered_mobile` — already declared in the bank profile, never
   measured. If statements carry it and it is being dropped, that is a fixable bug.
3. Widen UPI-VPA mining. It already produced all 10 CALL+TXN entities, so the mechanism
   works; the question is yield.

**Verify:** `ACCOUNT_NO+PHONE` count, and MEDIUM correlation, before/after.

### F5 — risk heat maps absent

FR-18, bonus. Zero references in the codebase. The smallest honest scope of the remaining
work.

### F6 — IPDR rejects 11 of 18 rows

Improved from 100%, not solved. Small in row count, but IPDR is one of FR-9's three legs.

### F7 — location filter unverified

FR-15 names location explicitly. CDR carries cell-ID/location fields; whether they are
filterable end-to-end has not been checked.

---

## 4. Closed: FR-9 STRONG correlation

Not a defect. Measured at source-file level:

```
IPDR MSISDNs : 7500107305, 8535088505
IPDR IMEIs   : 355330170920575, 358419296846579
IPDR IMSIs   : 405870182224029, 405870182365083

each of the six, searched across cdr/                  : 0 files
each of the six, searched anywhere outside ipdr/        : 0 files
```

Those identifiers exist nowhere in the case except the IPDR files themselves. Two
subscribers have internet records and nothing else; nobody else has internet records at
all. Only 6 of 11,914 entities have any IP session. No parser change alters this.

One hypothesis remains untestable: **7 password-protected archives, 31 encrypted members**
— all CDR or IMEI, **none IPDR**. A password therefore adds call coverage, and can only
produce a STRONG hit if an unlocked CDR happens to contain one of those two MSISDNs.

Note for the record: a locked archive contains `8535088005`, which is **not** the IPDR's
`8535088505`. Different numbers. Not a lead.

**Action:** request the archive password from the case officer. Everything else about STRONG
is blocked on evidence, not code.

---

## 5. How each fix is verified

State the expected number **before** measuring. Then diff every metric, not only the
targeted one, and explain anything that moves — including numbers that go down.

```bash
docker compose up -d --build
docker compose exec -T api ruff check backend tools scripts
docker compose exec -T api sh -c "pytest backend/tests -p no:warnings 2>&1 | tail -2"
cd frontend && npx tsc --noEmit && npm run build && npx vitest run
```

```
POST /v1/analyze  {"dataset":"fir-65-2024","window_minutes":10}
GET  /v1/data-quality/fir-65-2024?window=10
```

Baseline to diff against (28 Jul 2026, `fir-65-2024`, W=10):

| Metric | Value |
|---|---|
| files | 930 |
| events | 238,985 |
| transactions | 35,870 |
| calls | 203,046 |
| ip_sessions | 69 |
| entities | 4,132 |
| correlation_hits (STRONG) | 0 |
| correlation_hits_medium | 2 |
| transfers | 12,616 |
| high_risk_entities | 0 |
| rejected_rows | 140,040 |
| tests | 142 passed |

### Traps already paid for

- **A zero is ambiguous** — identical whether a feature works and found nothing or never
  ran. Re-run against data known to contain a hit.
- **Never trust a count a feature reports about itself** — MEDIUM = 2 was re-derived by
  walking all 224k events with an independent bisect.
- **`/app` is `COPY`ed into the image, not bind-mounted** — host edits do not reach a
  running container. Always `docker compose up -d --build`.
- **Never run a second `_analyze` inside the API container** — a duplicate ~3.5 GB copy
  OOM-kills it. Go through the HTTP API.
- **Do not rebuild while a long analyse runs** — it kills the run.
- **A cold `fir-65-2024` analyse is ~13 min** and pins a GIL-holding worker, so the API is
  unresponsive throughout. Not a hang.
- **Run the whole test suite, never one file** — users seed into a module-level cache, so
  tests can pass alone and 401 together.

---

## 6. Rules that do not bend

1. **The LLM never sees case data** — question plus schema vocabulary only, enforced by
   `_assert_no_case_data`; answers are composed locally in `answer.py`.
2. **Nothing is dropped silently.** Every rejected row is counted and surfaced with a
   reason. This extends to detection: a rule that never ran must not look like a rule that
   found nothing.
3. **Never fabricate an identity link.** No invented account↔phone pairs, ever.
4. **Real evidence never reaches git.** `git status --porcelain` must show no FIR files, no
   `.env`, no `*.db`.
5. **Do not redefine a headline metric to make a gate pass.** Add a new field instead — as
   `correlation_hits_medium` did.

---

## 7. Validation cycle — 30 Jul 2026

Two case folders this time, not one: `FIR 65-2024` and `FIR-0006-2025 U`. Every figure below
is reproducible with `python -m scripts.measure_ingestion --input <case>`, and both recovery
paths are switchable (`ERAKSHAK_VALUE_TYPING`, `ERAKSHAK_STRUCTURE_RECOVERY`) so the two arms
of any A/B run the same build. That last point is not a convenience — attributing a
30,976-event change from run timestamps alone proved impossible without it.

### 7.1 Objective

Stop the pipeline losing files and rows. Four classes of file were producing no events. None
needed a new profile; they needed to be opened and given a readable shape.

### 7.2 Before / after — `FIR 65-2024`, W=10

| Metric | 28 Jul baseline | 30 Jul | Change |
|---|---|---|---|
| files | 930 | 986 | +56 |
| events | 238,985 | **246,353** | +7,368 |
| transactions | 35,870 | **39,170** | +3,300 |
| calls | 203,046 | 203,050 | +4 |
| **ip_sessions** | 69 | **4,133** | **60x** |
| entities (non-external) | 4,132 | **6,681** | +2,549 |
| `ACCOUNT_NO` identifiers | 549 | **3,022** | 5.5x |
| entities with account **and** phone | 1 | **3** | +2 |
| rejected_rows | 140,040 | **118,836** | −21,204 |
| rows stranded in unrecognised tables | 23,846 | **16,307** | −32% |
| correlation STRONG / MEDIUM | 0 / 2 | 0 / 2 | unchanged |
| high_risk_entities | 0 | 0 | unchanged |
| parse seconds | 1,043 | **646** | −38% |

### 7.3 Before / after — `FIR-0006-2025 U` (first validated run)

| Metric | Value |
|---|---|
| files / tables | 1,176 / 1,545 |
| events | **456,423** |
| transactions | **344,047** |
| calls | 112,174 |
| ip_sessions | **202** (was 0 — this case was reported as having no IPDR at all) |
| rejected_rows | 302,597 (168,735 non-evidentiary / 133,862 unmapped) |
| unrecognised tables | 1,279 of 1,545 (83%) |

`calls = 112,174` is identical across all five builds measured on this case, through geometry
recovery, duplicate detection and the preamble fix. That invariance is the strongest evidence
available that those changes are non-destructive on the telecom path.

**Full pipeline, first ever run on this case** (30 Jul, W=10, 2,927 s):

| Metric | Value |
|---|---|
| files | 1,555 |
| events | 456,431 |
| transactions | 344,055 |
| calls | 112,174 |
| ip_sessions | 202 |
| entities | 5,362 |
| transfers | 64,812 |
| **high_risk_entities** | **2** |
| **top_risk_score** | **85.1** |
| risk bands | high 2 · medium 41 · low 5,420 |
| correlation STRONG / MEDIUM | **0 / 0** |
| entities with account **and** phone | **4** |
| entities with CALL + IP | 3 |
| entities with CALL + TXN | 1 |
| `ACCOUNT_NO` identifiers | 3,762 |
| `UPI_ID` identifiers | 152,816 |

**This vindicates leaving the scoring untouched.** F1's premise was that
`high_risk_entities = 0` on `fir-65-2024` might mean the FATF gates were mis-calibrated. This
case produces **2 high-risk entities and a top score of 85.1 with the identical, unrescaled
scoring**. So the gates work; `fir-65-2024` simply has no entity exhibiting enough
typologies. Had the bands been renormalised to force a non-zero count there, this case would
now be inflated and its two genuine highs diluted.

**MEDIUM = 0 despite 344,055 transactions**, and only 1 entity holds both a call and a
transaction — so no call/transfer pair falls inside a 10-minute window. Same binding
constraint as `fir-65-2024`: the account↔phone bridge, not the window.

Internal consistency check: the ingestion-only run measured 344,047 transactions and this
full run 344,055, a difference of **+8** — exactly the gain the `header_idx` fix produced on
`_Doc_202404201542344604122.pdf` (115 → 123 events), which landed between the two runs.

### 7.4 Root causes fixed, with attribution

| Fix | Root cause | Measured effect |
|---|---|---|
| HTML reader + `google_subscriber` profile | `.html` absent from `FORMAT_BY_EXT`, so Google legal-process responses were never opened | IP_SESSION 69 to 4,133; FIR-0006 0 to 202 |
| Fixed-width reader | a printed statement has no delimiter, so pandas returned one `Unnamed: 0` column | one file 0 to 84 events, ledger reconciles exactly |
| Geometry recovery | `pdfplumber` flattens every page's tables into one row list: glued widths, six-row headers, records spanning five rows whose date sat on a discarded continuation | complaint folder 14 to 389 events |
| Duplicate detection | the same exhibit parsed repeatedly | 179 files / 108 MB on FIR-0006, events unchanged |
| Instance-level column typing | — | **+23 events. Near-neutral, and not presented as more** |

Attribution matters here: the headline gain is **opening files nobody had opened**, not
smarter matching. Value typing earns its place only because it is the sole mechanism that can
map a headerless statement or a recovered region.

### 7.5 The regression, and why it took five attempts

Geometry recovery first **cost 30,976 transactions** on `FIR-0006-2025 U`. Recorded in full
because the reasoning failures are the instructive part.

| Predicted mechanism | Verdict |
|---|---|
| `_coalesce` over-merging a sparse first column | wrong |
| insufficient row coverage | wrong — 98.2% of rows were inside accepted spans |
| polluted merged headers breaking aliases | wrong — headers were clean |
| preamble keyed on the first *span* | wrong — the preamble itself spans two runs |

Three real causes, each found by **measuring**, not reasoning:

1. `['Page Total','0.00','4890309.00']` rows of raw width 3 inside a width-8 table split one
   9,845-row statement into **183 runs**.
2. Only **1 of 183** spans began with a label row; `if not header_rows: continue` discarded
   the other 182 — 10,027 rows became 25 records.
3. `[headers] + rows` discarded the document preamble holding `Account No | 60532637196`.
   `_norm_bank` drops a row with no account, so one file went **6,869 transactions to 0** with
   its records and headers otherwise recovered perfectly.

**Two of the failures were my own instruments.** Both early probes counted *records* while
the acceptance criterion counts *events*, and a record can survive intact while losing the
column that made it mappable — which is exactly how cause 3 hid. A "criterion PASSED" was
declared on that basis and was wrong.

Acceptance criteria, finally measured:

| Criterion | Target | Measured | Result |
|---|---|---|---|
| FIR-0006 TRANSACTION | >= 343,932 | 344,047 | PASS (+115) |
| FIR 65-2024 TRANSACTION | >= 37,916 | 39,170 | PASS (+1,254) |
| FIR 65-2024 IP_SESSION | >= 4,133 | 4,133 | PASS (+0) |

### 7.6 FR-9 window sweep — the flagship, settled

| Window (min) | 1 | 5 | 10 | 30 | 60 |
|---|---|---|---|---|---|
| STRONG | **0** | **0** | **0** | **0** | **0** |
| MEDIUM | 0 | 0 | 2 | 4 | 6 |
| high_risk | 0 | 0 | 0 | 0 | 0 |
| top_risk_score | 54.3 | 54.3 | 54.3 | 54.3 | 54.3 |

Only `TIER_STRONG` and `TIER_MEDIUM` exist in the code; there is no WEAK tier.

**STRONG is 0 across a 60x window range, so FR-9 is not a calibration problem.** MEDIUM grows
monotonically and entities never leave, which is the expected behaviour and a usable
consistency check on the correlator.

What changed since §4 is the *reason*, not the count. §4 proved that the IPDR identifiers
appear in no CDR file — and that proof holds. But it covered only the IPDR files, and a second
source of IP activity existed that the walker never opened. **7 entities now hold both call
and IP evidence.** The missing leg is the transaction, which needs a real account-to-phone link.

**The narrowest useful evidence request** — five KYC rows, for MSISDNs that already have both
call and IP activity:

```
FIR 65-2024     : +919537658408  +919687045370
FIR-0006-2025 U : +919099102222  +919737002222  +919825504222
```

One row each in `entity_map.csv` makes STRONG testable with no new code and no inferred link.
That is a smaller ask than the archive password in §4, which remains open but is now the
second priority.

### 7.7 Entity semantics — participant vs primary

Measured across pipeline stages, because two metrics disagreed and the disagreement was real:

| Stage | Semantics | Verdict |
|---|---|---|
| `timeline_builder` | primary | inconsistent with the correlator; `correlate` works around it by re-deriving transactions |
| `window_correlator._by_participant` | participant | intentional, documented in the docstring |
| `money_flow` | primary-to-primary, primary-to-counterparty on fallback | intentional, documented |
| `graph.service` | participant | intentional |
| `detection/features` | **primary** | design decision with a defect consequence — below |

Runtime evidence on `FIR 65-2024`: **15,098** entities hold transactions only as a
counterparty. Simulating participant semantics without changing production code:

| Rule | Production | Participant sim | Reads |
|---|---|---|---|
| `structuring` | 0 | 0 | `feats` |
| `rapid_in_out` | 20 | **120** | `feats` |
| `mule_account` | **0** | **3** | `feats` |
| `layering` | 55 | 55 | `transfers` |
| `circular_flow` | 15 | 15 | `transfers` |

`layering` and `circular_flow` are unchanged because they read `transfers`, which already
carries counterparty flows. Only the three `feats`-driven rules are affected.

Entity **E02650** — one of the two MEDIUM correlation hits — holds **84 transactions,
Rs 280,700 in and Rs 268,508 out, `max_rapid_forward` = 1.0**, and the detector scores it with
an empty feature vector (`txn_count` = 0). Money in approximately equal to money out with
total rapid forwarding is the mule signature the case is looking for, and `mule_account`
cannot fire on it.

This is a **second, independent cause** of `high_risk_entities = 0`, alongside F1's threshold
calibration. Re-tuning F1 alone could never surface these entities, because their feature
vector is empty at any threshold. The design intent is coherent — participant semantics for
relationships, primary for an entity's own behaviour — but its consequence is invisible, which
violates rule 2: a rule that never ran must not look like a rule that found nothing.

Also measured: `coincidence_count` = 0 for both MEDIUM entities, because `apply_analysis`
passes STRONG hits only to `detection.detect`. Harmless while STRONG is 0; a bug the moment it
is not. It also explains why `top_risk_score` stayed at exactly 54.3 across all five windows.

**No detector semantics were changed.** Doing so needs its own validation baseline.

### 7.8 What "never opened" actually contains

A bare count reads as unread evidence tables. It is not:

| Category | FIR 65-2024 | FIR-0006-2025 U |
|---|---|---|
| non-tabular (image / media / system) | 140 (37%) | **1,974 (90%)** |
| container (holds other files) | 214 (56%) | 125 (6%) |
| **potentially tabular, no reader** | **25 (7%)** | **22 (1%)** |
| unknown / other | 1 | 70 |

The actionable bucket is **47 files across both cases**, and 42 of them are legacy `.doc`.
Everything else is photographs, `.opus` voice notes, `.tif` scans and Outlook containers.
Reporting the aggregate without this split would misdirect effort at 2,571 files when the real
backlog is 47.

Two reconciliation notes, kept because the discrepancy was real and explained rather than
smoothed over. The pipeline counts 467 / 1,788 where this census counts 380 / 2,191:

- FIR 65-2024 has **96 nested `.zip` members**; the pipeline recurses three levels deep and
  finds members the one-level census never sees.
- FIR-0006 holds **1,679 MB uncompressed**, and `WhatsApp Chat - Bhai.zip` alone is 1,079 MB,
  exceeding the 512 MB expansion budget — extraction stops early, so the pipeline sees fewer
  members than exist.

That truncation **is** logged (`archive ... exceeds expansion budget — stopping`) but never
reaches the reject report, so it is invisible in `/v1/data-quality`. By rule 2 it should be a
reject entry, not just a log line. Open.

### 7.9 Performance

| | 28 Jul | 30 Jul |
|---|---|---|
| `FIR 65-2024` parse | 1,043 s | **646 s** (−38%) |
| `FIR-0006-2025 U` parse | — | 2,653 s |

Faster despite doing strictly more work, because duplicate exhibits are now parsed once.

### 7.10 Remaining limitations

1. **FR-9 STRONG = 0** — blocked on the account-to-phone bridge, not on code, not on the window.
2. **`account+phone` = 3** is genuine and small. The one file that looked like the bridge
   carries the *investigating officer's* mobile beside mule accounts — 94 of 98 officers have
   exactly one mobile, only 10 of 32 accounts do, and one constable's number spans two
   accounts. Linking those rows would merge mule accounts into police entities. The guard is
   `has_admin_role_columns`; the low count is that guard working, not a defect.
3. **WhatsApp `_chat.txt` — 5,148 rows** of timestamped communication with no home in the
   canonical model. Mapping it onto `CALL` would put false call records into evidence. Adding
   a `MESSAGE` type is a model change and a new baseline, not a fix.
4. ~~**Detector blind to counterparty-side transactions**~~ — fixed in §8. Counterparty entities
   now carry fan-in and transfer-derived flows. `mule_account` still fires 0 on `fir-65-2024`,
   and per-rule eligibility now shows why: **6 eligible, not 9,996.**
5. **`_Doc_202404201542344604122.pdf` loses 10 of 125 events** under recovery. Unexplained,
   0.003% of the dataset. Recorded as unexplained rather than assumed benign — assuming a
   small residual was harmless is exactly what produced the false PASS in §7.5.
6. **Archive budget truncation is not surfaced** in the reject report — §7.8.
7. **Reference/roster tables** (~4,000 rows) are correctly refused: no timestamps, no
   transactions. Not recoverable as events.

### 7.11 Traps added to the list

- **Count the quantity the criterion names.** Two probes measured records while the criterion
  measured events, and a record survives intact while losing the column that made it mappable.
- **Never attribute a change to code from run timestamps.** Add a flag and run both arms on
  one build.
- **A non-empty result is not a correct result.** Recovery replaced a 10,027-row table with 25
  records and the integration accepted it because the output was merely non-empty.
- **A safety invariant only guards what it measures.** The row-accounting check caught the
  10,027 to 25 collapse and could not have caught the preamble loss, where every row survived.
- **Do not run three case-scale jobs at once.** Three concurrent passes exhausted memory and
  killed a run with `MemoryError` in an unrelated function.
- **Widening a feature-vector population silently refits the model.** Adding counterparty
  entities to `feats` was a rules change on its face; it moved every observed entity's ML score
  by up to 12.4 risk points. Any change to *who is in* a fitted population needs its own A/B.
- **State what a setting was measured to do, not what it was intended to do.** Halving the
  MEDIUM weight was written up as removing a band promotion. It removes none — the same three
  entities cross either way. The justification is evidential, and saying so is the whole point.
- **Each case exists at two paths, and `files` differs between them.** `datasets/FIR 65-2024`
  holds 646 files as delivered, including TIFs and macOS `._` resource forks;
  `datasets/raw/fir-65-2024` holds 506 staged with flattened names. Both produce **identical**
  events (247,492), transactions (40,309), calls (203,050), entities (7,358), transfers (14,217)
  and an identical eligibility table — but `files` reads 952 against 961, because archive
  members are counted and the staged copy expands differently. Quote the path with the figure,
  and never A/B across the two: an early comparison here moved code *and* path at once and
  could attribute nothing.

---

## 8. Detection cycle — 30 Jul 2026

Seven defects, of which **one was a regression introduced by the fix for another** and caught
before merge by A/B rather than by a test. Full detail in `docs/COMPONENT_STATUS.md` §6.1–6.4.

| # | Defect | Fix | Measured effect |
|---|---|---|---|
| D1 | `call_transfer_coincidence` fed STRONG hits only, and STRONG is **0 on both real cases** — the rule was structurally dead on real evidence | Both tiers reach `detect` | `demo` fires 9 → 30, entity-level recall **0.500 → 1.000**; `fir-65-2024` **0 → 2** |
| D2 | MEDIUM scored as heavily as STRONG, so an uncorroborated coincidence contributed like a corroborated one | `medium_weight: 0.075` vs `0.15` | Score contribution 10.5 → 5.3 points. Does **not** change which entities change band |
| D3 | Counterparty-only entities had empty feature vectors, so no rule could fire on an account seen only as somebody else's payee | `features.build` fills fan-in and transfer-derived flows | `mule_account` eligibility on `demo` 30 → 64. **On `FIR-0006-2025 U`, `structuring` fired 9 → 23** — 14 counterparty accounts that each received ≥3 INR credits in [₹9L, ₹10L), 12 of which had no risk row at all before. This, not `mule_account`, was the real yield |
| D4 | **Regression from D3**: the Isolation Forest silently refit over the enlarged population | Fit only on entities holding records of their own; `ml_scored` flag distinguishes the two kinds of 0.0 | Fit population 30 → 104 → **30**. Before the fix: 29 of 30 observed entities moved, mean \|Δml\| 0.252, max 0.414 — **7.6 risk points on average, 12.4 at worst** |
| D5 | `eligible` was `len(feats)` for **5 of 8 rules**, so `mule_account` read "9,996 eligible, 0 fired" | Per-rule structural precondition + a sentence when eligible is 0 | `fir-65-2024`: mule 9,996 → **6**, rapid_in_out → **35**, coincidence → **6**, comm_burst → **3,991**, dormant → **454** |
| D6 | The report cut the eligibility note at **96 characters** — shorter than every note the detector produces, so the reader got the premise and not the conclusion, in the document most likely to be relied on | PDF wraps that column instead of truncating; DOCX never needed a cap | Same defect class as the STR grounds truncated at 5 and 3, in the same file. Pinned in both formats by rendering the report and reading the cell back |
| D7 | `ml_scored` was computed but not persisted, and `create_all` leaves an existing table's shape alone — so the column would have worked on every fresh checkout and failed with "no such column" on the machine with the longest history | Nullable column + a narrow guarded `ALTER TABLE` on connect (nullable adds only; never a drop, rename or type change) | Verified against a database built without the column: added on connect, idempotent on a second run, and a row round-trips with `ml_scored = False` intact |

Verified by A/B against `a7709fe` on `demo`, same dataset, same window: **`ml moved: 0 of 89`**,
and every remaining score move is exactly `0.7 × 0.075 × 100 = 5.3` — one rule's tier weight.
Nothing else in the pipeline moved. Real-case A/B in `COMPONENT_STATUS.md` §6.3.
**278 tests pass**; `test_ml_fit_population.py` pins D4.

Both real cases were then A/B'd with code as the only variable (same staged path, same window).
On `FIR-0006-2025 U` `high_risk_entities` stays at **2** and `top_risk_score` moves 85.2 → 85.5;
on `fir-65-2024` it stays at **0** and 54.3 → 54.2. The baseline arm's 54.3 reproduces the figure
already recorded across the FR-9 window sweep, which is the independent check on the harness.

**Not claimed:** `high_risk_entities` is still 0 on `fir-65-2024` and `mule_account` still fires
0 on either case. That is now *explained* rather than open — a counterparty-only entity in that case is a
terminal payee, money in and never out, because the case holds the victim's statement and not
the mule's, so `max_rapid_forward` is 0 by definition. Six entities in 7,358 reach fan-in ≥ 5 and
none of them forwards. Missing evidence, not a code defect — the same shape as FR-9.
