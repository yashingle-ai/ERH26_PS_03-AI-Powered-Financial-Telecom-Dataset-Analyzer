"""CSV / delimited reader -> pandas DataFrame. Bank CSV, CDR, IPDR (FR-1/2/3)."""

from __future__ import annotations

import pandas as pd


def read(path: str, skiprows: int = 0) -> pd.DataFrame:
    # Tolerant read: keep everything as string, don't coerce yet (normalization does that).
    # `on_bad_lines="skip"` survives ragged real-world exports; skiprows drops preamble.
    return pd.read_csv(path, dtype=str, keep_default_na=False, skipinitialspace=True,
                       skiprows=skiprows, on_bad_lines="skip", engine="python")


def read_lines(path: str, n: int = 40) -> list[str]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return [next(fh, "") for _ in range(n)]
