"""CSV / delimited reader -> pandas DataFrame. Bank CSV, CDR, IPDR (FR-1/2/3)."""

from __future__ import annotations

import pandas as pd


def read(path: str) -> pd.DataFrame:
    # Tolerant read: keep everything as string, don't coerce yet (normalization does that).
    return pd.read_csv(path, dtype=str, keep_default_na=False, skipinitialspace=True)
