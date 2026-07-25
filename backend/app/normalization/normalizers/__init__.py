"""Value normalizers (FR-7, Doc 06 §10). Aggressive normalization *before* correlation.

- phone  -> E.164 (+91XXXXXXXXXX for India)
- ip     -> canonical string
- datetime -> timezone-aware (default IST when naive)
- amount -> float (strip currency symbols / commas)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from dateutil import parser as dtparser

from ...core import config

IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc
_TZOFFSETS = {"IST": 19800}  # seconds
# Canonical timezone the whole system normalizes to, so all datasets share one axis (A1).
CANONICAL_TZ = IST
_SOURCE_TZ = {"IST": IST, "UTC": UTC}


def _tz(source_tz: str = "IST"):
    return _SOURCE_TZ.get((source_tz or "IST").upper(), IST)


def _to_canonical(dt: datetime | None, source_tz: str) -> datetime | None:
    """Attach the source timezone to a naive value, then convert to the canonical TZ.

    A1 fix: crypto exports are UTC, telecom/bank are IST. Without this a UTC timestamp is
    silently treated as IST (a 5.5h error) and corrupts the unified timeline.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz(source_tz))
    return dt.astimezone(CANONICAL_TZ)


def phone(value) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    if not digits:
        return None
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10:
        prefix = config.settings().get("normalization", {}).get("phone_e164_prefix", "+91")
        return prefix + digits
    return "+" + digits if len(digits) > 10 else None


def ip(value) -> str | None:
    if not value:
        return None
    v = str(value).strip()
    return v or None


def parse_dt(value, source_tz: str = "IST") -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip()
        # ISO (yyyy-mm-dd...) must NOT use dayfirst or dateutil swaps month/day.
        # dd/mm/yyyy (Indian bank statements) requires dayfirst=True.
        iso_like = bool(re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", s))
        try:
            dt = dtparser.parse(s, dayfirst=not iso_like, tzinfos=_TZOFFSETS)
        except (ValueError, OverflowError, TypeError):
            return None
    return _to_canonical(dt, source_tz)


def _digits(v) -> str:
    return re.sub(r"\D", "", str(v)) if v is not None else ""


def _parse_date_naive(value) -> datetime | None:
    """Parse a date-only value to a NAIVE datetime: dd-mm-yyyy, dd/mm/yyyy, or yyyymmdd."""
    if value is None or value == "":
        return None
    s = str(value).strip().strip("'\"")
    d = _digits(s)
    if len(d) == 8 and ("-" not in s and "/" not in s):   # yyyymmdd
        try:
            return datetime(int(d[:4]), int(d[4:6]), int(d[6:8]))
        except ValueError:
            return None
    iso_like = bool(re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", s))
    try:
        dt = dtparser.parse(s, dayfirst=not iso_like, tzinfos=_TZOFFSETS)
        return dt.replace(tzinfo=None)
    except (ValueError, OverflowError, TypeError):
        return None


def combine_date_time(date_val, time_val, source_tz: str = "IST") -> datetime | None:
    """Combine separate date + time columns into one canonical tz-aware datetime.

    Builds the naive local time first, then applies the source timezone and converts to
    canonical (A1) — so UTC IPDR/crypto and IST CDR land on the same axis correctly.
    Handles time as HH:MM:SS or hhmmss (6 digits). Real CDR/IPDR split these.
    """
    d = _parse_date_naive(date_val)
    if d is None:
        return None
    ts = str(time_val).strip().strip("'\"") if time_val is not None else ""
    if ts in ("", "nan"):
        return _to_canonical(d, source_tz)
    digits = _digits(ts)
    try:
        if ":" in ts:
            parts = [int(x) for x in ts.split(":")]
            hh, mm, ss = (parts + [0, 0, 0])[:3]
        elif len(digits) in (5, 6):                       # hhmmss / hmmss
            digits = digits.zfill(6)
            hh, mm, ss = int(digits[:2]), int(digits[2:4]), int(digits[4:6])
        elif len(digits) in (3, 4):                       # hhmm
            digits = digits.zfill(4)
            hh, mm, ss = int(digits[:2]), int(digits[2:4]), 0
        else:
            return _to_canonical(d, source_tz)
        return _to_canonical(d.replace(hour=hh, minute=mm, second=ss), source_tz)
    except ValueError:
        return _to_canonical(d, source_tz)


def amount(value) -> float | None:
    if value is None or value == "":
        return None
    s = re.sub(r"[^\d.\-]", "", str(value))
    if s in ("", "-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None
