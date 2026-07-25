"""Excel reader -> 2D grid of cell values. Handles both .xlsx (openpyxl) and legacy
.xls (xlrd) via pandas' automatic engine selection. Bank statements / CDR / IPDR (FR-1)."""

from __future__ import annotations

import pandas as pd


def read_grid(path: str) -> list[list]:
    """Read the primary sheet as a raw grid (header found downstream)."""
    df = pd.read_excel(path, header=None, dtype=str, sheet_name=0)
    df = df.where(pd.notna(df), "")
    return df.values.tolist()


def read_all_sheets(path: str) -> list[tuple[str, list[list]]]:
    """B2: read every sheet so multi-sheet workbooks don't lose data.

    Returns [(sheet_name, grid), ...]. pandas auto-selects openpyxl/.xlsx or xlrd/.xls.
    """
    book = pd.read_excel(path, header=None, dtype=str, sheet_name=None)
    out = []
    for name, df in book.items():
        df = df.where(pd.notna(df), "")
        grid = df.values.tolist()
        if grid:
            out.append((str(name), grid))
    return out
