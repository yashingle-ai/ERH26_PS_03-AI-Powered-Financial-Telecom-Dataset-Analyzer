"""Word (.docx) table reader -> 2D grid (B1).

Many case files (bank account details, charts) are Word tables. We extract the largest
table as a grid; the downstream header-finder + profiles map it like any other source.
Legacy .doc (binary) is not supported here — convert to .docx/.xlsx first.
"""

from __future__ import annotations


def read_grid(path: str) -> list[list]:
    from docx import Document

    doc = Document(path)
    best: list[list] = []
    for table in doc.tables:
        grid = []
        for row in table.rows:
            grid.append([c.text.strip() for c in row.cells])
        if len(grid) > len(best):
            best = grid
    return best
