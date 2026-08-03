"""Ingestion service — detect + parse a file into raw records with provenance (Phase 1).

Output is a ParsedFile: raw column->value records (not yet normalized) plus the detected
profile, a header-identity block (account holder/number for bank statements), and a reject
log. Normalization/entity-resolution (Phase 2) consumes this.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..core import config
from ..core.logging_config import get_logger
from . import detector, structure
from .parsers import archive, docx_tables, excel, fixed_width, html_tables, pdf, tabular

log = get_logger(__name__)


@dataclass
class ParsedFile:
    path: str
    format: str
    source_type: str | None
    profile_id: str | None
    confidence: float
    needs_manual_mapping: bool
    headers: list[str]
    records: list[dict] = field(default_factory=list)
    header_identity: dict = field(default_factory=dict)
    rejects: list[dict] = field(default_factory=list)
    #: Name of the archive this file was extracted from, if any (evidentiary chain).
    container: str | None = None
    #: Table index within a multi-table source (Word documents hold many).
    table_index: int = 0
    #: {header: {"target", "confidence", "type", "purity", "header_score"}} — columns
    #: mapped from their VALUES because no profile alias claimed them. Carried through to
    #: normalization, and surfaced so an analyst can audit every inferred mapping rather
    #: than discover that a column was interpreted on a guess.
    value_map: dict = field(default_factory=dict)

    @property
    def summary(self) -> dict:
        return {
            "file": Path(self.path).name,
            "path": self.path,
            "container": self.container,
            "table_index": self.table_index,
            "format": self.format,
            "source_type": self.source_type,
            "profile": self.profile_id,
            "confidence": self.confidence,
            "needs_manual_mapping": self.needs_manual_mapping,
            "headers": self.headers,
            "records": len(self.records),
            "rejects": len(self.rejects),
            "value_inferred": {h: s["target"] for h, s in self.value_map.items()},
        }


def _all_header_tokens() -> set[str]:
    tokens: set[str] = set()
    for plist in config.profiles().values():
        for profile in plist:
            for spec in profile.get("field_map", {}).values():
                tokens.update(a.strip().lower() for a in spec.get("aliases", []))
    return tokens


def _best_sheet(sheets: list[tuple[str, list[list]]]) -> list[list]:
    """Pick the sheet most likely to hold the data: best header-token match, else largest."""
    best, best_score = None, (-1, -1)
    tokens = _all_header_tokens()  # hoisted: rebuilding this per sheet re-walks every profile
    for _name, grid in sheets:
        hi = _find_header_row(grid)
        header = [str(c).strip().lower() for c in grid[hi]] if hi < len(grid) else []
        score = (sum(1 for c in header if c in tokens), len(grid))
        if score > best_score:
            best_score, best = score, grid
    return best if best is not None else sheets[0][1]


def _find_csv_header_row(lines: list[str]) -> int:
    """Locate the real header line in a CSV that may have a metadata preamble.

    Picks the early line whose comma-separated cells best match known field aliases
    (>=2 hits and >=3 columns). Returns 0 when there's no preamble.
    """
    tokens = _all_header_tokens()
    best_idx, best_hits = 0, 0
    for i, line in enumerate(lines):
        if line.count(",") < 3:
            continue
        cells = [c.strip().strip("'\"").lower() for c in line.split(",")]
        hits = sum(1 for c in cells if c in tokens)
        if hits > best_hits:
            best_hits, best_idx = hits, i
    return best_idx if best_hits >= 2 else 0


def _find_header_row(grid: list[list]) -> int:
    """Row index whose cells best match known field aliases (>=2 matches)."""
    tokens = _all_header_tokens()
    best_idx, best_hits = 0, 0
    for i, row in enumerate(grid[:40]):  # header is near the top
        hits = sum(1 for c in row if str(c).strip().lower() in tokens)
        if hits > best_hits:
            best_hits, best_idx = hits, i
    return best_idx if best_hits >= 2 else 0


def _bank_identity_aliases() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for profile in config.profiles().get("banks", []):
        for field_name, spec in profile.get("header_identity", {}).items():
            out.setdefault(field_name, [])
            out[field_name].extend(a.strip().lower() for a in spec.get("aliases", []))
    return out


def _is_numeric_identity_field(field_name: str) -> bool:
    return any(k in field_name for k in ("no", "number", "mobile", "phone"))


#: A country code on its own identifies nobody. Statements write mobiles as
#: "+91 8180934367", "+91-81809 34567" or "0 81809 34567", so a value is only kept
#: once it carries enough digits to be an actual identifier.
_MIN_IDENTITY_DIGITS = 6


def _clean_numeric_identity(value: str) -> str | None:
    """Strip separators from a numeric identity value, or None if it is too short."""
    compact = re.sub(r"[\s\-()]", "", str(value).strip())
    if len(re.sub(r"\D", "", compact)) < _MIN_IDENTITY_DIGITS:
        return None
    return compact


def _extract_identity(rows_above: list[list], text_lines: list[str]) -> dict:
    identity: dict = {}
    alias_map = _bank_identity_aliases()

    # (a) grid label/value pairs above the table header
    for row in rows_above:
        cells = [str(c).strip() for c in row]
        for j, cell in enumerate(cells):
            low = cell.lower().rstrip(":")
            for field_name, aliases in alias_map.items():
                if low not in aliases:
                    continue
                rest = [cells[k] for k in range(j + 1, len(cells)) if cells[k]]
                if not rest:
                    continue
                if _is_numeric_identity_field(field_name):
                    # A split cell ("+91" | "8180934367") yields the country code alone
                    # from the first non-empty cell, so join the row's tail and clean it.
                    value = _clean_numeric_identity("".join(rest))
                    if value:
                        identity[field_name] = value
                else:
                    identity[field_name] = rest[0]

    # (b) free text (PDF): "Account Number: 12345"  /  "Account Name: John Doe"
    joined = "\n".join(text_lines)
    for field_name, aliases in alias_map.items():
        if field_name in identity:
            continue
        # numeric identifiers (account no / mobile) capture digits; names capture words
        numeric = _is_numeric_identity_field(field_name)
        # A digits-only class stops at the first space, so "+91 8180934367" captured
        # "+91" — three of four real mobiles came out as the bare country code. Allow
        # internal separators and validate the digit count afterwards.
        value_pat = (r"(\+?\d[\d\s\-()]{4,24}\d|\+?\d+)" if numeric
                     else r"([A-Za-z][A-Za-z .]+?)")
        for alias in aliases:
            # `[.:\-\s]*` rather than `\s*[:\-]?\s*`: a printed HDFC statement writes
            # "Account No.    : 50200059660555", and the abbreviating period sat between
            # the alias and the separator, so the account never matched and every row of
            # an 85-transaction statement was rejected for having no account.
            m = re.search(rf"{re.escape(alias)}[.:\-\s]*{value_pat}(?:\s{{2,}}|\n|$| IFSC| A/C)",
                          joined, re.I)
            if not m:
                continue
            raw = m.group(1).strip()
            if numeric:
                cleaned = _clean_numeric_identity(raw)
                if not cleaned:
                    continue          # country code only — keep looking
                identity[field_name] = cleaned
            else:
                identity[field_name] = raw
            break
    return identity


def _dedupe_headers(headers: list[str]) -> list[str]:
    """Make header names unique so later columns don't overwrite earlier ones.

    A record is built as {header: cell}, so two columns sharing a name (common in real
    exports, which repeat a label or leave it blank) silently discard the first one's
    data. Repeats become "Name__2", "Name__3", …; blanks become "column_<i>" so they
    stay addressable. Profile matching is unaffected — it looks up known aliases, and
    the first occurrence keeps its original name.
    """
    seen: dict[str, int] = {}
    out: list[str] = []
    for i, h in enumerate(headers):
        name = h or f"column_{i}"
        if name in seen:
            seen[name] += 1
            name = f"{name}__{seen[name]}"
        else:
            seen[name] = 1
        out.append(name)
    return out


def columns_from_records(records: list[dict], headers: list[str]) -> dict[str, list]:
    """{header: [values...]} for value-based column typing.

    Capped: the typer samples a couple of hundred values per column, so materialising a
    million-row column to hand it 200 is waste on a 335 MB case folder.
    """
    limit = min(len(records), 400)
    return {h: [records[i].get(h) for i in range(limit)] for h in headers}


def _records_from_grid(grid: list[list], header_idx: int, base_prov: dict,
                       headers: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    if headers is None:
        headers = _dedupe_headers([str(c).strip() for c in grid[header_idx]])
    records, rejects = [], []
    blank = 0
    for r, row in enumerate(grid[header_idx + 1:], start=header_idx + 1):
        cells = [str(c).strip() for c in row]
        if not any(cells):
            blank += 1
            continue
        if all(not c for c in cells[:2]):  # likely a footer/blank continuation
            blank += 1
            continue
        rec = {headers[i]: (cells[i] if i < len(cells) else "") for i in range(len(headers))}
        rec["_provenance"] = {**base_prov, "row": r}
        records.append(rec)
    if blank:
        # Counted, not silent — but kept out of the mapping-failure reasons on purpose.
        # An empty layout row is not lost evidence, and lumping the two together made
        # `rejected_rows` read as a catastrophic gap when two thirds of it was padding:
        # one 1,909-row export was 1,268 blank rows. An investigator has to be able to
        # tell "we could not read this" from "there was nothing here".
        rejects.append({**base_prov, "reason": REASON_BLANK_ROW,
                        "rows": blank, "rejected": blank, "evidentiary": False})
    return records, rejects


def _read_grid(path: str, fmt: str) -> tuple[list[list], list[str]]:
    """Load the best grid for a grid-shaped format, plus any surrounding text lines."""
    if fmt == "xlsx":
        # B2: read all sheets, keep the one whose detected profile scores best
        # (falls back to the largest sheet) — avoids losing data on non-first sheets.
        sheets = excel.read_all_sheets(path)
        return (_best_sheet(sheets) if sheets else [[]]), []
    if fmt == "docx":
        return docx_tables.read_grid(path) or [[]], []
    if fmt == "html":
        text_lines, grid = html_tables.read(path)
        return grid or [[]], text_lines
    if fmt == "fixed":
        text_lines, grid = fixed_width.read(path)
        return grid or [[]], text_lines
    text_lines, grid = pdf.read(path)
    return grid, text_lines


def parse_file(path: str) -> ParsedFile:
    """Parse a file into a single ParsedFile (the best grid, for grid formats).

    Use `parse_file_multi` when a source can hold several independent tables.
    """
    fmt = detector.detect_format(path)
    if fmt != "csv":
        grid, text_lines = _read_grid(path, fmt)
        return _parsed_from_grid(path, fmt, grid, text_lines)
    return _parse_csv(path, fmt)


def _parse_csv(path: str, fmt: str) -> ParsedFile:
    """Delimited text. Unlike the grid formats, rows come straight from pandas."""
    # Real exports carry a metadata preamble before the real table — locate the header.
    preview = tabular.read_lines(path, config.max_preamble_rows())
    header_row = _find_csv_header_row(preview)
    df = tabular.read(path, skiprows=header_row)
    # pandas already disambiguates repeated CSV columns ("Name.1"), but stripping
    # whitespace here can collide them again — and a duplicate label makes row[c]
    # return a Series instead of a value, which breaks every downstream consumer.
    headers = _dedupe_headers([str(c).strip() for c in df.columns])
    df.columns = headers
    cap = config.max_rows_per_file()
    if len(df) > cap:                      # G1: cap + log (no silent truncation)
        log.warning("truncating %s: %d rows > cap %d", Path(path).name, len(df), cap)
        df = df.iloc[:cap]

    records = []
    for i, (_idx, row) in enumerate(df.iterrows()):
        rec = {c: row[c] for c in headers}
        rec["_provenance"] = {"source_file": Path(path).name,
                              "row": i + header_row + 2, "format": fmt}
        records.append(rec)

    identity = _extract_identity([], [])
    # bank CSVs carry identity inline; capture from first row if present
    if records:
        for key, col in (("account_no", "Account Number"),
                         ("account_holder", "Account Name"),
                         ("registered_mobile", "Customer Mobile"),
                         ("registered_mobile", "Registered Mobile"),
                         ("registered_mobile", "Mobile")):
            if col in records[0] and records[0][col]:
                identity[key] = records[0][col]

    det = detector.detect_profile(headers, columns_from_records(records, headers))
    profile = det.get("profile") or {}
    return ParsedFile(
        path=path, format=fmt,
        source_type=det.get("source"),
        profile_id=profile.get("profile", {}).get("id"),
        confidence=det.get("confidence", 0.0),
        needs_manual_mapping=det.get("needs_manual_mapping", True),
        headers=headers, records=records, header_identity=identity, rejects=[],
        value_map=det.get("value_map") or {},
    )


def _parsed_from_grid(path: str, fmt: str, grid: list[list], text_lines: list[str],
                      table_index: int = 0,
                      identity_rows: list[list] | None = None,
                      header_idx: int | None = None) -> ParsedFile:
    """Build a ParsedFile from a grid.

    `header_idx` is for callers that already KNOW where the header is. Geometry recovery
    hands over `[headers] + rows`, and re-detecting on that grid silently discarded every
    row above whatever `_find_header_row` picked instead. On one real statement it chose a
    repeated page header 11 rows down — because `_merge_header` had absorbed an opening
    balance into the true header (`Balance 40.00Cr`, 4 alias hits) while the page header was
    clean (`Balance`, 6 hits) — and 11 records with 10 transactions were dropped.
    """
    if header_idx is None:
        header_idx = _find_header_row(grid)
    headers = _dedupe_headers([str(c).strip() for c in grid[header_idx]]) if grid else []
    base_prov = {"source_file": Path(path).name, "format": fmt}
    if table_index:
        base_prov["table"] = table_index
    records, rejects = _records_from_grid(grid, header_idx, base_prov, headers) if grid else ([], [])
    # Records are built before detection so the detector can read the column VALUES, not
    # only the header strings. Values are what let an unfamiliar export be classified.
    det = detector.detect_profile(headers, columns_from_records(records, headers))
    # `identity_rows` lets a split section inherit the document's header block, which sits
    # above the first table and applies to all of them.
    identity = _extract_identity(
        grid[:header_idx] if identity_rows is None else identity_rows, text_lines)
    profile = det.get("profile") or {}
    return ParsedFile(
        path=path, format=fmt,
        source_type=det.get("source"),
        profile_id=profile.get("profile", {}).get("id"),
        confidence=det.get("confidence", 0.0),
        needs_manual_mapping=det.get("needs_manual_mapping", True),
        headers=headers, records=records, header_identity=identity, rejects=rejects,
        table_index=table_index, value_map=det.get("value_map") or {},
    )


#: Reason recorded for rows that were empty rather than unreadable. Kept distinct so
#: `rejected_rows` can be split into "we could not map this" and "there was nothing here".
REASON_BLANK_ROW = "blank / layout row (no content)"

#: A grid split into more sections than this is far likelier to be a mis-detected
#: header pattern than a document with that many stacked tables.
_MAX_GRID_SECTIONS = 40

#: A candidate header needs this many known-alias hits before it may split a table.
#: Two is enough for `_find_header_row`, which only has to pick the *best* row; here a
#: false positive severs a real table, so the bar is higher.
_SECTION_HEADER_MIN_HITS = 3


def _header_hits(row: list) -> int:
    tokens = _all_header_tokens()
    return sum(1 for c in row if str(c).strip().lower() in tokens)


def _norm_header(row: list) -> tuple[str, ...]:
    """Comparable form of a header row, for spotting a repeated page header."""
    return tuple(re.sub(r"\s+", " ", str(c)).strip().lower() for c in row if str(c).strip())


def _split_grid_sections(grid: list[list]) -> list[tuple[int, int]]:
    """Find stacked tables in one grid. Returns [(header_idx, end_idx_exclusive), ...].

    Real portal and complaint exports paste several unrelated tables into a single
    sheet. With one header row for the whole grid, every row below the second table's
    header is mapped against the wrong columns: on `fir-65-2024` an NCRP export put
    1,900 of 1,909 rows into "row missing timestamp / primary identifier", because the
    second table's serial-number column was being read as an account number.

    Conservative by design — a false split severs a genuine table, which is worse than
    leaving a section unrecovered. A row only starts a new section when it matches at
    least `_SECTION_HEADER_MIN_HITS` known aliases, is mostly non-numeric (headers are
    words), and has data under it.
    """
    if not grid:
        return []
    first = _find_header_row(grid)
    sections: list[int] = [first]
    for i in range(first + 1, len(grid) - 1):
        row = grid[i]
        cells = [str(c).strip() for c in row]
        if sum(1 for c in cells if c) < 2:
            continue
        if _header_hits(row) < _SECTION_HEADER_MIN_HITS:
            continue
        # Headers are labels, not values: require most filled cells to be non-numeric.
        filled = [c for c in cells if c]
        numericish = sum(1 for c in filled if re.fullmatch(r"[\d.,/:\-+₹\s]+", c))
        if numericish * 2 > len(filled):
            continue
        # A multi-page PDF statement repeats its column header on every page. Those are
        # continuations of one table, not new tables: splitting them fragments a single
        # statement into dozens of pieces and strands the account identity — which lives
        # only in the page-1 header block — away from every later page.
        if _norm_header(grid[i]) == _norm_header(grid[sections[-1]]):
            continue
        sections.append(i)
        if len(sections) >= _MAX_GRID_SECTIONS:
            log.debug("grid section cap reached; remaining rows stay in the last section")
            break
    bounds = []
    for n, start in enumerate(sections):
        end = sections[n + 1] if n + 1 < len(sections) else len(grid)
        if end - start >= 2:            # a header with no data row is not a table
            bounds.append((start, end))
    return bounds


def parse_file_multi(path: str) -> list[ParsedFile]:
    """Parse a file into one ParsedFile per mappable table.

    Two sources hold more than one table. A case .docx commonly holds dozens of small
    tables (one per account or subject) — a single grid per document silently dropped
    47% of the table rows in the real case data. Spreadsheet and PDF exports from the
    cybercrime portal stack several unrelated tables in one grid, which mapped the
    second table's columns onto the first table's headers.
    """
    fmt = detector.detect_format(path)

    if fmt == "docx":
        grids = docx_tables.read_all_grids(path)
        if not grids:
            return [parse_file(path)]
        return [
            _parsed_from_grid(path, "docx", grid, [], table_index=i + 1)
            for i, (_label, grid) in enumerate(grids)
        ]

    if fmt == "csv":
        return [_parse_csv(path, fmt)]  # pandas owns the row split; no grid to section

    grid, text_lines = _read_grid(path, fmt)
    sections = _split_grid_sections(grid)

    # Geometry recovery, only where the ordinary path demonstrably failed: a grid holding
    # several differently-shaped tables, or one whose best header row names a single column.
    # `pdfplumber` flattens every table on every page into one list of rows, which on
    # cybercrime-portal exports produced a 495-row grid yielding 0 usable records — the
    # transaction dates sat on continuation rows that were being discarded as padding.
    if len(sections) < 2 and structure.enabled() and structure.needs_recovery(grid):
        recovered = structure.regions_located(grid)
        if recovered:
            log.info("%s: recovered %d table region(s) from broken geometry",
                     Path(path).name, len(recovered))
            # The account/holder block sits above the first recovered table and identifies
            # the whole document. `[headers] + rows` drops it, and `_norm_bank` drops a row
            # with no account — the same hazard the stacked-table splitter already handles
            # by passing its preamble down.
            preamble = structure.document_preamble(grid, recovered)
            return [
                # header_idx=0: recovery already resolved the header, so re-detecting it
                # here can only lose rows above whatever gets picked instead.
                _parsed_from_grid(path, fmt, [headers] + rows, text_lines,
                                  table_index=i + 1, identity_rows=preamble,
                                  header_idx=0)
                for i, (headers, rows, _start) in enumerate(recovered)
            ]

    if len(sections) < 2:
        # ordinary one-table file — identical to parse_file, no behaviour change
        return [_parsed_from_grid(path, fmt, grid, text_lines)]

    # The account/holder/mobile block sits above the FIRST header and identifies the whole
    # document. Giving it only to section 1 strands every later section without an
    # account, and `_norm_bank` drops a row that has no account — so a split would have
    # cost transactions rather than recovering them.
    preamble = grid[:sections[0][0]]
    out: list[ParsedFile] = []
    for i, (start, end) in enumerate(sections):
        section = grid[start:end]
        out.append(_parsed_from_grid(path, fmt, section, text_lines,
                                     table_index=i + 1, identity_rows=preamble))
    log.info("%s: split into %d stacked tables", Path(path).name, len(out))
    return out


def _parse_one(p: Path, out: list[ParsedFile], pdf_cap: float, include_pdf: bool,
               origin: str | None = None, skipped: list[dict] | None = None) -> None:
    """Parse a single file into `out`. `origin` names the archive it came from, if any."""
    if p.suffix.lower() == ".pdf":
        # PDFs in real cases are mostly narrative/scanned (slow, no structured
        # tables). Opt-in, and skip huge ones even when enabled.
        if not include_pdf:
            if skipped is not None:
                _record_skip(skipped, p, container=origin,
                             reason="file not opened: PDF parsing disabled for this run")
            return
        size_mb = p.stat().st_size / 1e6
        if p.stat().st_size > pdf_cap:
            # Decide on content, not size. Both outcomes are recorded either way: an
            # over-cap PDF used to vanish behind a log line, which is 34 files and 292 MB
            # across the two cases — including `CA-3779 KYC FORM.pdf` and a 284-page bank
            # statement whose transactions were being discarded on file size alone.
            if pdf_has_text_layer(str(p)):
                log.info("over-cap PDF has a text layer, parsing anyway "
                         "(%.1fMB > %.0fMB cap): %s", size_mb, config.max_pdf_mb(), p.name)
            else:
                log.info("skipping scanned PDF, no text layer (%.1fMB > %.0fMB cap): %s",
                         size_mb, config.max_pdf_mb(), p.name)
                if skipped is not None:
                    _record_skip(
                        skipped, p, container=origin,
                        reason=f"file not opened: scanned PDF, no text layer "
                               f"({size_mb:.1f}MB over the {config.max_pdf_mb():.0f}MB "
                               f"cap) — needs OCR")
                return
    try:
        parsed = parse_file_multi(str(p))
    except Exception as e:  # per-file failure never aborts the batch (Doc 04)
        log.warning("failed to parse %s: %s", p.name, e)
        parsed = [ParsedFile(
            path=str(p), format=p.suffix.lstrip("."), source_type=None,
            profile_id=None, confidence=0.0, needs_manual_mapping=True,
            headers=[], records=[], header_identity={},
            rejects=[{"error": str(e), "file": p.name}],
        )]
    for pf in parsed:
        if origin:
            # Keep the evidentiary chain intact: a statement pulled out of bank.zip must
            # cite "bank.zip → statement.csv", not a temp path nobody can trace back to
            # the exhibit.
            pf.container = origin
            for rec in pf.records:
                prov = rec.get("_provenance")
                if isinstance(prov, dict):
                    prov["container"] = origin
                    prov["source_file"] = f"{origin} → {prov.get('source_file', p.name)}"
        out.append(pf)


def parse_directory(root: str, include_pdf: bool = True,
                    skipped_out: list[dict] | None = None,
                    on_progress=None) -> list[ParsedFile]:
    """Parse every supported file under a directory tree (bank/, cdr/, ipdr/).

    `include_pdf=False` skips PDFs entirely — use for large real-case folders where the
    structured data is in CSV/XLSX and PDFs are narrative/scanned.

    ZIP archives are expanded into a scratch directory and their contents parsed too — on
    real cases most structured evidence arrives sealed inside (often nested) archives.

    `on_progress(done, total, name)` is optional; called after each top-level path is
    handled so the API can stream a percent-complete bar.
    """
    out: list[ParsedFile] = []
    skipped: list[dict] = []          # used when the caller supplies no sink
    pdf_cap = config.max_pdf_mb() * 1024 * 1024
    archive_budget = int(config.max_archive_mb() * 1024 * 1024)
    scratch = Path(tempfile.mkdtemp(prefix="erakshak-archives-"))
    try:
        _walk(Path(root), out, pdf_cap, include_pdf, archive_budget, scratch,
              skipped if skipped_out is None else skipped_out,
              on_progress=on_progress)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return out


#: Extensions we knowingly cannot read. Separated from genuinely unexpected types so the
#: reject report can say "we know, and here is why" rather than listing them as mysteries.
_KNOWN_UNREADABLE = {
    ".doc": "legacy OLE2 Word — convert to .docx",
    # `.xml` in these cases is a response manifest, not data: it names the PDF that holds
    # the content (`ContentInfo: CAF`, `ContentFileName: 7201803066.pdf_DT_CAF_0.pdf`).
    # Parsing it as a table yields nothing, so it is skipped knowingly.
    ".xml": "response manifest, points to a PDF — no rows of its own",
    ".msg": "Outlook message container",
    ".eml": "email container",
    ".db": "database file, not a tabular export",
    ".onetoc2": "OneNote table of contents",
    ".emmx": "mind-map container",
}


#: Pages probed when deciding whether an over-cap PDF is scanned or has a text layer.
_PDF_TEXT_PROBE_PAGES = 2


def pdf_has_text_layer(path: str, pages: int = _PDF_TEXT_PROBE_PAGES) -> bool:
    """True when the first few pages yield extractable text.

    The size cap exists because large PDFs in real cases are usually scanned narrative that
    yields nothing. Size is a proxy for that, and it is a poor one: measured across the 15
    distinct over-cap PDFs in the two case folders, 14 are scans with zero extractable text
    — but one is a 284-page bank statement with 446,732 characters of text, 502 IFSC codes
    and real transactions, and it was being discarded on file size alone.

    Probing is cheap enough to replace the guess: 0.01-0.07s for a scan, 0.56s for the
    284-page statement. Uses pdfplumber, already a declared dependency, rather than adding
    PyMuPDF for this.
    """
    try:
        with pdf.pdfplumber.open(path) as doc:
            limit = min(pages, len(doc.pages))
            for i in range(limit):
                if (doc.pages[i].extract_text() or "").strip():
                    return True
    except Exception as exc:                      # noqa: BLE001 - unreadable == no text
        log.debug("text-layer probe failed for %s: %s", Path(path).name, exc)
    return False


def _record_skip(skipped: list[dict], path: Path, container: str | None = None,
                 reason: str | None = None) -> None:
    """Record a file the walker never opened.

    `_walk` only parses extensions in FORMAT_BY_EXT and previously dropped everything
    else with no trace at all — 125 files in one real case, 267 in the other. A row that
    fails to map is at least counted; a file that is never opened was invisible, so the
    system could not tell an investigator what it had not looked at. That is the worse
    failure of the two: it is unknowable from the output.
    """
    ext = path.suffix.lower()
    skipped.append({
        "file": f"{container} → {path.name}" if container else path.name,
        "container": container,
        "reason": reason or (
            f"file not opened: "
            f"{_KNOWN_UNREADABLE.get(ext, f'unsupported type {ext or chr(40)+chr(41)}')}"),
        "rows": 0,
        "rejected": 0,
        "file_skipped": True,
    })


def _content_key(path: Path) -> str | None:
    """SHA-256 of a file's bytes, or None if it cannot be read."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _walk(root: Path, out: list[ParsedFile], pdf_cap: float, include_pdf: bool,
          archive_budget: int, scratch: Path, skipped: list[dict],
          on_progress=None) -> None:
    # Real case folders carry the same exhibit in several places — one portal export
    # appeared three times across `fir-0006-2025-u`, and its 830 rows were parsed three
    # times. Event-level dedup catches the resulting duplicates afterwards, so the output
    # was never wrong, but the work was wasted and the reject and duplicate counts read as
    # far worse than the evidence actually is. The copy is recorded rather than ignored:
    # which exhibits are duplicated is itself part of the chain of custody.
    seen: dict[str, str] = {}
    paths = []
    for p in sorted(root.rglob("*")):
        if p.name.startswith("~$"):
            continue
        if p.name.startswith("._") or "__MACOSX" in p.parts:
            continue
        if not p.is_file():
            continue
        paths.append(p)
    total = max(len(paths), 1)
    for i, p in enumerate(paths):
        if p.suffix.lower() == ".zip":
            dest = scratch / f"{p.stem}-{abs(hash(str(p))) & 0xFFFFFF:06x}"
            for member in archive.extract_archive(
                str(p), dest,
                max_total_bytes=archive_budget,
                max_depth=config.max_archive_depth(),
                skipped_out=skipped,
            ):
                if member.suffix.lower() in detector.FORMAT_BY_EXT:
                    _parse_one(member, out, pdf_cap, include_pdf, origin=p.name,
                               skipped=skipped)
                else:
                    _record_skip(skipped, member, container=p.name)
        elif p.suffix.lower() in detector.FORMAT_BY_EXT:
            key = _content_key(p)
            if key is not None and key in seen:
                skipped.append({
                    "file": p.name, "container": None,
                    "reason": f"duplicate exhibit: byte-identical to {seen[key]}",
                    "rows": 0, "rejected": 0, "file_skipped": True, "duplicate_of": seen[key],
                })
            else:
                if key is not None:
                    seen[key] = p.name
                _parse_one(p, out, pdf_cap, include_pdf, skipped=skipped)
        else:
            _record_skip(skipped, p)
        if on_progress is not None:
            try:
                on_progress(i + 1, total, p.name)
            except Exception:  # noqa: BLE001 — UI progress must never abort ingest
                pass
