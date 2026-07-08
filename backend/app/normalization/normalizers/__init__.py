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
_TZOFFSETS = {"IST": 19800}  # seconds


def _tz():
    # Asia/Kolkata == IST fixed offset (no DST). Sufficient for this domain.
    return IST


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


def parse_dt(value) -> datetime | None:
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
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz())
    return dt


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
