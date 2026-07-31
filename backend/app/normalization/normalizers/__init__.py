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

# `ascii_digits` guards the entry of every identifier and amount normaliser below. It lives in
# `core` because `ingestion.value_typer` needs the same one and had its own copy — which is
# exactly how half of this fix got missed the first time.
from ...core.text import ascii_digits, digits_only

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
    digits = re.sub(r"\D", "", ascii_digits(value))
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


#: Core-banking exports (Finacle/ICORE, and anything routed through SAS) write
#: `11DEC2019:09:07:02` — a date and time joined by a colon. dateutil parses the
#: date half alone but chokes on the whole string, so every row in such a file was
#: dropped for "missing timestamp" even though the value was perfectly good.
_SAS_DATETIME = re.compile(
    r"^(\d{1,2}[A-Za-z]{3}\d{2,4}):(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?)$"
)

# NCRP complaint PDFs split date/time across lines:
#   "09-06-2024\nHR: 3\nMIN: 50\nAM/PM: PM"  ->  09-06-2024 15:50:00
_NCRP_COMPLAINT_DT = re.compile(
    r"^(?P<date>\d{1,2}[-/]\d{1,2}[-/]\d{2,4})"
    r"(?:\s*HR:\s*(?P<hr>\d{1,2}))?"
    r"(?:\s*MIN:\s*(?P<mn>\d{1,2}))?"
    r"(?:\s*AM/PM:\s*(?P<ap>AM|PM))?$",
    re.I,
)


def _preprocess_dt_string(s: str) -> str:
    """Normalize quirky bank/complaint datetime strings before dateutil."""
    s = re.sub(r"\s+", " ", s).strip()
    m = _SAS_DATETIME.match(s)
    if m:
        return f"{m.group(1)} {m.group(2)}"  # -> "11DEC2019 09:07:02"
    m = _NCRP_COMPLAINT_DT.match(s)
    if m and (m.group("hr") is not None or m.group("ap") is not None):
        date = m.group("date")
        if m.group("hr") is None:
            return date
        h = int(m.group("hr"))
        mn = int(m.group("mn") or 0)
        ap = (m.group("ap") or "").upper()
        if ap == "PM" and h < 12:
            h += 12
        elif ap == "AM" and h == 12:
            h = 0
        return f"{date} {h:02d}:{mn:02d}:00"
    return s


#: Two arbitrary, different defaults. dateutil fills missing components from `default`,
#: so a value carrying no date yields a different date under each — which is how we tell
#: "13:45:00" apart from a real timestamp without writing a format zoo.
_DT_PROBE_A = datetime(2001, 2, 3)
_DT_PROBE_B = datetime(2004, 5, 6)


def parse_dt(value, source_tz: str = "IST") -> datetime | None:
    """Parse a timestamp, or return None if the value cannot supply a real date.

    A time-only value ("13:45:00") is refused rather than parsed. dateutil would
    silently fill in *today*, so a 2019 statement row would enter the timeline dated
    today — and, because every such row gets the same fabricated date, they cluster
    within minutes of each other and can manufacture correlation hits that never
    happened. Returning None makes the row a counted reject instead, which is the
    rule everywhere else here: never drop or invent data silently.

    Date-only values are fine — they parse to midnight, which is a real date.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        s = _preprocess_dt_string(str(value).strip().strip("'\""))
        # ISO (yyyy-mm-dd...) must NOT use dayfirst or dateutil swaps month/day.
        # dd/mm/yyyy (Indian bank statements) requires dayfirst=True.
        iso_like = bool(re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", s))
        try:
            dt = dtparser.parse(s, dayfirst=not iso_like, tzinfos=_TZOFFSETS,
                                default=_DT_PROBE_A)
            alt = dtparser.parse(s, dayfirst=not iso_like, tzinfos=_TZOFFSETS,
                                 default=_DT_PROBE_B)
        except (ValueError, OverflowError, TypeError):
            return None
        if dt.date() != alt.date():      # the date came from the default, not the value
            return None
    return _to_canonical(dt, source_tz)


def account_no(value) -> str | None:
    """Clean NCRP / statement account cells before they become merge keys.

    Complaint tables use `-:39951540286` and multi-line `201029737717\\nLayer : 1`.
    """
    if value is None:
        return None
    # Digits normalised to ASCII first: ACCOUNT_NO is a merge key, so the same account written
    # in Gujarati numerals in an affidavit and in ASCII on the statement must produce one key.
    s = ascii_digits(value).strip()
    if not s:
        return None
    s = s.splitlines()[0].strip()
    s = re.sub(r"^[\-:]+\s*", "", s).strip()
    return s or None


#: Kept as a module-local name because callers across the codebase already import it.
_digits = digits_only


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


#: Currency tokens removed **with any trailing dot**, before the character filter runs. Latin
#: `Rs.`/`INR.`, the rupee sign, and the Gujarati (રૂ) and Devanagari (रु) abbreviations.
_CURRENCY = re.compile(r"(?i)(?:\brs\b|\binr\b|₹|રૂ|रु)\.?\s*")
#: The Indian "rupees only" terminator, e.g. `75,00,000/-`.
_RUPEES_ONLY = re.compile(r"/\s*-?\s*$")


def amount(value) -> float | None:
    """Parse a money cell to float, or None if the magnitude cannot be established.

    `Rs.75,00,000` used to return **0.75**. The character filter kept the dot belonging to
    `Rs.` and dropped the grouping commas, leaving `.7500000`, which `float()` reads as a
    fraction — a ₹75-lakh transfer recorded as 75 paise, silently, with no reject entry and
    nothing anywhere to indicate a problem. It fed `total_in`, the `structuring` band test,
    `layering`'s minimum-amount floor, the risk score and the STR alike.

    Not a Gujarati-specific fault — Latin `Rs.` did exactly the same — but it surfaced while
    auditing Gujarati handling, because the police affidavits write `રૂ.૭૫,૦૦,૦૦૦/-`. The
    `/-` variant at least failed loudly and returned None; the bare `Rs.` form did not.

    Refusing is the correct failure here. A None becomes a visible reject; a wrong magnitude
    does not, and there is no way for a reader downstream to tell 0.75 from a real 0.75.
    """
    if value is None or value == "":
        return None
    s = ascii_digits(value).strip()
    s = _CURRENCY.sub("", s)
    s = _RUPEES_ONLY.sub("", s).strip()
    s = re.sub(r"[^\d.\-]", "", s)
    if s in ("", "-", "."):
        return None
    # A leading separator is the signature of exactly the corruption above, not a fraction:
    # amounts in this data are written `0.75`, never `.75`. If one still reaches here the
    # input is in a form this function has not been taught, and the magnitude is unknown.
    if s.startswith("."):
        return None
    try:
        return float(s)
    except ValueError:
        return None
