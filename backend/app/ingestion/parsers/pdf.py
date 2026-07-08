"""PDF reader -> (text_lines, table_grid) via pdfplumber. Bank statements (FR-1).

pdfplumber is coordinate-aware, so it reconstructs ruled tables well for
digitally-generated statements (the common case; scanned PDFs/OCR are optional, Doc 03).
"""

from __future__ import annotations

import pdfplumber


def read(path: str) -> tuple[list[str], list[list]]:
    text_lines: list[str] = []
    table: list[list] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            text_lines.extend(txt.splitlines())
            for t in page.extract_tables() or []:
                for row in t:
                    table.append([("" if c is None else str(c)) for c in row])
    return text_lines, table
