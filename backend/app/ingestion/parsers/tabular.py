"""CSV / delimited reader -> pandas DataFrame. Bank CSV, CDR, IPDR (FR-1/2/3)."""

from __future__ import annotations

import pandas as pd


def read(path: str, skiprows: int = 0) -> pd.DataFrame:
    # Tolerant read: keep everything as string, don't coerce yet (normalization does that).
    # `on_bad_lines="skip"` survives ragged real-world exports; skiprows drops preamble.
    #
    # index_col=False is load-bearing, not cosmetic. Operator CDR exports routinely end
    # each data row with a trailing comma, so the rows carry one more field than the header.
    # pandas resolves that by silently promoting column 0 to the index, which shifts every
    # column left by one: the A-party number lands in CALL_TYPE, the call date lands in
    # "Call Initiation Time", and normalization then rejects the row for a missing phone.
    # On the real case data this silently dropped whole files — 42,873 of 42,873 rows in the
    # largest. Forcing index_col=False keeps the columns aligned with the header.
    return pd.read_csv(path, dtype=str, keep_default_na=False, skipinitialspace=True,
                       skiprows=skiprows, on_bad_lines="skip", engine="python",
                       index_col=False)


def read_lines(path: str, n: int = 40) -> list[str]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return [next(fh, "") for _ in range(n)]
