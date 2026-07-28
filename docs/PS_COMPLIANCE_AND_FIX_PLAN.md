# ERakshak — problem-statement compliance and fix plan

**Problem statement:** ERH26_PS_03 — AI-Powered Financial & Telecom Dataset Analyzer
(Bank, CDR & IPDR Fusion)
**Assessed:** 28 Jul 2026, against `fir-65-2024` (505 staged files / 335 MB) unless stated
**Method:** every figure measured on this machine. Nothing carried over from a prior report.

This file is the working tracker. Each fix below gets implemented, tested, and its row
updated with before/after numbers. A fix that does not move its number stays open and says
so.

---

## 1. Scorecard

19 requirements from `research/02_requirement_analysis.md`.

| FR | Requirement | Status | Measured evidence |
|---|---|---|---|
| 1 | Parse bank statements (Excel/PDF/CSV) | 🟡 works, lossy | **122** BANK files → **36,281 txns** (was 78 / 35,870) |
| 2 | Parse CDR | 🟢 works | 90 files → **203,046 calls**; 24% rejects are mostly true duplicates |
| 3 | Parse IPDR | 🔴 barely | 12 files → **69 sessions**; 11 of 18 rows rejected |
| 4 | Schema mapping / auto-detection | 🟡 improving | **712 of 939 unrecognised** (was 747 of 930); 94 files now claimed by the mappability fallback, all flagged for review |
| 5 | Row-level reject diagnostics | 🟢 works | **139,534** rows itemised via `/v1/data-quality`; summary now splits `blank_rows` / `unmapped_rows` |
| 6 | Unified entity model | 🟡 partial | **4,182** entities; **ACCOUNT_NO+PHONE = 1** (was 0) |
| 7 | Timestamp normalisation | 🟢 works | IST canonical; time-only hazard closed 28 Jul |
| 8 | Unified timeline | 🟢 works | per-entity, bisect-indexed |
| 9 | **Temporal coincidence (flagship)** | 🔴 STRONG = 0 | evidence-blocked, proven at source-file level. MEDIUM = 2 |
| 10 | Link via UPI / IP / IMEI / beneficiary | 🟡 partial | UPI 2,849 · BENEFICIARY 9,816 · IMEI 30 · IMSI 32 · IP 6 · **ACCOUNT_NO 549** (was 499) · **account↔phone 1** (was 0) |
| 11 | Rules + ML detection | 🟡 works on synthetic only | 6 rules fire on `demo`; **0 high-risk on real** |
| 12 | Risk scores | 🟡 same cause as FR-11 | demo 3 high / 11 med / 75 low; real **0 high** |
| 13 | Mule-account signatures | 🟡 same cause as FR-11 | fires on `demo` only |
| 14 | Money-flow + comms graphs, drill-down | 🟢 works | 8,435 nodes on real data, HTTP 200 |
| 15 | Filter / search (entity, amount, time, location) | 🟡 partial | entity/amount/time yes; **location unverified** |
| 16 | Forensic report (PDF/Word) | 🟢 **works** | `POST /v1/report/{ds}` streams PDF (`%PDF`, 92,935 B) and DOCX (`PK`, 123,073 B); bad fmt → 400 |
| 17 | STR generation (bonus) | 🟡 reachable, content unreviewed | ships inside the report; the STR section itself has not been read against a real case |
| 18 | Risk heat maps (bonus) | 🔴 not implemented | zero matches anywhere in the codebase |
| 19 | Natural-language query (bonus) | 🟢 works | Gemini 6/6 planned; offline fallback; plain-text answers |

**9 green · 7 amber · 3 red** (was 8 / 7 / 4 at the start of the fix work).

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
| F1 | Calibrate detection thresholds + eligibility report | 11, 12, 13 | 🔵 **IN PROGRESS** — measuring real amount distribution vs the gates |
| F4b | Account↔phone bridge from complaint tables | 6, 10, 9 | **OPEN** — now off zero (1 entity), see below |
| F5 | Risk heat map | 18 | **OPEN** — genuinely absent from the codebase |
| F6 | IPDR row rejects (11 of 18) | 3 | **OPEN** |
| F7 | Location filter — verify or implement | 15 | **OPEN** |
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
