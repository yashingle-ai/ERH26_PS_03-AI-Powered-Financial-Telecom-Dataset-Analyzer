
# Gap analysis — measured against the real case data

**Supersedes [`gap_analysis.md`](gap_analysis.md)**, which claims *"All identified items
remediated"* including B1/B4 and `.xls` support "via xlrd". That status was wrong: `xlrd`
was never in `requirements.txt`, `._` sidecars were not skipped, and vendor formats did
fall through. Those were fixed in `49cf77e` / `ad641f3`; the older document was never
updated and should not be used as a status source.

Everything below is **measured on `datasets/FIR 65-2024`**, not estimated. Commands to
reproduce are in [Reproducing these numbers](#reproducing-these-numbers).

---

## Open gaps — start here

Every unresolved item, in one place. Read this before picking up work; the sections below
give the evidence and the measurements behind each row.

| ID | Gap | Size / impact | Where |
|---|---|---|---|
| **G1** | Scanned evidence has no OCR | 58 images (+18 TIF in archives) | [§4](#4-still-open) |
| **G2** | Legacy `.doc` (OLE2) unreadable | 37 files | [§4](#4-still-open) |
| **G3** | Multi-section spreadsheets (several tables stacked in one sheet) | Binance-style exports | [§4](#4-still-open) |
| **G4** | Password-protected archive members | counted at WARNING; analyst holds the password | [§1](#1-zip-archives-were-never-opened--92-of-them) |
| **G5** | **Correlation returns 0** — only 1 phone↔account bridge exists | blocks FR-9, the flagship feature | [Why correlation still returns 0](#why-correlation-still-returns-0) |
| **G6** | PDF parsing is off by default, and that is where the bank evidence is | transactions ×3.3 when enabled | [§3](#3-financial-evidence-is-locked-in-pdf) |
| **Q1** | DSL: relative dates (*"day before the last transaction"*) | returns a plausible wrong answer | [Known limits of the query DSL](#known-limits-of-the-query-dsl--open) |
| **Q2** | DSL: absence/negation (*"stopped calling after August"*) | returns roughly the opposite of what was asked | [same](#known-limits-of-the-query-dsl--open) |
| **Q3** | DSL: cross-entity comparison (*"called both A and B"*) | not representable | [same](#known-limits-of-the-query-dsl--open) |
| **Q4** | DSL: free-text search across fields | single-field `contains` only | [same](#known-limits-of-the-query-dsl--open) |

**Highest value next:** G6 then G5 (an `entity_map.csv` is the fastest route to a non-zero
correlation count), then Q2 (smallest DSL change with the worst current failure mode).

**When you close one,** update its row and the measurement it cites — this file is only
useful while its numbers are true. The previous gap document rotted precisely because
fixes landed and its status was never revised.

---

## Headline

The system reported success while never seeing most of the case.

| Metric | Before | After ingestion fixes | After, with `include_pdf=True` |
|---|---:|---:|---:|
| Files parsed | 194 | **511** | **905** |
| Events | 142,526 | **203,663** | **204,911** |
| Entities | 2,116 | **4,138** | **4,144** |
| Phones resolved | 4,989 | **7,956** | **7,968** |
| **Transactions** | 552 | 552 | **1,800** |
| **Accounts resolved** | 131 | 131 | **168** |
| **Entities bridging phone↔account** | 0 | 0 | **1** |
| Correlation hits | 0 | 0 | 0 |
| Runtime | ~56 s | ~120 s | ~744 s |

Two things to read carefully:

- **Archives and Word tables recover telecom evidence, not financial evidence.** Phones
  nearly doubled; accounts did not move at all. The bank statements are in PDF.
- **PDF parsing is what recovers the financial side** — transactions ×3.3, and the first
  phone↔account bridge the case has ever produced. It costs ~6× runtime, which is why it
  is off by default; on a real case it should be **on**.

---

## What was wrong

### 1. ZIP archives were never opened — 92 of them

`parse_directory` walked the filesystem only. Sealed inside those archives:

| Inside the 92 archives | Count |
|---|---:|
| Structured files (56 CSV, 12 XLSX, 9 TXT, 6 XLS) | **83** |
| PDFs | 129 |
| Nested archives | 96 |

Nothing reported the omission — the files simply did not exist as far as the pipeline was
concerned. **Fixed:** `backend/app/ingestion/parsers/archive.py` expands archives
(recursively, depth-capped) into a scratch directory; 110 files now come from archives.

Extraction is defensive because archives are untrusted third-party input: recursion depth
cap, shared uncompressed-byte budget (zip-bomb guard), path-traversal refusal, and
per-member error isolation. **Password-protected archives are real in this case data** —
`zipfile` raises a bare `RuntimeError` for them, which crashed the entire pipeline until it
was handled per-member. Locked members are now counted and logged at WARNING, because the
analyst holds the password and can act on it.

Provenance survives the boundary: a record extracted from `bank.zip` cites
`bank.zip → statement.csv`, not a temp path.

### 2. Word documents: one table read, the rest discarded

`docx_tables.read_grid` returned only the largest table. Real case documents hold many
small tables — one per account or subject:

| | Count |
|---|---:|
| Documents with tables | 123 |
| Tables in them | **730** |
| Tables actually read | 123 |
| **Rows kept / discarded** | 2,890 / **2,540 (47%)** |

Worst offenders: `confidential nccrp 145- Copy.docx` (84 tables), `bank riports.DOCX` (84),
`CA report - for merge.docx` (78).

**Fixed:** `read_all_grids()` mirrors `excel.read_all_sheets` — the same fix made for
multi-sheet workbooks and never made for Word. `parse_file_multi()` emits one `ParsedFile`
per table so each gets its own profile match. 264 docx tables now parse.

### 3. Financial evidence is locked in PDF

Format census across the bank-related folders (`bank/`, `personal/`, `wallet details/`):

| Format | Count | Parsed? |
|---|---:|---|
| PDF | 48 | opt-in (`include_pdf`) |
| CSV | 30 | yes |
| ZIP | 25 | **now yes** |
| TIF | 22 | **no — needs OCR** |
| XLSX | 16 | yes |
| DOCX | 8 | yes |
| XLS | 1 | yes |

Sampling 14 bank PDFs: **12 have a real text layer with detectable tables**, 2 are scans.
They are parseable *today* — no OCR required. Enabling PDFs on the `bank/` folder alone
took it from 13 files / 0 transactions to **130 files / 807 transactions / 17 accounts**.

**Not a code gap — an operating-default gap.** `include_pdf=False` is the documented
default for real cases (chosen for speed), and it is exactly where the money is.
**Recommendation: run real cases with PDFs enabled** and accept the ~6× runtime.

### 4. Still open

| Gap | Size | Note |
|---|---:|---|
| OCR for scanned evidence | 58 images (+18 TIF inside archives) | Deferred deliberately: OCR'd financial figures need a confidence gate before entering a forensic timeline |
| Legacy `.doc` (OLE2) | 37 files | `python-docx` cannot read them; correctly detected and cleanly rejected, not silently dropped |
| Multi-section spreadsheets | Binance-style exports | Several tables stacked in one sheet (KYC block, then ledgers); single-header parsing rejects cleanly rather than emitting garbage |
| Password-protected archive members | counted at WARNING | Analyst supplies the password |

---

## Why correlation still returns 0

**This is not a correlator bug.** A hit requires one entity holding a transaction *and* a
call *and* an IP session. The identifier census explains why that cannot happen:

| Entity shape | Before | After (with PDFs) |
|---|---:|---:|
| Phone only | 4,987 | 7,967 |
| Account only | 131 | 167 |
| **Both (bridgeable)** | **0** | **1** |

Bank statements are keyed by account number, CDR/IPDR by phone. Nothing in the raw exports
links them. Progress is real — the first bridge now exists — but one bridged entity, with
only 65 IP sessions in the whole case, is not enough for the triple to land.

### The LLM-vs-system experiment

**Question:** the system finds no account↔phone relationship. Can an LLM reading the same
case folder find one the rule-based pipeline cannot?

**Method:** mined all 730 Word tables for rows containing exactly one phone and one account
(an unambiguous 1:1 pairing), then intersected against the entities the pipeline resolved.

| | Result |
|---|---:|
| Documents containing both phones and accounts | 19 |
| Naive cross-product pairs | 1,165 |
| High-confidence 1:1 pairs | **33** |
| …whose phone exists in ingested data | 7 |
| …whose account exists in ingested data | **0** |
| **…that would create a working bridge** | **0** |

**Result: negative, and that is the useful finding.** Document mining does *not* rescue
correlation. The 33 mined accounts are complaint/fraud accounts from NCRP registers — not
the accounts whose statements were obtained. The intuition "the mapping is written down in
the FIR, the rule-based system just can't read prose" is **wrong**, and acting on it would
have wasted effort on a document-mining feature that recovers nothing.

The bridge is missing because the statements were not ingested, not because nobody recorded
the mapping. That is why evidence recovery had to come first.

### How to actually light up correlation

1. **Run with PDFs enabled** — the only change that moved the account count.
2. **Supply the KYC map.** Investigators hold CAF/registered-mobile data. Drop an
   `entity_map.csv` in the case folder (see `datasets/entity_map.template.csv`); the merge
   mechanism is built and unit-tested (`test_bridge.py`). This is the intended path and the
   fastest route to a non-zero hit count.
3. **OCR the scanned statements** to recover the remaining accounts.

---

## Natural-language query

### Before

Five hardcoded regex intents. Measured against the real corpus (118,443 events):

| Question | Answered |
|---|---|
| `transfers over 100000` | yes |
| `high risk entities` | yes |
| `calls to 9702000558` | yes |
| `events on 2024-08-01` | yes |
| `transfers within 10 minutes of a call` | yes |
| **who did 9702000558 call most often?** | **no** |
| **show me calls between 2am and 5am** | **no** |
| **which numbers used the same IMEI?** | **no** |
| **what happened the day before the last transaction?** | **no** |
| **list numbers that stopped calling after August** | **no** |
| **who are the top 5 contacts of the main suspect?** | **no** |
| **find calls longer than 10 minutes** | **no** |
| **which towers did the suspect use in Surat?** | **no** |

**5/5 canned phrasings, 0/8 real questions.** It also silently capped results at 200 rows
with no indication.

### After — LLM → validated DSL

The failing questions are *structural*: they need aggregation over 200k events. Vector
retrieval (RAG) cannot do that, so RAG is **not** the right primary mechanism here.

```
question ─► Gemini (schema vocabulary only) ─► QuerySpec (validated) ─► local executor ─► rows
                                                      │
                                         no key / not planned
                                                      └──► rule-based fallback
```

- `backend/app/search/dsl.py` — closed query language (enum fields and operators, no free
  text, no SQL) plus a pure-local executor. Always reports `total` alongside `rows`, so
  truncation is visible.
- `backend/app/search/llm_planner.py` — the only module that calls an external API.
  Verified live: **8/8** of the previously-unanswerable questions now produce a correct
  plan, and 6/6 execute end-to-end against the real 166k-event CDR corpus.
- `/v1/query/{ds}` returns `engine`, `total`, `truncated`, and the generated **`spec`** so
  the analyst can audit exactly what ran.

**Data handling (research/10 SR-R4).** Backed by the Google Gemini API on a free-tier
Flash-Lite model — planning one question into a small enum-constrained object is an easy
task, so a larger tier buys nothing. The model receives the question plus the field
vocabulary. It never receives case records. `_assert_no_case_data` enforces this at the
boundary — it rejects oversized, multi-line, and delimited payloads — and is covered by
tests, including one asserting a legitimate question containing a phone number still
passes. With no API key the endpoint falls back to the offline interpreter, so an
air-gapped deployment keeps working.

**RAG remains the right answer for the narrative documents** (FIR, charge sheets, CA
reports) — "what does the charge sheet say about X". That requires sending case text to an
external service and is gated on revisiting the data-governance decision. Recorded here as
a follow-on, not built.

### Known limits of the query DSL — open

These are **DSL expressiveness gaps, not planner failures**. The model produces the closest
valid plan it can; the language has no way to say what the question means, so the answer
comes back plausible and subtly wrong rather than refused. That is the dangerous shape, so
each one is listed with what it would take to close it.

| # | Question shape | What happens now | What it needs |
|---|---|---|---|
| Q1 | **Relative dates** — *"the day before the last transaction"*, *"the week after the FIR"* | Plans `event_type=TRANSACTION` and drops the relative clause. Returns all transactions, not the ones on that day | An anchor concept: `relative_to` (`first_event`/`last_event`/a literal date) plus an offset, resolved by the executor after the anchor is computed. Cannot be a plain filter — the value depends on the result set |
| Q2 | **Absence / negation over time** — *"numbers that stopped calling after August"*, *"accounts with no activity since March"* | Plans `group_by=phone` over all calls. Returns the busiest numbers — arguably the opposite of what was asked | A `having` clause over grouped buckets (e.g. `max(timestamp) < X`). The filter must apply *after* grouping; today filters only run before it |
| Q3 | **Cross-entity comparison** — *"numbers that called both A and B"* | No representation; the planner picks one side | Set intersection across two grouped result sets |
| Q4 | **Free-text search over narration** | `contains` works on a single field only | Full-text index across narration/location/label, or the RAG path above |

Q1 and Q2 were both observed live against the real case. Q3 and Q4 are known-missing rather
than observed.

**Guidance until these close:** the endpoint returns the generated `spec`, so an analyst can
see the query actually run. Any answer to a question of the shapes above should be checked
against that spec before it is relied on — the plan will look reasonable while omitting the
part that mattered.

**Suggested order.** Q2 (`having`) is the highest value and the smallest change — it is a
post-grouping filter pass in `_grouped`. Q1 needs a two-phase execute (resolve anchor, then
filter) and touches the schema. Q3 and Q4 are larger and should wait for a real need.

---

## Reproducing these numbers

```bash
# Headline pipeline metrics (add --window to vary W)
python scripts/run_pipeline.py --input "datasets/FIR 65-2024"

# With the financial evidence included (~12 min)
python - <<'PY'
from backend.app import pipeline
inv = pipeline.run_base("datasets/FIR 65-2024", include_pdf=True)
pipeline.apply_analysis(inv, 10)
print(inv.summary())
PY

# Regression suites for every fix above
pytest backend/tests/test_real_data_ingestion_fixes.py backend/tests/test_nl_query_dsl.py -q
```

**Data safety.** All of this runs against case data that must never be committed.
`datasets/` is deny-by-default in both `.gitignore` and `.dockerignore`; archive extraction
writes to a temp directory that is removed on completion. After any run,
`git status --porcelain | grep -Ei 'FIR|\.zip|erakshak\.db'` must return nothing.
