"""Ingestion service — detect + parse a file into raw records with provenance (Phase 1).

Output is a ParsedFile: raw column->value records (not yet normalized) plus the detected
profile, a header-identity block (account holder/number for bank statements), and a reject
log. Normalization/entity-resolution (Phase 2) consumes this.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..core import config
from ..core.logging_config import get_logger
from . import detector
from .parsers import excel, pdf, tabular

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

    @property
    def summary(self) -> dict:
        return {
            "file": Path(self.path).name,
            "format": self.format,
            "source_type": self.source_type,
            "profile": self.profile_id,
            "confidence": self.confidence,
            "needs_manual_mapping": self.needs_manual_mapping,
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


def _records_from_grid(grid: list[list], header_idx: int, base_prov: dict) -> tuple[list[dict], list[dict]]:
    headers = [str(c).strip() for c in grid[header_idx]]
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
        df = tabular.read(path)
        headers = list(df.columns)
        det = detector.detect_profile(headers)
        records = []
        for r, row in df.iterrows():
            rec = {c: row[c] for c in headers}
            rec["_provenance"] = {"source_file": Path(path).name, "row": int(r) + 2,
                                  "format": fmt}
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

    else:  # xlsx / pdf -> grid
        if fmt == "xlsx":
            grid = excel.read_grid(path)
        else:
            text_lines, grid = pdf.read(path)
        header_idx = _find_header_row(grid)
        headers = [str(c).strip() for c in grid[header_idx]]
        det = detector.detect_profile(headers)
        base_prov = {"source_file": Path(path).name, "format": fmt}
        records, rejects = _records_from_grid(grid, header_idx, base_prov)
        identity = _extract_identity(grid[:header_idx], text_lines)

    profile = det.get("profile") or {}
    return ParsedFile(
        path=path, format=fmt,
        source_type=det.get("source"),
        profile_id=profile.get("profile", {}).get("id"),
        confidence=det.get("confidence", 0.0),
        needs_manual_mapping=det.get("needs_manual_mapping", True),
        headers=headers, records=records, header_identity=identity, rejects=rejects,
    )


def parse_directory(root: str) -> list[ParsedFile]:
    """Parse every supported file under a directory tree (bank/, cdr/, ipdr/)."""
    out = []
    for p in sorted(Path(root).rglob("*")):
        if p.suffix.lower() in detector.FORMAT_BY_EXT and p.is_file():
            try:
                out.append(parse_file(str(p)))
            except Exception as e:  # per-file failure never aborts the batch (Doc 04)
                log.warning("failed to parse %s: %s", p.name, e)
                out.append(ParsedFile(
                    path=str(p), format=p.suffix.lstrip("."), source_type=None,
                    profile_id=None, confidence=0.0, needs_manual_mapping=True,
                    headers=[], records=[], header_identity={},
                    rejects=[{"error": str(e), "file": p.name}],
                ))
    return out
