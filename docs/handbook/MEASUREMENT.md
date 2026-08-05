# Measurement — the protocol, and every current figure with its provenance

This is the part of the project that took longest to get right, and the part most likely to be
skipped. Three requirements went green by **re-measuring alone**, three claims were **withdrawn** as
unattributable, and one headline (FR-4) was measuring the wrong unit for weeks.

---

## 1. The protocol

**Re-measure before you fix.** The recorded figure is stale more often than not. It has been cheaper
than fixing something three times, which has happened.

**Count the quantity the criterion names.** A probe counted *records* while the criterion counted
*events*, and reported PASS. A record survives intact while losing the column that made it mappable,
so the counts diverge exactly where it matters.

**One variable per comparison.** Both arms same build, switched by an env flag. Two runs at different
times prove nothing about code — that inference was made once and withdrawn.

```bash
ERAKSHAK_BANK_REPLY_LINKS=0 python -m scripts.run_pipeline --input "$C" --save off.json
ERAKSHAK_BANK_REPLY_LINKS=1 python -m scripts.run_pipeline --input "$C" --save on.json
```

**Hold the dataset path fixed.** See `RUNBOOK.md` §7 — the same case at two paths gives identical
events and a different `files` count.

**Diff per entity, not per headline.** "3 fired" before and after can be a *different* 3. Dump one
row per entity from each arm and diff the rows; the headline hides substitutions.

**A non-empty result is not a correct result.** Recovery replaced a 10,027-row table with 25 records
and the integration accepted it because the output was non-empty.

**Say what did not move.** If a change moved nothing, that is the finding. Three claims here were
withdrawn for being unattributable or overstated and the docs say so — that is the norm, not an
embarrassment.

**A safety invariant only guards what it measures.** The row-accounting check caught a 10,027 → 25
collapse and could not have caught the preamble loss, where every row survived and only a column
went.

---

## 2. Current figures — staged paths, 31 Jul

### Ingestion

| | `fir-65-2024` | `FIR-0006-2025 U` |
|---|---|---|
| tables parsed | 961 | 1,305 |
| rows parsed | 364,747 | 749,421 |
| events | 247,492 | 456,328 |
| transactions / calls / IP sessions | 40,309 / 203,050 / 4,133 | 343,952 / 112,174 / 202 |
| entities (non-external) | 7,358 | 5,361 |
| transfers | 14,217 | 64,931 |
| rows claimed by a profile | **95.6%** | **97.8%** |

`calls` on `FIR-0006` has held at **112,174 across five builds** — the invariant used to detect
accidental ingestion changes. If it moves and you did not touch ingestion, something is wrong.

### Unclaimed tables, by reason (`unrecognised_by_reason`)

| reason | `fir-65-2024` | `FIR-0006-2025 U` |
|---|---|---|
| `out_of_scope_no_canonical_field` | 482 tbl / **13,315** rows | 640 tbl / 6,330 rows |
| `refused_officer_bearing` | 106 tbl / 787 rows | 337 tbl / **7,332** rows |
| `reference_no_time_anchor` | 83 tbl / 2,078 rows | 94 tbl / 3,102 rows |
| **`unread_parser_gap`** | **0 / 0** | **3 tbl / 92 rows** |

**The genuine parser gap is 3 tables and 92 rows — 0.008% of 1,114,168 rows parsed.** The biggest
single unclaimed table is an 11,275-row CCTV log, which is not Bank/CDR/IPDR.

*Caveat:* `unread_parser_gap` needs a canonical field **and** a column `value_typer._is_temporal`
recognises, so the 0 is bounded by that date coverage rather than proof of completeness.

### Rejected rows, by reason

| | `fir-65-2024` | `FIR-0006-2025 U` |
|---|---|---|
| total | 117,741 | 296,215 |
| duplicate events removed | 40,750 (34.6%) | 164,959 (55.7%) |
| row missing timestamp / identifier | 60,325 (51.2%) | 111,278 (37.6%) |
| unrecognised source type | 16,180 (13.7%) | 16,856 (5.7%) |
| blank / layout rows | 486 (0.4%) | 3,122 (1.1%) |

Duplicates and blanks are `evidentiary: False` — dropped, but **not a loss**. That middle row was one
reason hiding two and is now split into `no timestamp` (unrecoverable) and `has a timestamp but no
mapped primary identifier` (a mapping gap). **Nobody has yet measured the split on a real case** —
that is the open FR-1 number.

### Correlation — FR-9

| W | STRONG | MEDIUM (links off) | MEDIUM (links on) |
|---|---|---|---|
| 1 | 0 | 0 | **2** |
| 5 | 0 | 0 | **4** |
| 10 | 0 | 2 | **6** |
| 30 | 0 | 4 | **9** |
| 60 | 0 | 6 | **11** |

`fir-65-2024`, same build, flag as the only variable. **STRONG is 0 at every window.** The IP leg:
4,129 of 4,133 sessions carry an MSISDN (attribution is fine), but the IPDR covers **19 phones out of
4,026** in the CDR, and only 8 overlap. Three entities hold call+IP+transaction and in none of them do
the three fall within 60 minutes.

### Detection

| | `demo` | `fir-65-2024` | `FIR-0006-2025 U` |
|---|---|---|---|
| high / medium / low | 3 / 14 / 87 | 0 / 26 / 9,970 | 2 / 44 / 24,887 |
| top risk score | 92.5 | 54.2 | **85.5** |
| `account+phone` entities | — | **30** (was 2) | — |

`FIR-0006` reaching **85.5 on the identical unrescaled config** is what withdrew F1's threshold
calibration: the gates are not mis-tuned, `fir-65-2024` simply has no entity with enough typologies.

Ground truth on `demo` — scenario recall **15/15**. Entity-level, for the two rules that changed:

| rule | before | after |
|---|---|---|
| `call_transfer_coincidence` | precision 0.333, recall 0.500 | precision 0.200, **recall 1.000** |
| `rapid_in_out` | precision 0.107 | **precision 0.130**, recall 1.000 |

### Narrative documents

123 indexed, **39 prose-only**, 8 key-value forms. 469 accounts, 435 phones, 280 IFSC, 20 IMEI, 1
IMSI, 11 UPI. Plus **47 exhibits that were never delivered** — every unreadable `.docx` is exactly 162
bytes.

---

## 3. Figures that were withdrawn

Kept visible on purpose. A doc that only lists successes teaches nothing about how to work here.

| claim | why it went |
|---|---|
| "fixed-width: one file 0 → 84 events" | not reproducible; both files were at 0. Real figure 0 → 743 |
| "1,906 phantom record losses" | the probe ignored a `recovered` fallback. Real loss: 0 |
| "criterion 1 PASSED" | measured records where the criterion counts events — this is how the preamble bug hid |
| "the v3→v4 regression is caused by X" | attributed by run timestamp. Unprovable; a flag was added |
| F1 threshold calibration | premise weakened — the other case reaches 85.5 on the same config |
| "303 rows / 522 accounts / 223 mobiles" of KYC bridge | occurrence counts of digit runs incl. IFSC and e-mail digits, over duplicated tables. Deduplicated: **61 pairs, 47 accounts, 56 mobiles** |
| "up to 4 new STRONG candidates" | labelled an upper bound, realised as **0**. Holding all three event *types* says almost nothing about whether they fall inside the window |
| "halving MEDIUM's weight removes a band promotion" | it removes none — the same three entities cross either way |

---

## 4. Probe hygiene

Probes live in a scratch directory, **not** the repo — they hold real identifiers.

- `sys.stdout.reconfigure(encoding="utf-8")` at the top, always. Gujarati output to a cp1252 console
  raises `UnicodeEncodeError` mid-run and loses the results.
- `open(path, encoding="utf-8")` for reading your own JSON back. Default cp1252 fails on Gujarati.
- Mask identifiers in output: `f"{s[:2]}…{s[-2:]}({len(s)})"` is enough to tell two apart.
- Use `run_base()` when you do not need correlation/detection/graph — that is where the time goes.
- Anchor identifier regexes on a label. An unanchored 9–18 digit run in Gujarati prose is as likely to
  be a case number or a section citation as an account. The same reasoning put AADHAAR behind keyword
  anchoring: Verhoeff alone admits 1 in 10 UTRs and would have manufactured **56,998** false
  candidates in the CDR.
- Check your regex against a value you have already read. A GSTIN pattern was off by one character and
  matched nothing, including a GSTIN sitting in front of me; and an `IMSI` pattern that allowed only
  ASCII between the label and the digits reported **0** where the answer was 1, because the documents
  write `IMSI નં. 404…`.
