"""Table-region recovery for grids whose geometry is broken (FR-1, FR-4).

`pdfplumber.extract_tables()` returns every table on every page flattened into one list of
rows. On real cybercrime-portal exports that produces a grid the existing header/section
logic cannot read, and it is the largest remaining block of lost rows: ~4,000 on
`fir-65-2024` and ~9,000 on `fir-0006-2025-u`.

Three faults, all measured on `31107240106470.pdf` and `latest Cyber Police Portal.pdf`:

  1. **Mixed widths.** One grid held rows of width 9, 10, 11, 6 and 2 — several unrelated
     tables concatenated. A single header row for the whole grid maps the second table's
     columns onto the first table's names. The first 8 rows of that file are a complete,
     mappable NCRP transaction table (₹50,000-₹500,000 with clean dates and accounts) and
     they were lost purely because a differently-shaped table sat underneath them.

  2. **Multi-row headers.** The column titles are split down six consecutive rows —
     `Action Taken by Bank/`, then `(Wallet/PG/PA)`, then `Merchant`, then `Date of Action`.
     Reading any single row as the header misses most of the column names, which is how
     `_find_header_row` ended up choosing `['Complainant/ Victim Details View & Print']` —
     a one-cell page title — for a 830-row table.

  3. **Multi-row records.** One logical record spans four or five physical rows: the
     account continues on the next row, `Date: 03/06/2024` on the row after, `Layer : 2`
     after that. `_records_from_grid` discards rows whose first two cells are blank as
     layout padding — 954 of 2,485 rows in one folder, 38%, and the transaction date was
     in them.

The region boundary is a change in row width, and the record boundary is the key column
being populated. Both are structural facts about the grid rather than anything to do with
column names, which is what makes this work on an export nobody has written a profile for.

This runs only where the existing path demonstrably failed — see `needs_recovery` — so
files that already parse keep their current behaviour exactly.
"""

from __future__ import annotations

import os
import re


def enabled() -> bool:
    """Geometry recovery can be switched off with ERAKSHAK_STRUCTURE_RECOVERY=0.

    Present for the same reason `value_typer.enabled` is: it makes the two arms of a
    measurement run the same build, so a number that moves is attributable to this code
    and not to some other edit made in between. Attributing a 30,976-transaction change
    on `fir-0006-2025-u` from run timestamps alone proved impossible without it.
    """
    return os.environ.get("ERAKSHAK_STRUCTURE_RECOVERY", "1").strip().lower() not in (
        "0", "false", "no", "off")

#: Rows needed before a run of equal-width rows is treated as a table.
_MIN_REGION_ROWS = 3
#: Header cells needed before a recovered region is worth emitting.
_MIN_HEADER_CELLS = 2
#: Leading rows examined for a multi-row header block.
_MAX_HEADER_ROWS = 8
#: Distinct effective widths, each with this many rows, that mark a grid as glued.
_GLUED_MIN_ROWS_PER_WIDTH = 3

#: A row this much narrower than the grid's dominant width is a page artifact — a
#: per-page subtotal, a separator, a stray fragment — not the start of a different table.
#: Measured: `01-07-2022 to 31-12-2022.pdf` is 9,845 rows of raw width 8 with 184
#: `['Page Total','0.00','4890309.00']` rows of width 3 interleaved every ~54 rows.
#: Grouping on raw width alone shattered one table into 183 fragments.
_MINOR_WIDTH_RATIO = 0.6

#: Derived rows: a per-page or running subtotal, or a balance carried across pages. They
#: are not transactions, and emitting them as records injects rows with no timestamp.
_RE_DERIVED_ROW = re.compile(
    r"^\s*(?:page\s+)?(?:sub\s*)?total\b|^\s*grand\s+total\b|^\s*(?:opening|closing)\s+bal"
    r"|^\s*(?:carried|brought)\s+(?:forward|over)\b|^\s*b[/\\]?f\b|^\s*c[/\\]?f\b", re.I)

#: Share of a grid's non-empty rows that emitted regions must account for. A safety net
#: that does not depend on knowing which mechanism misbehaved: recovery replaced a
#: 10,027-row table with 25 records and the integration point accepted it because the
#: result was merely non-empty. Recovery must demonstrably account for the data or stand
#: aside and let the existing path run.
_MIN_ROW_ACCOUNTING = 0.5

_RE_DATEISH = re.compile(r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b")
#: A trailing Cr/Dr marker is part of the amount on Indian statements, so `40.00Cr` has to
#: read as a value. Without it, a header row carrying an opening balance was classed as a
#: label row and merged into the column names — `Balance 40.00Cr` — which then lost the
#: header-detection contest to a repeated page header and cost 11 records.
_RE_MONEYISH = re.compile(r"^\s*[-+(]?\s*(?:₹|rs\.?|inr)?\s*\d{1,3}(?:,\d{2,3})+(?:\.\d+)?"
                          r"\s*(?:cr|dr)?\)?\s*$|"
                          r"^\s*\d+\.\d{2}\s*(?:cr|dr)?\s*$", re.I)
_RE_SERIALISH = re.compile(r"^\s*\d{1,4}\s*$")
_RE_LONG_DIGITS = re.compile(r"\d{9,}")


def _cells(row: list) -> list[str]:
    return [re.sub(r"\s+", " ", str(c)).strip() for c in row]


def effective_width(row: list) -> int:
    """Row width ignoring trailing empty cells — the shape the table actually has."""
    cells = _cells(row)
    while cells and not cells[-1]:
        cells.pop()
    return len(cells)


def _looks_like_data(row: list) -> bool:
    """True when a row carries values rather than labels."""
    cells = [c for c in _cells(row) if c]
    if not cells:
        return False
    for c in cells:
        if _RE_DATEISH.search(c) or _RE_MONEYISH.match(c) or _RE_LONG_DIGITS.search(c):
            return True
    return False


def _is_label_row(row: list) -> bool:
    """True when a row's filled cells read as column titles rather than values."""
    cells = [c for c in _cells(row) if c]
    if not cells:
        return False
    if _looks_like_data(row):
        return False
    lettered = sum(1 for c in cells if any(ch.isalpha() for ch in c))
    return lettered * 2 >= len(cells)


def needs_recovery(grid: list[list]) -> bool:
    """True when the ordinary header/section path cannot read this grid.

    Deliberately narrow: recovery only runs on the two signatures actually measured, so a
    grid that already parses is never touched.
    """
    if len(grid) < _MIN_REGION_ROWS:
        return False

    # Raw cell count, matching `_runs`. Effective width was used here first and it fired on
    # perfectly clean spreadsheets: a statement with sparse debit/credit columns trims to a
    # different width on almost every row, so an ordinary xlsx looked like glued tables and
    # recovery degraded files that already parsed.
    widths: dict[int, int] = {}
    for row in grid:
        if effective_width(row) == 0:
            continue
        widths[len(row)] = widths.get(len(row), 0) + 1
    substantial = [w for w, n in widths.items() if n >= _GLUED_MIN_ROWS_PER_WIDTH]
    if len(substantial) >= 2:
        return True                      # glued tables of different shapes

    # A degenerate header: nothing in the first rows carries more than one label cell, so
    # whatever gets chosen names one column and orphans the rest.
    for row in grid[:_MAX_HEADER_ROWS]:
        if _is_label_row(row) and len([c for c in _cells(row) if c]) >= _MIN_HEADER_CELLS:
            return False
    return True


def dominant_width(grid: list[list]) -> int:
    """Widest raw cell count that appears on enough rows to be a real table shape."""
    counts: dict[int, int] = {}
    for row in grid:
        if effective_width(row):
            counts[len(row)] = counts.get(len(row), 0) + 1
    substantial = [w for w, n in counts.items() if n >= _GLUED_MIN_ROWS_PER_WIDTH]
    return max(substantial) if substantial else max(counts, default=0)


def _is_minor(row: list, dominant: int) -> bool:
    """True for a page artifact that must not be read as a table boundary."""
    return bool(dominant) and len(row) < _MINOR_WIDTH_RATIO * dominant


def _runs(grid: list[list]) -> list[tuple[int, int]]:
    """Maximal spans of consecutive rows sharing a raw cell count.

    Raw `len(row)`, not effective width. Effective width was the first attempt and it
    fragmented a single table into 118 runs: these grids are sparse, so a row of the same
    11-column table trims to width 6 or 2 depending only on which trailing cells happen to
    be empty. The raw count is the table's actual shape — the two real tables in
    `31107240106470.pdf` are exactly len 9 and len 11.

    Rows far narrower than the dominant width are transparent to the grouping. Treating
    them as boundaries was the first of the two defects that cost 30,976 transactions: a
    `Page Total` row every 54 rows split one 9,845-row statement into 183 fragments. They
    stay inside the span so `_coalesce` can decide what they are.
    """
    dominant = dominant_width(grid)
    spans: list[tuple[int, int]] = []
    start, current = 0, None
    for i, row in enumerate(grid):
        if effective_width(row) == 0:
            continue                     # wholly empty: belongs to neither side
        if _is_minor(row, dominant):
            continue                     # page artifact: neither starts nor ends a run
        w = len(row)
        if current is None:
            start, current = i, w
        elif w != current:
            spans.append((start, i))
            start, current = i, w
    if current is not None:
        spans.append((start, len(grid)))
    return [(a, b) for a, b in spans if b - a >= _MIN_REGION_ROWS]


def _merge_header(rows: list[list]) -> list[str]:
    """Join a multi-row header block into one name per column."""
    width = max((len(r) for r in rows), default=0)
    out: list[str] = []
    for c in range(width):
        parts = []
        for row in rows:
            cell = _cells(row)[c] if c < len(row) else ""
            if cell and cell not in parts:
                parts.append(cell)
        out.append(" ".join(parts).strip())
    return out


def _coalesce(rows: list[list], width: int) -> list[list[str]]:
    """Merge continuation rows into the record above, keyed on the first column.

    A record starts where column 0 is populated. Everything after it until the next such
    row belongs to it — that is where the transaction date lives on these exports.
    """
    out: list[list[str]] = []
    for row in rows:
        cells = _cells(row)
        cells += [""] * (width - len(cells))
        cells = cells[:width]
        if not any(cells):
            continue
        if cells[0] and _RE_DERIVED_ROW.match(cells[0]):
            continue                     # `Page Total`, `Carried Forward` — not a record
        if cells[0] or not out:
            out.append(cells)
            continue
        prev = out[-1]
        for c, cell in enumerate(cells):
            if not cell:
                continue
            prev[c] = f"{prev[c]} {cell}".strip() if prev[c] else cell
    return out


#: `Txn Date: 13/05/2024`, `A/C No.-:4292074819`, `Disputed Amount: 300000`, `Layer : 1`.
#: The portal writes these as labelled fields INSIDE a cell rather than as columns, so the
#: transaction date and the beneficiary account are invisible to any profile — the cell as
#: a whole types as narration. Promoting recurring labels to real columns turns an
#: unreadable table into a mappable one, and the labels it produces (`Txn Date`,
#: `A/C No.`) are already aliases in the bank profiles.
_EMBEDDED_FIELD = re.compile(
    r"([A-Za-z][A-Za-z0-9./]*(?:\s+[A-Za-z0-9./]+){0,3})\s*(?:-\s*:|:)\s*"
    r"(.{1,60}?)"
    r"(?=\s{2,}|$|\s+[A-Za-z][A-Za-z0-9./]*(?:\s+[A-Za-z0-9./]+){0,3}\s*(?:-\s*:|:))")
#: Label tokens kept. The full run before the colon swallows the preceding sentence —
#: `Money Transfer to Txn Date` — while the last two tokens give `Txn Date`, which is
#: already an alias for `timestamp_start` in the NCRP profile. Likewise `A/C No`.
_LABEL_TOKENS = 2
#: A label must appear on this many records before it becomes a column, so a stray colon in
#: free text does not invent one.
_MIN_LABEL_RECORDS = 2
#: Cap on promoted columns, to bound a pathological page of prose.
_MAX_PROMOTED = 12


def _promote_embedded_fields(headers: list[str], rows: list[list[str]]
                            ) -> tuple[list[str], list[list[str]]]:
    """Lift recurring `Label: value` pairs out of cell text into their own columns."""
    found: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    for row in rows:
        pairs: dict[str, str] = {}
        for cell in row:
            for label, value in _EMBEDDED_FIELD.findall(cell or ""):
                tokens = re.sub(r"\s+", " ", label).strip().split()
                key = " ".join(tokens[-_LABEL_TOKENS:]).rstrip(".").strip()
                value = value.strip().rstrip(",;").strip()
                if not key or not value or key.lower() in ("layer",):
                    continue
                pairs.setdefault(key, value)
        found.append(pairs)
        for key in pairs:
            counts[key] = counts.get(key, 0) + 1

    promoted = [k for k, n in sorted(counts.items(), key=lambda kv: -kv[1])
                if n >= _MIN_LABEL_RECORDS and k not in headers][:_MAX_PROMOTED]
    if not promoted:
        return headers, rows
    return (headers + promoted,
            [row + [pairs.get(k, "") for k in promoted]
             for row, pairs in zip(rows, found)])


def regions(grid: list[list]) -> list[tuple[list[str], list[list[str]]]]:
    """Recover (headers, rows) for each real table inside a broken grid."""
    return [(headers, rows) for headers, rows, _start in regions_located(grid)]


def document_preamble(grid: list[list],
                      located: list[tuple[list[str], list[list[str]], int]] | None = None
                      ) -> list[list]:
    """Rows above the first recovered table — the block carrying account and holder.

    A recovered region reaches `_parsed_from_grid` as `[headers] + rows`, which throws the
    preamble away. On one real Bank of Maharashtra statement that cost every one of 8,534
    rows: `Account No | 60532637196` sits sixteen rows above the column header, `_norm_bank`
    drops a row with no account, and the file went 6,869 transactions -> 0 while its headers
    and records were otherwise recovered perfectly.

    It must be the first region's start, not the first *span's* start. The preamble of that
    statement is itself split into two spans by width — `(0,6)` and `(6,16)` — before the
    table's span at `(16, 8555)`. Keying on the first span returned `grid[:0]`.
    """
    located = regions_located(grid) if located is None else located
    return grid[:located[0][2]] if located else []


def regions_located(grid: list[list]) -> list[tuple[list[str], list[list[str]], int]]:
    """`regions()` plus each region's starting row index in the original grid.

    Returns `[]` when recovery cannot account for the grid — the caller then leaves the
    existing path in place. That check is the reason this function can no longer lose data
    wholesale: it does not depend on correctly predicting which step misbehaved.
    """
    spans = _runs(grid)
    out: list[tuple[list[str], list[list[str]], int]] = []
    accounted = 0
    inherited: list[str] | None = None

    for start, end in spans:
        span = grid[start:end]
        width = effective_width(span[0])

        header_rows: list[list] = []
        idx = 0
        while idx < len(span) and idx < _MAX_HEADER_ROWS and _is_label_row(span[idx]):
            header_rows.append(span[idx])
            idx += 1

        if header_rows:
            headers = _merge_header(header_rows)
            headers = [h or f"column_{i}" for i, h in enumerate(headers[:width])]
            if sum(1 for h in headers if not h.startswith("column_")) < _MIN_HEADER_CELLS:
                continue
            inherited = headers
        elif inherited is not None:
            # A table continuing onto the next page does not repeat its header. Discarding
            # such a span was the second defect behind the 30,976-transaction loss: only 1
            # of 183 spans in one statement began with a label row, so 182 were dropped.
            headers = inherited
        else:
            continue

        rows = _coalesce(span[idx:], len(headers))
        if rows:
            promoted_headers, promoted_rows = _promote_embedded_fields(headers, rows)
            out.append((promoted_headers, promoted_rows, start))
            accounted += end - start

    non_empty = sum(1 for row in grid if effective_width(row))
    if non_empty and accounted < _MIN_ROW_ACCOUNTING * non_empty:
        return []
    return out
