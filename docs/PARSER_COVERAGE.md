# Parser coverage — what gets read, what does not, and why

**Measured:** 30 Jul 2026, both real case folders.
**Reproduce:** `python -m scripts.census_skipped "datasets/FIR 65-2024" "datasets/FIR-0006-2025 U"`
and `python -m scripts.measure_ingestion --input "<case>"`.

This file answers one question an investigator is entitled to ask: *what did you not look
at?* Section 1 is the coverage count. Section 2 is what each reader does. Section 3 is the
remaining backlog, sized honestly.

---

## 1. Coverage

### 1.1 Headline

| | FIR 65-2024 | FIR-0006-2025 U |
|---|---|---|
| Files on disk (excl. macOS sidecars) | 993 | 3,654 |
| **Opened by a parser** | **613** | **1,463** |
| **Never opened** | **380** | **2,191** |
| Coverage by file count | 62% | 40% |

The raw coverage percentage is misleading on its own, which is the point of the next table.

### 1.2 Why files are not opened

`_walk` opens a file only if its extension is in `detector.FORMAT_BY_EXT`. Everything else is
recorded by `_record_skip` with a reason — nothing is dropped silently. Grouped by whether
the file could plausibly hold a table at all:

| Category | FIR 65-2024 | FIR-0006-2025 U | Actionable? |
|---|---|---|---|
| Non-tabular — image / media / system | 140 (37%) | **1,974 (90%)** | No |
| Container — holds other files | 214 (56%) | 125 (6%) | Contents already walked |
| **Potentially tabular, no reader** | **25 (7%)** | **22 (1%)** | **Yes** |
| Unknown / other | 1 | 70 | Review |

**The real backlog is 47 files across both cases, and 42 of them are legacy `.doc`.**

Everything else is `.jpg` (1,410 on FIR-0006 alone), `.tif` scans, `.opus` voice notes,
`.mp4`, `.heic`, `.vcf` contact cards, Outlook containers and shortcuts. Reporting "2,571
files never opened" as a single number would point effort at fifty times more work than
exists.

Actionable extensions, exactly:

```
FIR 65-2024      : .doc=21  .rpt=2  .odt=2
FIR-0006-2025 U  : .doc=21  .rpt=1
```

### 1.3 Files opened but not classified

Being opened is not the same as being understood. Of the tables parsed:

| | FIR 65-2024 | FIR-0006-2025 U |
|---|---|---|
| Tables parsed | 951 | 1,545 |
| Classified to a source type | 293 | 266 |
| **Unrecognised** | **658 (69%)** | **1,279 (83%)** |
| Rows stranded in unrecognised tables | **16,307** | **21,539** |

Diagnosed by row count, the unrecognised set is dominated by tables that are *correctly*
refused rather than by parser failures:

- **no time anchor** — complaint registers and account rosters. Real evidence, but they hold
  no timestamped events, so they cannot become `TRANSACTION`/`CALL`/`IP_SESSION` rows. One of
  them is the file whose `Mobile Number` column belongs to the investigating officer; see
  §7.10 of `PS_COMPLIANCE_AND_FIX_PLAN.md` for why linking it would manufacture evidence.
- **header row not found** — portal PDFs whose geometry is broken. Partly fixed (§2.7);
  residual cases remain.
- **no rows parsed** — the reader produced nothing (scanned image PDFs, empty sheets).
- **WhatsApp `_chat.txt`** — 5,148 rows of genuinely timestamped chat with no home in the
  canonical model. Blocked on a design decision, not on a parser.

### 1.4 Duplicates and archives

| | FIR 65-2024 | FIR-0006-2025 U |
|---|---|---|
| Duplicate exhibits (parsed once, recorded) | 21 | 179 |
| ZIP archives walked | 92 | 76 |
| Nested `.zip` members inside them | 96 | 31 |
| Total uncompressed archive content | 210 MB | **1,679 MB** |

Archives are expanded up to `max_archive_depth = 3` levels with a shared
`max_archive_mb = 512` uncompressed budget. On FIR-0006 one archive
(`WhatsApp Chat - Bhai.zip`, 1,079 MB) exceeds that budget on its own, so extraction stops
early inside it. **That truncation is logged but does not reach the reject report**, so it is
invisible in `/v1/data-quality`. Open issue — by the project's rule 2 it should be a reject
entry, not just a log line.

Password-protected members are skipped and counted: 32 members across 8 archives on
FIR 65-2024.

---

## 2. What each reader does

Pipeline order: `detect_format` → reader → structure recovery (if needed) → `detect_profile`
→ `map_record` → normalizer.

### 2.1 `detector.py` — format decision

Decides the reader from **leading bytes**, not the extension, because extensions lie
constantly in case material: `.xls` files that are really `xlsx`, `.xlsx` that are really
macOS AppleDouble stubs, `.xls` that are really fixed-width text reports.

| Magic | Meaning |
|---|---|
| `PK\x03\x04` | ZIP → xlsx or docx (extension breaks the tie) |
| `\xd0\xcf\x11\xe0` | OLE2 → legacy `.xls` (or a `.doc`, which fails cleanly as a per-file reject) |
| `%PDF` | PDF |
| `\x00\x05\x16\x07` | AppleDouble sidecar → rejected, not data |
| anything else | text → csv / html / fixed-width |

Supported extensions: `.xlsx .xls` → xlsx · `.csv .txt` → csv · `.pdf` → pdf · `.docx` → docx
· `.html .htm` → html.

### 2.2 `parsers/excel.py`

Reads **every sheet**, then `_best_sheet` keeps the one whose header row matches the most
known field aliases, falling back to the largest. Reading only the first sheet lost data on
workbooks where the statement sits on sheet 2.

### 2.3 `parsers/tabular.py` + `_parse_csv`

Delimited text via pandas. Two case-specific behaviours: a metadata preamble is skipped by
locating the real header line within the first 30 rows, and repeated column labels are
de-duplicated (`Name__2`) because a duplicate label makes `row[col]` return a Series and
breaks every downstream consumer.

### 2.4 `parsers/fixed_width.py` — **added 30 Jul**

Printed statements have **no delimiter**, so pandas returned the entire file as one
`Unnamed: 0` column — 7,331 rows on FIR 65-2024 producing nothing. Column boundaries are
inferred from character positions that are blank on every record line. These files have no
header row at all, so columns are identified from their values by the value typer.
Narration continuations merge into the record above; repeated page preambles are rejected
rather than folded into the preceding transaction.

Measured: one file 0 → 84 events, and its debit/credit ledger reconciles exactly.

### 2.5 `parsers/pdf.py`

`pdfplumber`, which is coordinate-aware and reconstructs ruled tables well for
digitally-generated statements. Returns both the text lines (used for header-block identity
extraction) and a flat table grid. Scanned/OCR PDFs are out of scope; PDFs above
`max_pdf_mb = 6` are skipped and recorded, because real cases carry large narrative scans
that hold no structured data.

### 2.6 `parsers/docx_tables.py`

Reads **all** tables in a document, not just the first. A case `.docx` commonly holds dozens
of small tables, one per account or subject; a single grid per document dropped 47% of table
rows.

### 2.7 `parsers/html_tables.py` — **added 30 Jul**

`.html` was absent from `FORMAT_BY_EXT`, so Google's responses to legal process were never
opened at all — 8 files on FIR 65-2024, 15 on FIR-0006. Each carries an IP ACTIVITY table of
timestamped logins plus the subscriber's own MSISDN and e-mail in a header block.

The subscriber's phone is denormalized onto every activity row, because only BANK normalizers
receive `header_identity`. 2-Step Verification numbers are deliberately excluded — they are
often a second person's handset. The profile declares `source_tz: UTC` because Google stamps
every value `Z`; read as IST each login would land 5.5 hours early and correlate against the
wrong window.

Measured: IP_SESSION 69 → 4,133 on FIR 65-2024, and 0 → 202 on FIR-0006, which had been
reported as having no IPDR at all.

### 2.8 `parsers/archive.py`

Recursive ZIP expansion, capped on depth (3), total uncompressed bytes (512 MB) and per-member
size. Path-traversal members (`../../etc/passwd`) are refused explicitly. Provenance is
preserved as `bank.zip → statement.csv` so an exhibit can be traced back.

### 2.9 `structure.py` — **added 30 Jul**

For grids whose geometry is broken. `pdfplumber` flattens every table on every page into one
row list, which on cybercrime-portal exports produced three faults at once:

1. **Mixed widths** — several unrelated tables concatenated, so one header was applied to all.
2. **Multi-row headers** — column titles split down six consecutive rows.
3. **Multi-row records** — one logical record spanning four or five physical rows, with the
   transaction date on a continuation row that `_records_from_grid` discarded as padding
   (954 of 2,485 rows in one folder).

Regions are found by run of raw cell count, with narrow page artifacts (`Page Total` rows)
transparent so they do not fragment a table. Headers are merged across rows and inherited
across page breaks. Recurring `Label: value` pairs embedded in cell text are promoted to real
columns — which yields names like `Txn Date` and `A/C No` that are already profile aliases.
Derived rows (`Page Total`, `Carried Forward`) are dropped.

Two safety properties, both learned the hard way:

- **Row accounting** — recovery returns nothing unless its regions account for at least half
  the grid's rows. Without it, a 10,027-row statement was replaced by 25 records and accepted
  because the result was merely non-empty.
- **Preamble preserved** — the account block above the first region is passed down as
  `identity_rows`. Losing it cost every one of 8,534 rows on one statement: `_norm_bank` drops
  a row with no account, so the file went 6,869 transactions → 0 with headers and records
  otherwise perfect.

Switchable with `ERAKSHAK_STRUCTURE_RECOVERY=0`.

### 2.10 `value_typer.py` — instance-level column typing

Types a column from its **values**, not its name: a column of `11DEC2019:09:07:02` is a
timestamp whether the bank calls it `Tran Date`, `Txn Dt` or nothing at all. Needed because
one exact-string alias vocabulary was gating six independent decisions, so a single unknown
spelling cascaded into a whole lost file.

Three signals, in order: a **value gate** (mandatory — nothing maps on a name alone), a
**fuzzy header tiebreak** with abbreviation expansion (`Withdrawal Amt.` reaches
`Debit Amount`), and a **one-to-one assignment** so two columns cannot claim the same target.

Honest sizing: on files that already have usable column names this is worth **+23 events**,
measured. It earns its place because it is the only mechanism that can map a headerless
fixed-width statement or a recovered region.

Guards, each closing a way it could manufacture rather than find evidence:

- a profile declaring a non-IST `source_tz` can never be claimed on values alone
- `match.required_all` stays a hard gate no fallback may bypass
- a phone column in a table carrying officer/designation columns can never fill a
  subject-phone target
- debit/credit orientation follows the balance delta, not column order
- inference failure degrades to header-only matching rather than losing the file

Switchable with `ERAKSHAK_VALUE_TYPING=0`.

---

## 3. Backlog, sized

| # | Item | Size | Blocked on |
|---|---|---|---|
| 1 | Legacy `.doc` reader | **42 files** | No clean pure-Python reader on Windows; `sniff_container` already detects OLE2 |
| 2 | `.rpt` / `.odt` | 5 files | Low value |
| 3 | WhatsApp `_chat.txt` | 5,148 rows | **Design decision** — no `MESSAGE` event type; mapping to `CALL` would put false call records into evidence |
| 4 | Residual broken-geometry PDFs | part of 9,792 rows on FIR-0006 | Further structure work |
| 5 | Archive budget truncation not in reject report | 1 archive, 1,079 MB | Rule-2 violation, small fix |
| 6 | `_Doc_202404201542344604122.pdf` loses 10 of 125 events | 10 events | **Unexplained** — recorded as such rather than assumed benign |
| 7 | Scanned/OCR PDFs | unknown | Out of scope by design (Doc 03) |

**Not backlog — correctly refused:**

- reference/roster tables with no timestamp (~4,000 rows). They hold no events, and the paths
  that would "recover" them fabricate identity links.
- images, video, voice notes, contact cards (~2,100 files). Not financial or telecom records.

---

## 4. How to re-measure

```bash
# coverage census — fast, no parsing
python -m scripts.census_skipped "datasets/FIR 65-2024" "datasets/FIR-0006-2025 U"

# ingestion metrics — reproduces every figure in §1.3
python -m scripts.measure_ingestion --input "datasets/FIR 65-2024" --save out.json

# isolate either recovery path
ERAKSHAK_STRUCTURE_RECOVERY=0 python -m scripts.measure_ingestion --input "<case>"
ERAKSHAK_VALUE_TYPING=0       python -m scripts.measure_ingestion --input "<case>"
```

Run one case at a time. Three concurrent case-scale passes exhausted memory and killed a run
with `MemoryError`.
