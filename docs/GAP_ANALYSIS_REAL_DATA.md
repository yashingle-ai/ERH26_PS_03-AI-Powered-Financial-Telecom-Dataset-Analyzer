
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
| **G4** | Password-protected archive members | counted at WARNING; set `ERAKSHAK_ZIP_PASSWORD` to unlock | [§1](#1-zip-archives-were-never-opened--92-of-them) |
| **G5** | **STRONG impossible on this evidence** (IPDR IDs nowhere else in case); MEDIUM=2 | STRONG closed-out; MEDIUM capped by account↔phone=0 | [Why STRONG is 0](#why-strong-fr-9-is-0--measured-closed-out-conclusion) |
| **G6** | PDF parsing is off by default, and that is where the bank evidence is | transactions ×3.3 when enabled | [§3](#3-financial-evidence-is-locked-in-pdf) |
| **G7** | Remaining bank rejects (timestamp/id after SOA recovery) | bank_generic still drops rows missing ts/id | [Bank reject recovery](#bank-reject-recovery--measured-2026-07-27) |
| ~~G7b~~ | ~~SOA PDFs scored as unrecognised (`Tran Particular`)~~ | **CLOSED** — 21,052 → 35,870 TXN; unrecognised rows → 0 | [SOA profile fix](#soa-pdfs--tran-particular-closed-2026-07-28) |
| ~~B8~~ | ~~Finacle `FORACID` / exchange `Time`+`User ID` / IPDR tab `.txt`~~ | **CLOSED** — see measured table below | [Bank reject recovery](#bank-reject-recovery--measured-2026-07-27) |
| ~~Q1~~ | ~~DSL: relative dates~~ | **CLOSED** — `relative_window` | [below](#known-limits-of-the-query-dsl--closed) |
| ~~Q2~~ | ~~DSL: absence/negation~~ | **CLOSED** — `having` | [below](#known-limits-of-the-query-dsl--closed) |
| ~~Q3~~ | ~~DSL: cross-entity comparison~~ | **CLOSED** — `group_must_include` | [below](#known-limits-of-the-query-dsl--closed) |
| ~~Q4~~ | ~~DSL: free-text search~~ | **CLOSED** — `any_text` field | [below](#known-limits-of-the-query-dsl--closed) |

**Highest value next:** raise **MEDIUM** via the account↔phone bridge
(`entity_map.csv` from KYC — in-case `registered_mobile ∩ CDR = 0`). SOA PDFs are
recovered. STRONG stays **evidence-blocked** (G5) until the case officer supplies the
archive password *and* unlocked CDRs contain the IPDR MSISDNs — or new IPDR arrives.

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

### Latest measured run — `fir-65-2024`, window 10 (2026-07-28)

| Metric | Before SOA fix | **After SOA `Tran Particular` (now)** | Δ |
|---|---:|---:|---:|
| Files | 930 | **930** | 0 |
| Events | 224,167 | **238,985** | +14,818 |
| **Transactions** | 21,052 | **35,870** | +14,818 |
| Calls | 203,046 | **203,046** | 0 |
| IP sessions | 69 | **69** | 0 |
| Entities | 4,131 | **4,132** | +1 |
| Transfers | 12,527 | **12,616** | +89 |
| Phone↔account bridges | 0 | **0** | 0 |
| **CDR phones ∩ IPDR phones** | **0** | **0** | 0 |
| Unrecognised source rows | ~58,416 | **0** | closed |
| Correlation hits | 0 STRONG / 2 MEDIUM | **0 STRONG / 2 MEDIUM** | 0 |

Expected before the SOA remeasure: TXN ≈ 36,379 (21,052 + 15,327 RBL SOA), MEDIUM = **2**,
STRONG = **0**. Got TXN **35,870** (duplicate SOA under `bank/` + `other/` deduped; 1 row
per copy still rejected for missing ts/id). MEDIUM stayed **2** as predicted — more bank
rows without an account↔phone bridge do not create new CALL+TXN entities inside W.

Independent re-derivation (paged `/v1/events`, not the correlator tally): CALL+TXN
anywhere **10**, within W=10 **2**, CALL+TXN+IP **0** — matches MEDIUM=2 / STRONG=0.

### First E2E run — `fir-0006-2025-u`, window 10 (2026-07-28)

Cold analyze ~60 min (1,504 files; graph 181k nodes). **No prior figures existed.**

| Metric | Measured |
|---|---:|
| Files | **1,504** |
| Events | **449,567** |
| Transactions | **337,393** |
| Calls | **112,174** |
| IP sessions | **0** |
| Entities | **2,742** |
| Transfers | **61,933** |
| Rejected rows | **327,987** (1,460 entries) |
| Unrecognised source rows | **0** |
| **STRONG** `correlation_hits` | **0** |
| **MEDIUM** `correlation_hits_medium` | **0** |
| High-risk entities | **2** |

STRONG cannot fire with **0** IP sessions. Independent bisect (paged events, not the
correlator tally): CALL+TXN anywhere **28**, within W=10 **0**, CALL+TXN+IP **0** —
matches MEDIUM=0 / STRONG=0. The 28 co-identity entities never land inside the same
10-minute window on this case.

Recovered bridges that were sitting unused in the case folder:

- **Common IMEI reports** → auto LINK events (PHONE↔IMEI).
- **IPv6 /64 enrichment** → IP-range host sessions inherit the TRAI MSISDN on the same /64.
- **CDR target IMEI** → IMEI/IMSI merge only when A-party is the report target (filename or `target_phone`).
- **G4** → `ERAKSHAK_ZIP_PASSWORD` / `ERAKSHAK_ZIP_PASSWORDS` tried on encrypted members
  (**7** zips, **31** locked members — no password set in `.env` yet).

**Tier (1.5.5):** `correlation_hits` stays STRONG-only (still **0**). MEDIUM call+txn
coincidences: **2** hits / **2** entities at W=10. G5 remains open until CDR∩IPDR > 0.

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
was handled per-member. Locked members are counted at WARNING; set
`ERAKSHAK_ZIP_PASSWORD` or comma-separated `ERAKSHAK_ZIP_PASSWORDS` to unlock them.

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
| Password-protected archive members | counted at WARNING | Set `ERAKSHAK_ZIP_PASSWORD(S)` |

---

## Bank reject recovery — measured 2026-07-27

**Baseline after `da97dd0`:** 18,721 of 20,033 bank rows still rejected (93%),
transactions stuck at 8,414, IPDR reported as 9/9 rejected.

Traced the worst files through `parse_file → map_record → _norm_bank/_norm_ipdr`
(not guessed). Three classes:

| Class | Worst file(s) | Rejected | Root cause | Fix |
|---|---|---:|---|---|
| Finacle/IndusInd bulk SOA | `statement bulk.xls` (inside GHOD DOD zip) | 6,975 | Account in `FORACID`, debit misspelled `DEDIT_AMOUNT`; timestamp was fine | Aliases on `bank_generic` |
| Exchange / P2P wallet ledger | `wallet_details__*.xlsx`, BNB reports | 6,683 | Timestamp in `Time`, subject in `User ID`, signed `Amount` — none mapped | `crypto_exchange_ledger` profile + signed-amount path in `_norm_bank` |
| Tab-separated IPDR range | `ipdr__1365.txt` | 9 | `pd.read_csv` defaulted to comma → one-column header → unrecognized source | `sep=None` delimiter sniff in `tabular.read` |

**Expectation before re-run:** recover ~13.6k bank rows from the first two classes;
IPDR txt should produce ~7 sessions (2 preamble rows are junk).

**Measured after rebuild + cold `/v1/analyze`:**

- Bank rejected **18,721 → 4,665** (−14,056)
- Transactions **8,414 → 20,999** (+12,585)
- Transfers **5,832 → 12,527** (+6,695)
- IP sessions **unchanged at 65** — the txt’s 7 real rows are the same sessions
  already present in `ipdr__1365.xlsx`, so A2 dedupe correctly drops them. The
  previous “9 of 9 IPDR rejected” was the unrecognized `.txt`; that file is now
  typed `IPDR` / `ipdr_iprange` with only the 2 preamble rows rejected.
- Correlation **still 0** — more transactions on the same accounts do not create
  the account↔phone bridge (G5). Entities only +12.

**Still open under G7:** the remaining 4,665 bank rejects are mostly complaint /
statement PDFs (`complain_gujarat_09__*.pdf`, Bandhan / Axis statement PDFs) —
a different class from the alias bugs above. Trace those next; do not re-tune
FORACID / Time aliases expecting further movement there.

Regression fixtures (synthetic shapes, no case data) live in
`backend/tests/test_real_data_ingestion_fixes.py`.

---

## Why STRONG (FR-9) is 0 — measured closed-out conclusion

**STRONG cannot fire on `fir-65-2024` because the IPDR identifiers are absent from the
rest of the case.** This is evidence, not a parser bug. Source-file search (stronger than
entity-level intersection):

| Identifier | Value | Hits under `cdr/` | Hits anywhere outside `ipdr/` |
|---|---|---:|---:|
| MSISDN | `7500107305` | **0** | **0** |
| MSISDN | `8535088505` | **0** | **0** |
| IMEI | `355330170920575` | **0** | **0** |
| IMEI | `358419296846579` | **0** | **0** |
| IMSI | `405870182224029` | **0** | **0** |
| IMSI | `405870182365083` | **0** | **0** |

Those six values exist **only inside IPDR files**. No amount of mapping/alias work will
create CALL+IP on one entity until IPDR for numbers that already appear in CDR is added,
or a locked archive is shown to contain those MSISDNs.

### Locked archives — precise statement

**7** password-protected archives, **31** encrypted members. **All seven are CDR or IMEI
exports — none is IPDR.**

```
CDR__1367__SP10024760.zip          CDR__4169__SP11102422.zip
CDR__6608__MSISDN_…tar.gz.zip      CDR__6857__SP9252797.zip
imei__6607__airtel__SP9086079.zip  imei__SP9045917.zip
upload__0065_soft_file__…zip
```

A password therefore adds **CDR/IMEI coverage, not IP sessions**. It can produce STRONG
only if an unlocked CDR happens to contain `7500107305` or `8535088505` — the one
hypothesis still untestable without the case officer’s password. Near-miss digit strings
in locked member names are **not** a lead.

**Action for the case officer:** supply `ERAKSHAK_ZIP_PASSWORD` (or
`ERAKSHAK_ZIP_PASSWORDS`). Everything else about STRONG on this case is blocked on
evidence, not code.

G5 remains **open** for STRONG until that evidence exists. MEDIUM (below) is a
mitigation, not the FR-9 fix.

### Mitigation: tiered correlation (MEDIUM)

| Tier | Rule | Summary field |
|---|---|---|
| **STRONG** | txn + call + IP in W | `correlation_hits` (unchanged meaning) |
| **MEDIUM** | txn + call in W, no overlapping IP | `correlation_hits_medium` (new) |

| Check | Result |
|---|---:|
| Correlator on smoke (STRONG) | hits ≥ 1 |
| Entities with ACCOUNT_NO + PHONE | **0** |
| Entities with CALL + TRANSACTION (any time) | **10** (UPI-phone bridge) |
| Those with CALL + TRANSACTION within W=10 | **2** |
| STRONG hits | **0** (evidence — § above) |
| MEDIUM hits (W=10) | **2** |

MEDIUM is capped by the missing account↔phone bridge: bank and telecom identities stay
separate entities except where UPI VPA mining already links a phone. Raising MEDIUM is
the productive code path while STRONG waits on evidence.

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
correlation.

### P1 census — account↔phone bridge (measured)

| Check | Result |
|---|---:|
| `registered_mobile` raw hits on bank PDFs | 10 files |
| …parseable to a 10-digit mobile | 5 |
| …mobile also present in CDR | **0** |
| In-case `entity_map` candidates (acct + mobile∩CDR) | **0** |
| Entities with ACCOUNT_NO | 388 (pre-SOA census) |
| Entities with PHONE | 8,141 (identifier count; resolved entities fewer) |
| Entities with ACCOUNT_NO **and** PHONE | **0** |
| UPI-phone counterparties driving CALL+TXN | all **10** of the anywhere-set |

`datasets/entity_map.template.csv` is still untried with **real KYC**. Filling it from
investigator CAF/KYC (account ↔ registered mobile that exists in CDR) is the only
remaining fast lever for MEDIUM. Case-derived header mobiles do not intersect CDR on
this folder.

### SOA PDFs — `Tran Particular` (CLOSED 2026-07-28)

Worst unrecognised file: `bank__RBL__409725898750-SOA.pdf` (15,327 rows). Headers were
real bank columns but `bank_generic` `required_any` lacked `tran particular` / debit /
credit / tran date, so `score_profile` returned **0** (`source=None`). Fix in
`config/profiles/banks/generic.yaml`. After rebuild+analyze the same file is
`source=BANK` / `profile=bank_generic` with **1** row rejected (missing ts/id).

### How to raise MEDIUM (and eventually STRONG)

1. **Supply `entity_map.csv`** (account ↔ registered mobile from KYC/CAF) — fastest lever;
   in-case registered_mobile cannot do it (∩ CDR = 0).
2. ~~Recover bank SOA / statement PDFs~~ — **done** for Finacle `Tran Particular` SOA.
3. **Ask the case officer for the archive password** — only then re-test whether IPDR
   MSISDNs appear in locked CDRs (STRONG hypothesis).
4. Until STRONG evidence arrives, use **MEDIUM** hits as two-leg investigative leads.
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
- `/v1/query/{ds}` returns `answer` (plain-text result composed locally), `engine`,
  `total`, `truncated`, and the generated **`spec`** so the analyst can audit exactly
  what ran. `explanation` describes the *plan*; `answer` answers the question.

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

### Known limits of the query DSL — closed

These four question shapes were **expressiveness gaps, not planner failures**: the model
produced the closest valid plan it could, and because the language had no way to say what
the question meant, the answer came back plausible and subtly wrong rather than refused.
That is the dangerous shape for a forensic tool, so all four were closed.

| # | Question shape | Was | Now | Verified on real data |
|---|---|---|---|---|
| Q1 | *"the day before the last transaction"* | Dropped the relative clause, returned **all** transactions | `relative_window` — anchor (`last_transaction`, `first_call`, …) + `offset_days` + `span_days`, resolved in a first pass against unfiltered events, then applied as a date range | Anchor resolved to 2025-03-01; window `2025-02-28 → 2025-03-01` returned 4 events |
| Q2 | *"numbers that stopped calling after August"* | Grouped and returned the **busiest** numbers — the opposite of the question | `having` — post-grouping conditions on `count` / `sum_amount` / `first_seen` / `last_seen` | `having last_seen <= 2024-08-31` returned **757** numbers on the 166k-event CDR corpus |
| Q3 | *"numbers that called both A and B"* | Not representable; the planner picked one side | `group_must_include` — keeps only groups whose events cover **every** listed value | Found exactly the caller who contacted both of two known numbers |
| Q4 | *"mentions X anywhere"* | `contains` searched one field only | `any_text` — a synthetic field concatenating narration, location, cell ID, IMEI/IMSI, IP, counterparty, label and source file | "Surat" matched 43,570 events across several fields |

**Planner behaviour is verified, not assumed.** Given the four questions in English, Gemini
selected the right construct each time (`relative_window`, `having`, `group_must_include`,
`any_text`) — see the live-run figures above.

**Auditability.** `/v1/query` returns the resolved `window`, any `skipped_blank` count, a
`note` when a query could not be answered as asked (e.g. no event to anchor to), and the
full `spec`. A relative-date answer is only trustworthy if the analyst can see which day it
actually resolved to.

**Still not expressible** (no current demand; record here if one appears): multi-hop graph
questions (*"who did the people who called A then pay?"*) and cross-dataset joins beyond
what entity resolution already merges.

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
