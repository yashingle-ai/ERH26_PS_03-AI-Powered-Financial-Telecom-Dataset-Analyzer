"""Excel reader -> 2D grid of cell values (openpyxl). Bank statements only (FR-1)."""

from __future__ import annotations

import openpyxl


def read_grid(path: str) -> list[list]:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.active
    grid = []
    for row in ws.iter_rows(values_only=True):
        grid.append([("" if c is None else c) for c in row])
    wb.close()
    return grid
