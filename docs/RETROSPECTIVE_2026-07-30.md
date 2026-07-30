# Engineering retrospective — ingestion recovery investigation, 29–30 Jul 2026

**Scope:** stop the pipeline losing files and rows, measured against two real case folders —
`FIR 65-2024` (2.0 GB) and `FIR-0006-2025 U` (2.1 GB).
**Commits:** `03fb24a`, `0aff17a`, `d534719`, `ad81349`, `67207f0`.
**Outcome:** +3,300 transactions, IP sessions ×60, one red requirement moved to amber, one
release-blocking regression introduced and closed, 73 new tests.

The uncomfortable headline: **of 23 hypotheses proposed, 13 were confirmed and 10 were
falsified — and 5 of the falsifications were faults in my own measuring instruments rather
than in the system under test.** Every genuine gain came from measuring a specific quantity;
none came from reasoning forward about where the problem ought to be. That pattern, not the
transaction count, is the useful output of this exercise.

---

## 1. Timeline

| Phase | Work |
|---|---|
| Research | Surveyed schema matching (Rahm & Bernstein taxonomy), value-based typing (Sherlock/Sato), structure detection (Pytheas), dead-letter patterns |
| Build 1 | `value_typer.py` — instance-level column typing |
| Measure 1 | Flag A/B: **+23 events**. Near-neutral. |
| Discover | `.html` absent from `FORMAT_BY_EXT` → Google legal-process files never opened |
| Build 2 | `html_tables.py` + `google_subscriber.yaml` → **IP_SESSION 69 → 4,133** |
| Build 3 | `fixed_width.py` — printed statements with no delimiter |
| Build 4 | `structure.py` — broken PDF grid geometry |
| **Regression** | FIR-0006 **−30,976 transactions** |
| Isolate | Four mechanisms predicted and falsified; flag added; two causes found and fixed |
| Still failing | −6,753 remained |
| Isolate again | Record-count probes were the wrong instrument; event-level probe found preamble loss |
| Close | All three acceptance criteria pass |
| Validate | Window sweep 1–60 min; detector semantics; coverage census |
| Study | `.vcf`, statutory identifiers, OCR — all negative |
| Fix | PDF size cap discarding a 284-page statement → **+1,066 transactions** |

---

## 2–4. Hypotheses: proposed, confirmed, falsified

### Confirmed (13)

| # | Hypothesis | Evidence |
|---|---|---|
| C1 | `.html` never opened because the extension was absent | IP_SESSION 69 → 4,133; FIR-0006 0 → 202 |
| C2 | Printed statements have no delimiter, so pandas yields one column | 7,331 rows in one `Unnamed: 0` column |
| C3 | `pdfplumber` flattens every page's tables into one grid | widths 2/9/11 in one grid |
| C4 | `Page Total` rows fragment run detection | one statement → **183 runs** |
| C5 | Spans without their own header block are discarded | **1 of 183** kept → 25 records |
| C6 | The document preamble is dropped, losing the account | 6,869 transactions → **0**, records intact |
| C7 | A non-finite cell raises `OverflowError` and zeroes a whole file | 11 CDR files, 118,510 rows |
| C8 | The register's `Mobile Number` is the officer's, not the holder's | 94/98 officers have 1 mobile; 10/32 accounts do |
| C9 | `detection/features` is primary-only | **15,098** entities with empty transaction vectors |
| C10 | MEDIUM hits never reach the risk model | `coincidence_count` = 0; `top_risk_score` flat at 54.3 across all windows |
| C11 | The size cap discarded a text-layer statement | 284 pages, 446,732 chars, **+1,066 transactions** |
| C12 | KYC scans carry Aadhaar, PAN and the registered mobile | observed directly on a PNB declaration |
| C13 | Duplicate exhibits are parsed repeatedly | 179 files / 108 MB on FIR-0006 |

### Falsified (10)

| # | Hypothesis | Why it was wrong |
|---|---|---|
| F1 | Instance-level typing recovers the bulk of unrecognised files | **+23 events of 246,353.** The residual is structure and correctly-refused tables, not unknown names |
| F2 | `_coalesce` over-merges a sparse first column | Coalescing was not involved |
| F3 | Insufficient row coverage explains the loss | **98.2%** of rows were inside accepted spans |
| F4 | Merged multi-row headers break profile aliases | Headers were clean and correct |
| F5 | Preamble = rows above the first *span* | The preamble itself spans two runs; `grid[:0]` |
| F6 | FR-9 STRONG is a window-calibration problem | **0 at every window from 1 to 60 min** |
| F7 | The FR-9 closure proof was complete | It covered only the IPDR files; a second IP source was never opened |
| F8 | `.vcf` is the highest value-per-effort item and targets FR-9 | Name is **not** a merge key — zero FR-9 impact |
| F9 | Statutory identifiers are the opportunity in text sources | 5 anchored Aadhaar, 30 PAN, 1 GSTIN → simulation merged **1** entity |
| F10 | All five `feats` rules are unreachable for counterparty-only entities | `layering`/`circular_flow` read `transfers`, which carries counterparty flows |

### Falsified because my instrument was wrong (5) — the important subset

| # | Claim | Actual fault |
|---|---|---|
| I1 | "xlsx/docx lose 1,906 records under recovery" | Probe ignored the `if recovered:` fallback. Real loss: **0** |
| I2 | "Criterion 1 PASSED" | Validated an **event**-count criterion with a **record**-count probe. A record survives intact while losing the column that made it mappable — exactly how C6 hid |
| I3 | "v3→v4 regression is attributable to geometry recovery" | Inferred from run timestamps; unprovable. Required a feature flag |
| I4 | "`files_never_opened` = 1,788 unread evidence tables" | 90% are photographs. Actionable: **47** files |
| I5 | "OCR extracted 0 of 6 fields, nothing detected" | My crop had a 17:1 aspect ratio, defeating the text detector. Corrected geometry recovered 9/10 digits of the phone |

---

## 5. Findings that produced measurable improvements

| Finding | Impact |
|---|---|
| `.html` never opened | **IP_SESSION 69 → 4,133 (×60)**; FR-3 red → amber |
| PDF size cap vs text layer | **+1,066 transactions**; 14 scans now named in the reject report |
| Fixed-width statements | **0 → 743 events** across both cases. *The "0 → 84" quoted in an earlier revision of this file is not reproducible and is withdrawn* |
| Broken grid geometry | complaint folder 14 → 389 events |
| Duplicate exhibits | 179 files / 108 MB not re-parsed; parse time **−38%** |
| `OverflowError` guard | 11 CDR files / 118,510 rows restored |
| Dr/Cr orientation from balance delta | every direction in one file was inverted |
| Non-IST profile guard | a rupee statement could have shifted 5.5 h and **manufactured** correlation hits |
| Officer-phone veto | prevented merging mule accounts into police entities |
| Reject-path composition | non-evidentiary rows measured at **42,761**, previously reported as 185 |

## 6. Effort spent for negative results

Worth recording — a measured negative is a real deliverable, and three of these prevented
work that would have been actively harmful.

| Investigation | Cost | Result | Was it worth it? |
|---|---|---|---|
| `value_typer` (~600 lines + tests) | High | **+23 events** | Marginal as a recovery tool. Justified only as the sole mechanism able to map a headerless statement or recovered region, and it surfaced 6 real defects |
| `.vcf` study | Low | 45 name↔phone pairs, **zero** FR-9 impact | Yes — stopped a feature justified on a false premise |
| Statutory identifier study | Medium | 1 entity merged | Yes — and it caught that Verhoeff alone yields **56,998** false Aadhaar candidates in CDR |
| OCR experiment | Medium | 0 of 7 fields exact | Yes — closed a large dependency decision with evidence |
| Reference-table linking | Low | Retracted before implementation | **Highest-value negative.** Would have fused mule accounts into police-officer entities |

---

## 7. Methodology lessons

**1. Count the quantity the acceptance criterion names.** Two probes counted records while
the criterion counted events. A record can survive intact while losing the column that made
it mappable, so a record-level "PASS" was evidence for nothing.

**2. Never attribute a change to code from run timestamps.** Add a flag, run both arms on one
build. `ERAKSHAK_VALUE_TYPING` and `ERAKSHAK_STRUCTURE_RECOVERY` exist because a
30,976-event delta could not otherwise be attributed.

**3. A non-empty result is not a correct result.** Recovery replaced a 10,027-row table with
25 records and the integration accepted it because the output was merely truthy.

**4. A safety invariant only guards what it measures.** The row-accounting check caught the
10,027 → 25 collapse and could not have caught the preamble loss, where every row survived
and only the identity was lost. State what an invariant does *not* cover.

**5. Validate the detector before trusting the study.** The GSTIN regex was off by one
character and matched nothing — including a GSTIN I had read with my own eyes. Verhoeff alone
admitted 1 in 10 UTRs. Both would have produced confident, wrong conclusions.

**6. A feature whose purpose is to stop losing data must not be able to lose data.** Value
inference is wrapped in a backstop that degrades to header-only matching on any exception.

**7. Judge a file by its content, not its container.** Twice: a size cap discarding a
284-page statement, and my own "non-actionable images" label over scanned bank KYC.

**8. Don't extrapolate from n=1** — and don't extrapolate from n=2 either, which is what the
"OCR will find the mobile" claim did.

**9. One case-scale job at a time.** Three concurrent passes exhausted memory and killed a
run with `MemoryError` in an unrelated function.

**10. Buffered pipes hide progress.** `| tail -N` withholds all output until exit; a 110-minute
probe was opaque throughout. Write to a file and flush.

---

## 8. Recommendations for future parser investigations

1. **Define the acceptance criterion as an event/row count before writing the probe**, then
   make the probe measure exactly that.
2. **Ship every new parse path behind an env flag** so it is A/B-able on one build and
   disable-able in the field without a revert.
3. **Add a non-destructiveness check at the integration point**, not only inside the new
   component: never accept a replacement path that accounts for less than the existing one.
4. **Baseline both cases before changing anything.** Single-case baselines hid that FIR-0006
   is 83% unrecognised against FIR 65-2024's 69%, and that its format mix differs.
5. **Report file coverage in categories, never as one number.** "2,571 never opened" pointed
   at 50× more work than the 47 files that were actionable.
6. **Unit-test identifier detectors against the adversarial neighbours** — UTRs for Aadhaar,
   dates for cell IDs, clocks for IPv6 — before running any corpus study.
7. **Prefer a declared dependency over a better one.** `pdfplumber` was already in
   `requirements.txt`; PyMuPDF was installed locally but absent from it, so using it would
   have broken the container build.
8. **Write the reject reason as the next action** — `"scanned PDF, no text layer — needs
   OCR"` names the work; `"skipped"` does not.

---

## 9. Work-item classification

| Item | Classification |
|---|---|
| `OverflowError` zeroing 11 CDR files | **Production bug** |
| Dr/Cr inverted on headerless columns | **Production bug** |
| Preamble discarded → 6,869 → 0 transactions | **Production bug** |
| Run fragmentation by `Page Total` rows | **Production bug** |
| Header-less spans silently dropped | **Production bug** |
| Over-cap PDFs dropped with no reject entry | **Production bug** (rule-2 violation) |
| `include_pdf=False` skips unrecorded | **Production bug** (rule-2 violation) |
| GSTIN regex off by one (study tooling) | **Production bug** (in tooling) |
| MEDIUM hits never reach the risk model | **Production bug** (latent; harmless while STRONG = 0) |
| `detection/features` primary-only semantics | **Design limitation** — documented, deliberately unchanged |
| `timeline_builder` primary vs correlator participant | **Design limitation** |
| No `AADHAAR`/`PAN`/`GSTIN` in the identifier model | **Design limitation** — measured as not worth extending |
| No `MESSAGE` event type (WhatsApp, 5,148 rows) | **Design limitation** / **Feature request** |
| Archive budget truncation not surfaced | **Design limitation** (rule-2, open) |
| `html_tables.py` + Google profile | **Architecture improvement** |
| `fixed_width.py` | **Architecture improvement** |
| `structure.py` geometry recovery | **Architecture improvement** |
| Content-hash duplicate detection | **Architecture improvement** |
| Text-layer-based PDF decision | **Architecture improvement** |
| Feature flags on both recovery paths | **Architecture improvement** |
| Inference backstop (degrade, never lose) | **Architecture improvement** |
| Officer-phone veto (`has_admin_role_columns`) | **Architecture improvement** (safety) |
| Non-IST profile guard | **Architecture improvement** (safety) |
| `value_typer.py` instance-level typing | **Feature request** delivered, **near-neutral** measured |
| `.vcf` reader | **Feature request** — deferred, attribution value only |
| OCR capability | **Feature request** — **closed, low priority** |
| FR-9 blocked on the account↔phone bridge | **Research finding** |
| `account+phone` = 3 is the guard working | **Research finding** |
| STRONG = 0 across a 60× window range | **Research finding** |
| Statutory identifiers scarce in text sources | **Research finding** |
| Verhoeff admits 1 in 10 UTRs | **Research finding** |
| 47 actionable unread files, not 2,571 | **Research finding** |
| `scripts/measure_ingestion.py` | **Measurement tooling** |
| `scripts/census_skipped.py` | **Measurement tooling** |
| Window sweep harness | **Measurement tooling** |
| Detector-semantics probe + participant simulation | **Measurement tooling** |
| Event-level loss probe | **Measurement tooling** |
| `docs/PARSER_COVERAGE.md` | **Documentation** |
| `PS_COMPLIANCE_AND_FIX_PLAN.md` §7 | **Documentation** |

---

## 10. Total measurable impact

### Recovered evidence — `FIR 65-2024`, W=10

| Metric | Before | After | Change |
|---|---|---|---|
| Transactions | 35,870 | **39,170** | **+3,300** |
| IP sessions | 69 | **4,133** | **×60** |
| Total events | 238,985 | **246,353** | +7,368 |
| Entities | 4,132 | **6,681** | +2,549 |
| `ACCOUNT_NO` identifiers | 549 | **3,022** | ×5.5 |
| Account **and** phone | 1 | **3** | +2 |
| `rejected_rows` | 140,040 | **118,836** | −21,204 |
| Rows stranded unrecognised | 23,846 | **16,307** | −32% |
| Parse time | 1,043 s | **646 s** | −38% |

`FIR-0006-2025 U` — first validated run: 456,423 events, 344,047 transactions, 202 IP
sessions (previously reported as a case with no IPDR at all).

### Defects fixed

**9 production bugs**, of which **3 silently corrupted evidence**: inverted transaction
directions, a UTC profile able to shift every timestamp 5.5 hours in a window-based
correlator, and an officer's phone becoming a subject identifier. All three are now pinned by
regression tests.

### Rules satisfied

- **Rule 2** (nothing dropped silently): over-cap PDFs, disabled-PDF skips, parse failures,
  blank rows and duplicate exhibits all now reach the reject report. **One violation remains
  open** — archive budget truncation.
- **Rule 3** (never fabricate an identity link): officer-phone veto added; reference-table
  linking retracted before implementation.
- **Rule 5** (do not redefine a headline metric): every new figure was added as a new field.

### Tests and tooling

**142 → 215 tests** (+73). Five new measurement tools, two repo-resident
(`scripts/measure_ingestion.py`, `scripts/census_skipped.py`) so every quoted ingestion figure
reproduces by command.

### Documentation

`docs/PARSER_COVERAGE.md` (new, 271 lines), `PS_COMPLIANCE_AND_FIX_PLAN.md` §7 (new, 240
lines) plus corrected scorecard rows, and this retrospective.

### Requirement movement

**9 green · 9 amber · 1 red** (from 9 / 8 / 2). FR-3 red → amber. FR-9 remains the only red,
and is now blocked on evidence rather than on code.

### Remaining open issues

| # | Issue | Size | Blocked on |
|---|---|---|---|
| 1 | FR-9 STRONG = 0 | — | 5 KYC rows from the case officer |
| 2 | Archive budget truncation not in the reject report | 1 archive, 1,079 MB | Small fix, rule-2 |
| 3 | WhatsApp `_chat.txt` | 5,148 rows | `MESSAGE` event type decision |
| 4 | Detector blind to counterparty-side transactions | 15,098 entities | New validation baseline |
| 5 | `_Doc_202404201542344604122.pdf` loses 10 of 125 events | 10 events | **Unexplained** |
| 6 | Legacy `.doc` reader | 42 files | No clean pure-Python reader |
| 7 | FIR-0006 full-pipeline run | — | Never executed; ingestion only |
| 8 | `files_never_opened` census vs pipeline disagreement | ±87 / −403 | Explained (nested archives, budget) but not reconciled to a single figure |

Item 5 is deliberately listed as unexplained rather than assumed benign: assuming a small
residual was harmless is precisely what produced the false PASS in §2 of this document.
