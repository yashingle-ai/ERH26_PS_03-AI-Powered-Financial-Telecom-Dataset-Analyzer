"""Word (.docx) table reader -> 2D grids (B1).

Many case files (bank account details, CA reports, charge sheets) are Word tables. These
documents routinely hold *many* tables — the real "CA report - for merge.docx" has 78, and
"confidential nccrp 145.docx" has 84 — because each account or subject gets its own small
table rather than one long one.

`read_grid` originally returned only the largest table, which discarded 2,540 of 5,430
table rows across the real case data (47%). `read_all_grids` returns every table so the
caller can map each one; `read_grid` is kept for callers that want a single best grid.

Legacy .doc (OLE2 binary) is not readable here — see `doc_legacy.py`.
"""

from __future__ import annotations


def read_all_grids(path: str) -> list[tuple[str, list[list]]]:
    """Every table in the document as (label, grid), in document order.

    Mirrors `excel.read_all_sheets` so multi-table Word documents lose no data, the same
    way multi-sheet workbooks stopped losing data.
    """
    from docx import Document

    doc = Document(path)
    out: list[tuple[str, list[list]]] = []
    for i, table in enumerate(doc.tables):
        grid = [[c.text.strip() for c in row.cells] for row in table.rows]
        if any(any(cell for cell in row) for row in grid):
            out.append((f"table{i + 1}", grid))
    return out


def read_grid(path: str) -> list[list]:
    """The largest table in the document (kept for single-grid callers)."""
    grids = read_all_grids(path)
    if not grids:
        return []
    return max((g for _, g in grids), key=len)
