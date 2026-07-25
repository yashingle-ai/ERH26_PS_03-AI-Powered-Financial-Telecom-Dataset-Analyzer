"""Ingestion service — detect + parse a file into raw records with provenance (Phase 1).

Output is a ParsedFile: raw column->value records (not yet normalized) plus the detected
profile, a header-identity block (account holder/number for bank statements), and a reject
log. Normalization/entity-resolution (Phase 2) consumes this.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..core import config
from ..core.logging_config import get_logger
from . import detector
from .parsers import archive, docx_tables, excel, pdf, tabular

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


def _extract_identity(rows_above: list[list], text_lines: list[str]) -> dict:
    identity: dict = {}
    alias_map = _bank_identity_aliases()

    # (a) grid label/value pairs above the table header
    for row in rows_above:
        cells = [str(c).strip() for c in row]
        for j, cell in enumerate(cells):
            low = cell.lower().rstrip(":")
            for field_name, aliases in alias_map.items():
                if low in aliases:
                    value = next((cells[k] for k in range(j + 1, len(cells)) if cells[k]), "")
                    if value:
                        identity[field_name] = value

    # (b) free text (PDF): "Account Number: 12345"  /  "Account Name: John Doe"
    joined = "\n".join(text_lines)
    for field_name, aliases in alias_map.items():
        if field_name in identity:
            continue
        # numeric identifiers (account no / mobile) capture digits; names capture words
        numeric = any(k in field_name for k in ("no", "number", "mobile", "phone"))
        value_pat = r"(\+?\d[\d]*)" if numeric else r"([A-Za-z][A-Za-z .]+?)"
        for alias in aliases:
            m = re.search(rf"{re.escape(alias)}\s*[:\-]?\s*{value_pat}(?:\s{{2,}}|\n|$| IFSC| A/C)",
                          joined, re.I)
            if m:
                identity[field_name] = m.group(1).strip()
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


def _records_from_grid(grid: list[list], header_idx: int, base_prov: dict,
                       headers: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    if headers is None:
        headers = _dedupe_headers([str(c).strip() for c in grid[header_idx]])
    records, rejects = [], []
    for r, row in enumerate(grid[header_idx + 1:], start=header_idx + 1):
        cells = [str(c).strip() for c in row]
        if not any(cells):
            continue
        if all(not c for c in cells[:2]):  # likely a footer/blank continuation
            continue
        rec = {headers[i]: (cells[i] if i < len(cells) else "") for i in range(len(headers))}
        rec["_provenance"] = {**base_prov, "row": r}
        records.append(rec)
    return records, rejects


def parse_file(path: str) -> ParsedFile:
    fmt = detector.detect_format(path)
    text_lines: list[str] = []

    if fmt == "csv":
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
        det = detector.detect_profile(headers)
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
        rejects = []

    else:  # xlsx / pdf / docx -> grid
        if fmt == "xlsx":
            # B2: read all sheets, keep the one whose detected profile scores best
            # (falls back to the largest sheet) — avoids losing data on non-first sheets.
            sheets = excel.read_all_sheets(path)
            grid = _best_sheet(sheets) if sheets else [[]]
        elif fmt == "docx":
            grid = docx_tables.read_grid(path) or [[]]
        else:
            text_lines, grid = pdf.read(path)
        return _parsed_from_grid(path, fmt, grid, text_lines)

    profile = det.get("profile") or {}
    return ParsedFile(
        path=path, format=fmt,
        source_type=det.get("source"),
        profile_id=profile.get("profile", {}).get("id"),
        confidence=det.get("confidence", 0.0),
        needs_manual_mapping=det.get("needs_manual_mapping", True),
        headers=headers, records=records, header_identity=identity, rejects=rejects,
    )


def _parsed_from_grid(path: str, fmt: str, grid: list[list], text_lines: list[str],
                      table_index: int = 0) -> ParsedFile:
    header_idx = _find_header_row(grid)
    headers = _dedupe_headers([str(c).strip() for c in grid[header_idx]]) if grid else []
    det = detector.detect_profile(headers)
    base_prov = {"source_file": Path(path).name, "format": fmt}
    if table_index:
        base_prov["table"] = table_index
    records, rejects = _records_from_grid(grid, header_idx, base_prov, headers) if grid else ([], [])
    identity = _extract_identity(grid[:header_idx], text_lines)
    profile = det.get("profile") or {}
    return ParsedFile(
        path=path, format=fmt,
        source_type=det.get("source"),
        profile_id=profile.get("profile", {}).get("id"),
        confidence=det.get("confidence", 0.0),
        needs_manual_mapping=det.get("needs_manual_mapping", True),
        headers=headers, records=records, header_identity=identity, rejects=rejects,
        table_index=table_index,
    )


def parse_file_multi(path: str) -> list[ParsedFile]:
    """Parse a file into one ParsedFile per mappable table.

    Only Word differs from `parse_file`: a case .docx commonly holds dozens of small
    tables (one per account or subject), and each needs its own profile match — a single
    grid per document silently dropped 47% of the table rows in the real case data.
    Every other format yields exactly one.
    """
    if detector.detect_format(path) != "docx":
        return [parse_file(path)]

    grids = docx_tables.read_all_grids(path)
    if not grids:
        return [parse_file(path)]
    return [
        _parsed_from_grid(path, "docx", grid, [], table_index=i + 1)
        for i, (_label, grid) in enumerate(grids)
    ]


def _parse_one(p: Path, out: list[ParsedFile], pdf_cap: float, include_pdf: bool,
               origin: str | None = None) -> None:
    """Parse a single file into `out`. `origin` names the archive it came from, if any."""
    if p.suffix.lower() == ".pdf":
        # PDFs in real cases are mostly narrative/scanned (slow, no structured
        # tables). Opt-in, and skip huge ones even when enabled.
        if not include_pdf:
            return
        if p.stat().st_size > pdf_cap:
            log.info("skipping large PDF (%.1fMB > %.0fMB cap): %s",
                     p.stat().st_size / 1e6, config.max_pdf_mb(), p.name)
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


def parse_directory(root: str, include_pdf: bool = True) -> list[ParsedFile]:
    """Parse every supported file under a directory tree (bank/, cdr/, ipdr/).

    `include_pdf=False` skips PDFs entirely — use for large real-case folders where the
    structured data is in CSV/XLSX and PDFs are narrative/scanned.

    ZIP archives are expanded into a scratch directory and their contents parsed too — on
    real cases most structured evidence arrives sealed inside (often nested) archives.
    """
    out: list[ParsedFile] = []
    pdf_cap = config.max_pdf_mb() * 1024 * 1024
    archive_budget = int(config.max_archive_mb() * 1024 * 1024)
    scratch = Path(tempfile.mkdtemp(prefix="erakshak-archives-"))
    try:
        _walk(Path(root), out, pdf_cap, include_pdf, archive_budget, scratch)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return out


def _walk(root: Path, out: list[ParsedFile], pdf_cap: float, include_pdf: bool,
          archive_budget: int, scratch: Path) -> None:
    for p in sorted(root.rglob("*")):
        if p.name.startswith("~$"):        # Office lock/temp files
            continue
        # macOS writes an AppleDouble sidecar ("._name") beside every file, and a
        # __MACOSX/ mirror inside archives, when copying to a non-HFS volume. Evidence
        # handed over on a Mac-formatted drive is full of them. They carry no data but
        # share the real file's extension, so they were being parsed and counted as
        # per-file parse failures — noise that hides genuine ingestion problems.
        if p.name.startswith("._") or "__MACOSX" in p.parts:
            continue
        if not p.is_file():
            continue

        if p.suffix.lower() == ".zip":
            dest = scratch / f"{p.stem}-{abs(hash(str(p))) & 0xFFFFFF:06x}"
            for member in archive.extract_archive(
                str(p), dest,
                max_total_bytes=archive_budget,
                max_depth=config.max_archive_depth(),
            ):
                if member.suffix.lower() in detector.FORMAT_BY_EXT:
                    _parse_one(member, out, pdf_cap, include_pdf, origin=p.name)
            continue

        if p.suffix.lower() in detector.FORMAT_BY_EXT:
            _parse_one(p, out, pdf_cap, include_pdf)
