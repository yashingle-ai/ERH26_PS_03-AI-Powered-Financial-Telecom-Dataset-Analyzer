"""Fixed-width printed statement reader -> (text_lines, grid).

Measured need. On `fir-65-2024` the largest block of still-unrecognised rows was not the
complaint PDFs — it was `.txt`, 7,331 rows whose headers came out as `['Unnamed: 0']`.
`detect_format` maps `.txt` to csv, pandas finds no comma, and the whole statement becomes
one column, so no profile can match and every row is rejected.

These files are bank statements printed to text: space-aligned columns, no delimiter
anywhere. A real HDFC example, with the account in a free-text preamble above:

    Account No.    : 50200059660555
       19/07/21   CU1901494271SHIV CREATION        503851        19/07/21        30,000.00   30,000.00
       26/07/21   IMPS-120712183651-SIGNZY         120712183651  26/07/21             1.05   30,001.05
                  TECHNOLOGIES-HDFC-XXXXXXXX0774-ACCOUNT
                  VERIFICATION

Two structural facts drive the design:

  * column boundaries are only discoverable from the data itself — a character position
    that is blank on every record line is a separator. This is the same coherency argument
    Pytheas makes for CSV table discovery, applied one dimension down.
  * a record spans several lines. The narration overflows and its continuation lines have
    an empty date column. Treating them as separate rows loses the rest of the narration;
    dropping them as blank loses it too.

There is no column header row at all, so headers are synthesised positionally and the
columns are identified from their VALUES by `value_typer` — a date column is
`timestamp_start`, a mutually-exclusive pair of money columns is debit/credit. This is the
case the instance-level matcher exists for, and it cannot be done from names because there
are no names.
"""

from __future__ import annotations

import re
from pathlib import Path

#: A record begins with a date in the left margin. Used both to decide whether a text file
#: is a fixed-width statement at all and to separate records from their continuations.
_RECORD_START = re.compile(r"^\s{0,10}(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})(?:\s|$)")
#: A report banner, not a transaction: a date immediately followed by a clock. Bank of
#: Baroda prints `23-07-2025 18:20:58    BANK OF BARODA, SFS MANSAROVAR` at the top of every
#: page, and it begins with a date, so it matched `_RECORD_START` and became "record 1".
#: That put `first` at the banner, leaving no preamble to search and burying the real
#: two-line column header inside the record block — 1,500 rows classified on values alone.
_REPORT_BANNER = re.compile(
    r"^\s{0,10}\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\s+\d{1,2}:\d{2}(?::\d{2})?\b")

#: Delimiters that mean the file belongs to pandas, not here.
_DELIMITERS = (",", "\t", "|", ";")
#: Share of lines that must agree on a delimiter count before the file is called delimited.
_DELIMITED_SHARE = 0.7
#: A delimited file has at least two separators per line (three or more fields). Presence
#: alone is not enough: a printed statement writes amounts as `30,000.00`, so most of its
#: lines contain a comma and a presence test rejected genuine fixed-width statements.
#: What distinguishes a real CSV is that the count is CONSISTENT, and greater than one.
_MIN_DELIMS_PER_LINE = 2
#: Runs of two or more spaces are column alignment. A delimited file has none.
_ALIGNED_SHARE = 0.7
#: A table has several columns; one or two inferred spans is prose that happens to start
#: with a date.
_MIN_COLUMNS = 3

_MULTISPACE = re.compile(r"\S {2,}\S")
#: Record lines needed before the layout is worth inferring. Two lines cannot establish a
#: column boundary — every position they happen to share would look like a separator.
_MIN_RECORDS = 4
#: Consecutive blank character positions that constitute a column gap. A single space
#: occurs inside narration text; two or more is alignment.
_MIN_GAP = 2
#: Lines read when sniffing. Statements put their preamble first, so look past it.
_SNIFF_LINES = 400

#: A `Label : value` line. These are preamble, and a multi-page statement repeats its whole
#: preamble on every page — those repeats fall BETWEEN record lines, so without this test
#: they were coalesced into whichever transaction preceded them, producing a narration of
#: "Requestin SAHARA DA GROUND FL ... 174575519 502000596 REGULAR" and corrupting the row.
_LABELLED_LINE = re.compile(r"[A-Za-z]\s*:\s")
#: A narration continuation wraps into one or two columns. A line that puts text into many
#: columns at once is a repeated page header, not an overflow.
_MAX_CONTINUATION_COLUMNS = 3


#: Lines above the first record examined for a column-header block.
_HEADER_LOOKBACK = 14
#: A rule line drawn under or over the header — `-----` or `=====`.
_RULE_LINE = re.compile(r"^[\s\-=_]+$")
#: Header cells needed before a recovered header block replaces the positional names.
_MIN_HEADER_CELLS = 3


def _header_from_preamble(lines: list[str], first: int,
                          spans: list[tuple[int, int]]) -> list[str] | None:
    """Recover real column names from a header block above the first record.

    The original assumption — "there is no column header row at all" — held for the printed
    HDFC statement this reader was built for, but not generally. A Bank of Baroda
    "Customer Account Ledger Report" writes its header across two lines between rule lines:

        -------------------------------------------------------------------------
          GL.     Value       Instrmnt   Particulars      Transaction   Transac
          Date    Date         Number                    Debit Amount  Credit Am
        -------------------------------------------------------------------------
        02-04-2024  02-04-2024     62353 TO CASH          1,10,000.00

    Synthesising `column_0..N` there threw away `Particulars`, `Debit Amount` and
    `Credit Amount` — all existing profile aliases — leaving 1,500 rows of real transactions
    to be classified on values alone and reported as "header row not found".

    Returns None when no such block exists, so the positional fallback still applies.
    """
    collected: list[list[str]] = []
    for i in range(first - 1, max(first - 1 - _HEADER_LOOKBACK, -1), -1):
        line = lines[i]
        if not line.strip() or _RULE_LINE.match(line):
            continue
        # A `Label : value` line is preamble, not a column header, and reaching one means
        # the header block (if any) has been passed.
        if _LABELLED_LINE.search(line):
            break
        cells = _assign_words(line, spans)
        filled = [c for c in cells if c]
        # A header line spans the table. One or two cells is a stray note such as
        # "Order by GL. Date." sitting between the rule and the data.
        if len(filled) < _MIN_HEADER_CELLS:
            continue
        # Values, not labels — the record block has been reached.
        if _RECORD_START.match(line) or any(
                re.search(r"\d{2}[-/]\d{2}[-/]\d{2,4}|\d,\d{2,3}", c) for c in filled):
            break
        collected.append(cells)
        if len(collected) >= 3:
            break

    if not collected:
        return None
    collected.reverse()                      # restore top-to-bottom order
    merged: list[str] = []
    for col in range(len(spans)):
        parts = [row[col] for row in collected if col < len(row) and row[col]]
        merged.append(" ".join(parts).strip())
    if sum(1 for h in merged if h) < _MIN_HEADER_CELLS:
        return None
    return [h or f"column_{i}" for i, h in enumerate(merged)]


def _assign_words(line: str, spans: list[tuple[int, int]]) -> list[str]:
    """Assign each word of a header line to the column its midpoint falls in.

    Character slicing is right for data, which is aligned to the spans by construction, and
    wrong for headers, which are centred or right-aligned over their column and overhang it.
    Slicing produced `'lue te'` for `Value Date` and `'ransaction bit Amount'` for
    `Transaction Debit Amount` — names an analyst would read as corruption. Matching on the
    word midpoint tolerates the overhang.
    """
    cells = [""] * len(spans)
    for m in re.finditer(r"\S+", line):
        mid = (m.start() + m.end()) // 2
        for col, (a, b) in enumerate(spans):
            # widen slightly: a header word may sit just outside its column's data extent
            if a - 2 <= mid < b + 2:
                cells[col] = f"{cells[col]} {m.group()}".strip()
                break
    return cells


def _lines(path: str) -> list[str]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _record_lines(lines: list[str]) -> list[int]:
    return [i for i, ln in enumerate(lines)
            if _RECORD_START.match(ln) and not _REPORT_BANNER.match(ln)]


def looks_fixed_width(path: str) -> bool:
    """True when the file is a space-aligned statement rather than delimited text.

    Deliberately narrow. A Hikvision CCTV log in the same case folder is 11,275 lines of
    plain text and must NOT be dragged in here — its lines begin `User: admin Date:...`,
    not with a date in the left margin, so the record-start anchor excludes it.
    """
    try:
        lines = _lines(path)[:_SNIFF_LINES]
    except OSError:
        return False
    body = [ln for ln in lines if ln.strip()]
    if len(body) < _MIN_RECORDS:
        return False
    if _is_delimited(body):
        return False
    starts = _record_lines(lines)
    if len(starts) < _MIN_RECORDS:
        return False
    records = [lines[i] for i in starts]
    aligned = sum(1 for ln in records if _MULTISPACE.search(ln))
    if aligned < _ALIGNED_SHARE * len(records):
        return False
    # The record lines must share blank column positions, otherwise this is date-prefixed
    # prose rather than a table.
    return len(_boundaries(records)) >= _MIN_COLUMNS


def _is_delimited(body: list[str]) -> bool:
    """True when a delimiter appears a consistent, plural number of times per line."""
    for delim in _DELIMITERS:
        counts = [ln.count(delim) for ln in body]
        plural = [c for c in counts if c >= _MIN_DELIMS_PER_LINE]
        if not plural:
            continue
        mode = max(set(plural), key=plural.count)
        if counts.count(mode) >= _DELIMITED_SHARE * len(body):
            return True
    return False


#: Share of record lines that must be blank at a position for it to count as a column gap.
#: Requiring *every* line meant one malformed row collapsed two real columns: on a Bank of
#: Baroda ledger, 730 of 731 records separated the GL date from the value date by two spaces,
#: and the single exception merged them into `02-04-2024  02-04-2024`. That cell parses as
#: neither date, so `_norm_bank` dropped all 731 rows for "missing timestamp".
#: One bad row must not be able to destroy the layout for the rest.
_GAP_BLANK_SHARE = 0.98


def _boundaries(rows: list[str]) -> list[tuple[int, int]]:
    """Column spans, inferred from character positions blank in nearly every record line."""
    if not rows:
        return []
    width = max(len(r) for r in rows)
    threshold = max(1, int(len(rows) * _GAP_BLANK_SHARE))
    blank = [
        sum(1 for r in rows if i >= len(r) or r[i] == " ") >= threshold
        for i in range(width)
    ]

    spans: list[tuple[int, int]] = []
    start: int | None = None
    gap = 0
    for i in range(width):
        if blank[i]:
            gap += 1
            if gap >= _MIN_GAP and start is not None:
                spans.append((start, i - gap + 1))
                start = None
        else:
            if start is None:
                start = i - 0
            gap = 0
    if start is not None:
        spans.append((start, width))
    return [(a, b) for a, b in spans if b > a]


def _slice(line: str, spans: list[tuple[int, int]]) -> list[str]:
    return [line[a:b].strip() for a, b in spans]


def read(path: str) -> tuple[list[str], list[list[str]]]:
    """Return (preamble_text_lines, grid) — same contract as `parsers.pdf.read`.

    The grid's first row is synthesised positional headers; there is no header row in the
    source. The preamble is returned as text so `_extract_identity` can pull the account
    number and holder out of `Account No.    : 50200059660555`.
    """
    lines = _lines(path)
    starts = _record_lines(lines)
    if len(starts) < _MIN_RECORDS:
        return lines, []
    spans = _boundaries([lines[i] for i in starts])
    if not spans:
        return lines, []

    first, last = starts[0], starts[-1]
    preamble = [ln.strip() for ln in lines[:first] if ln.strip()]

    # Use the source's own column names when it has them; fall back to positional.
    header = (_header_from_preamble(lines, first, spans)
              or [f"column_{i}" for i in range(len(spans))])
    grid: list[list[str]] = [header]
    starts_set = set(starts)
    for i in range(first, min(last + 1, len(lines))):
        line = lines[i]
        cells = _slice(line, spans)
        if i in starts_set:
            grid.append(cells)
            continue
        if len(grid) <= 1 or not any(cells):
            continue
        if _LABELLED_LINE.search(line) or sum(1 for c in cells if c) > _MAX_CONTINUATION_COLUMNS:
            continue                     # repeated page header, not a wrapped narration
        # Continuation: the narration wrapped. Append each field's text to the record
        # above rather than emitting a fragment row (which has no date and is dropped)
        # or discarding it as blank (which loses the rest of the narration).
        prev = grid[-1]
        for c, cell in enumerate(cells):
            if cell:
                prev[c] = f"{prev[c]} {cell}".strip() if prev[c] else cell
    return preamble, grid
