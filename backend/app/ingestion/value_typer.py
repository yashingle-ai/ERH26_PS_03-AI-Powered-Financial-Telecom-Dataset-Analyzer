"""Instance-level column typing — infer a column's canonical target from its VALUES.

Why this exists, measured rather than assumed. Every classification decision in the
pipeline read one thing: header strings against hand-written alias lists. That single
vocabulary gated the sheet choice, the header row, the section split, the profile match
*and* the field mapping, so one unknown spelling cascaded into a whole lost file: the
header row is not found -> `_find_header_row` falls back to row 0 (a letterhead) ->
`score_profile` returns 0.0 -> `source_type` is None -> the file is rejected entirely.
Patching aliases was tried twice and drifted back both times, which is stated in
`detector._fallback_score` itself.

Values do not drift the way labels do. A column of `11DEC2019:09:07:02` is a timestamp
whether the bank calls it `Tran Date`, `Txn Dt`, `पोस्टिंग दिनांक` or nothing at all.
That is the instance-level matcher of Rahm & Bernstein's schema-matching taxonomy, and
the principle behind Sherlock/Sato-style semantic type detection: type from values, not
from names.

Three signals combine here, deliberately in this order:

  1. a **value gate** — a column may only claim a canonical target if its sampled values
     actually look like that target's type. This is the drift-immune part and it is
     mandatory: nothing is ever mapped on a name alone, because that is the mechanism
     that already fails.
  2. a **fuzzy header tiebreak** — among targets whose gate passes, the one whose aliases
     the header most resembles wins. Abbreviations are expanded before comparison, so
     `Withdrawal Amt.` reaches `Debit Amount`. This is what separates `debit` from
     `credit`, which are value-identical.
  3. a **one-to-one assignment** — two columns may not claim the same target. Resolving
     each column independently is how `pstd_dt` overwrote a clean `Tran_Date` and took
     95% of bank rows with it.

Safety, because a wrong inference here manufactures evidence:

  * inference only ever fills a target the profile's own aliases did NOT map. A real
    header match always wins, so this can add recognition and never change an existing
    reading.
  * a row-counter column is detected and vetoed explicitly. An NCRP export's serial
    column being read as an account number is a bug this codebase has already paid for.
  * every inferred mapping is returned with its evidence (type, purity, header score) so
    it can be shown to an analyst and audited, and callers flag such files for review.
"""

from __future__ import annotations

import os
import re
from difflib import SequenceMatcher


def enabled() -> bool:
    """Value-based inference can be switched off with ERAKSHAK_VALUE_TYPING=0.

    Two reasons it is a flag and not a constant. It makes the before/after arms of a
    measurement run the *same* build, so a number that moves cannot be an artefact of
    some other edit. And an analyst preparing evidence may want a strictly
    header-declared run, with no inferred column readings in it at all.
    """
    return os.environ.get("ERAKSHAK_VALUE_TYPING", "1").strip().lower() not in (
        "0", "false", "no", "off")

# --------------------------------------------------------------------------------------
# sampling
# --------------------------------------------------------------------------------------

#: Values sampled per column. Spread across the column rather than taken from the top:
#: real exports carry sub-headers, opening-balance rows and totals near the edges.
_SAMPLE = 200
#: Below this many non-empty values a column carries no usable evidence. Typing a column
#: from two cells is guessing, and guessing here fabricates identifiers.
_MIN_SAMPLES = 4
#: Fraction of sampled values that must match a type before the column may claim it.
_MIN_PURITY = 0.75
#: Datetime columns are the messiest in practice (opening-balance rows, "B/F", footers),
#: so they get a slightly lower bar than identifier columns.
_MIN_PURITY_TIME = 0.60


def clean_value(value) -> str:
    """Normalize a cell the way the downstream mapper and normalizers already do.

    Two measured reasons, both cases of the typer being stricter than the code that
    consumes its output — so a column the pipeline could read typed as nothing:

      * quotes. An NCRP register writes text-forced Excel cells, so the apostrophe
        survives extraction: `"'50200099412403'"`. `field_mapper.map_record` strips those.
      * embedded newlines. pdfplumber returns a complaint PDF's date cell as
        `'15-05-2024\\nAM/PM: AM'`. Both `_norm_header` and
        `normalizers._preprocess_dt_string` collapse whitespace before doing anything, so
        typing the raw cell meant every `Transaction Date` column in every NCRP PDF
        matched no temporal pattern at all.
    """
    return re.sub(r"\s+", " ", str(value)).strip().strip("'\"").strip()


def _account_candidate(v: str) -> str:
    """Mirror `normalizers.account_no`: first line, leading `-:` stripped.

    Complaint tables write accounts as `-:016901567850` and `201029737717 Layer : 1`.
    The normalizer has always cleaned that before using the value as a merge key; the
    typer did not, so a whole column of usable accounts failed the shape test on a
    two-character prefix.
    """
    s = v.split(" Layer")[0].strip()
    return re.sub(r"^[\-:]+\s*", "", s).strip()


def sample_values(values: list) -> list[str]:
    """Non-empty, wrapper-stripped values, evenly spread, capped at `_SAMPLE`."""
    cleaned = [clean_value(v) for v in values if v is not None and str(v).strip() != ""]
    cleaned = [v for v in cleaned if v]
    if len(cleaned) <= _SAMPLE:
        return cleaned
    stride = len(cleaned) / _SAMPLE
    return [cleaned[int(i * stride)] for i in range(_SAMPLE)]


# --------------------------------------------------------------------------------------
# value recognizers
# --------------------------------------------------------------------------------------

_DATE = r"(?:\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}" \
        r"|\d{1,2}[-\s]?[A-Za-z]{3,9}[-\s]?\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s*\d{4})"
#: Hours and minutes are separated by a colon, never a dot, and minutes cannot exceed 59.
#: Allowing `.` and bare `\d{2}` made a clock out of small rupee amounts: `23.60` matched
#: as 23:60, so `_is_amount` rejected it as temporal and a real statement's debit column —
#: 42 values — typed as nothing at all. `.` survives only for fractional seconds.
_TIME = r"(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?:\.\d+)?\s*(?:[AaPp][Mm])?"

#: NCRP complaint PDFs append the clock as separate labelled fields, and often only some
#: of them: `15-05-2024 AM/PM: AM` carries no hour at all. `_preprocess_dt_string` already
#: reduces that to the bare date, so the tail must not stop the cell being typed temporal.
_NCRP_CLOCK_TAIL = r"(?:\s+(?:HR|MIN|AM\s*/\s*PM)\s*:\s*[A-Za-z0-9]*)*"

_RE_DATE_ONLY = re.compile(rf"^{_DATE}{_NCRP_CLOCK_TAIL}$", re.I)
# `11DEC2019:09:07:02` (Finacle/SAS) joins the two halves with a colon, and NCRP PDFs
# split the clock into `HR:`/`MIN:`/`AM/PM:` fields — both are real and both used to be
# dropped as "missing timestamp", so both are recognized as datetimes here.
_RE_DATETIME = re.compile(
    rf"^{_DATE}(?:[\s:T]+{_TIME})"
    rf"|^{_DATE}\s+HR:\s*\d{{1,2}}"
    rf"|^\d{{1,2}}[A-Za-z]{{3}}\d{{2,4}}:{_TIME}$",
    re.I,
)
_RE_TIME_ONLY = re.compile(rf"^{_TIME}$")

# Money: optional sign/symbol, grouped or plain digits, optional Dr/Cr suffix.
_RE_AMOUNT = re.compile(
    r"^[-+(]?\s*(?:₹|rs\.?|inr|\$)?\s*\d{1,3}(?:,\d{2,3})*(?:\.\d{1,4})?\s*"
    r"(?:cr|dr|db)?\)?$|^[-+(]?\s*(?:₹|rs\.?|inr|\$)?\s*\d+(?:\.\d{1,4})?\s*(?:cr|dr|db)?\)?$",
    re.I,
)
#: A decimal fraction, thousands grouping or a currency mark — what separates money from
#: a long digit string. Without this an account-number column reads as `amount`, and a
#: statement's account column gets normalized as a transaction value.
_RE_MONEY_TELL = re.compile(r"\.\d{1,4}$|,\d{2,3}|₹|rs\.?|inr|\$|\b(?:cr|dr)\b", re.I)
#: Digits-only runs this long are identifiers (account / UTR / IMEI), not rupee amounts.
_MAX_PLAIN_AMOUNT_DIGITS = 8
#: A bare integer with no separators — the only shape allowed to be a duration/port/bytes.
_RE_PLAIN_INT = re.compile(r"^\d{1,12}$")

_RE_IPV4 = re.compile(r"^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
                      r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$")
# >=3 colons: a clock ("09:07:02") has two and was being typed as IPv6, which let a
# time column claim an ip target.
_RE_IPV6 = re.compile(r"^(?:[0-9A-Fa-f]{0,4}:){3,7}[0-9A-Fa-f]{0,4}$")
_RE_UPI = re.compile(r"^[a-zA-Z0-9.\-_]{2,}@[a-zA-Z]{2,}$")
_RE_PERSON = re.compile(r"^[A-Za-z][A-Za-z.'\-]*(?:\s+[A-Za-z.'\-]+){0,4}$")
_RE_CELL_ID = re.compile(r"^[0-9A-Fa-f]{2,6}(?:[-_/][0-9A-Fa-f]{1,8}){2,4}$")
_RE_CURRENCY = re.compile(r"^[A-Z]{3}$")
#: Characters a phone number may contain. Without this guard the digits of
#: "09-06-2024 HR: 3 MIN: 50" concatenated to an 11-digit string and typed as a phone.
_RE_PHONE_SHAPE = re.compile(r"^[+\d\s\-()]+$")

#: Call-type / direction vocabularies seen in real TSP exports.
_DIRECTION_WORDS = {
    "moc", "mtc", "mo", "mt", "sms-o", "sms-t", "smso", "smst", "in", "out",
    "incoming", "outgoing", "inbound", "outbound", "a", "b", "cr", "dr", "debit",
    "credit", "call-in", "call-out", "voice", "sms", "data",
}

_DIGITS = re.compile(r"\D")


def _digits(value: str) -> str:
    return _DIGITS.sub("", value)


def _luhn_ok(num: str) -> bool:
    """IMEI carries a Luhn check digit; IMSI does not. The only reliable way to tell two
    15-digit identifier columns apart without trusting the header."""
    total, alt = 0, False
    for ch in reversed(num):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def _is_phone(v: str) -> bool:
    if not _RE_PHONE_SHAPE.match(v):
        return False
    d = _digits(v)
    if len(d) == 10:
        return d[0] in "6789"
    if len(d) == 11 and d[0] == "0":
        return d[1] in "6789"
    if len(d) == 12 and d.startswith("91"):
        return d[2] in "6789"
    return False


def _is_imsi(v: str) -> bool:
    """15 digits under an Indian MCC. The MCC prefix, not Luhn, is the discriminator.

    Luhn was tried first and is too brittle: a case file with one mistyped IMEI drops the
    column's purity below the gate, and then neither `imei` nor `imsi` fires and the
    column goes unmapped. The 404/405 prefix is stable across every real export here.
    """
    if not _RE_PHONE_SHAPE.match(v):
        return False
    d = _digits(v)
    return len(d) == 15 and d.startswith(("404", "405"))


def _is_imei(v: str) -> bool:
    if not _RE_PHONE_SHAPE.match(v):
        return False
    d = _digits(v)
    if len(d) not in (15, 16) or d.startswith(("404", "405")):
        return False
    # Luhn is a bonus signal, not a gate — see `_is_imsi`. A 15-digit non-MCC identifier
    # in a telecom export is an IMEI whether or not its check digit survived transcription.
    return True


def _is_acct_like(v: str) -> bool:
    """A bank/wallet account identifier: mostly digits, 9-20 long, not a phone or IMSI.

    Deliberately shape-only. Whether such a column IS the account (rather than a UTR or
    a cheque number) is settled by `_TARGET_TYPES` plus the length/uniqueness rule in
    `_column_types`, not here.

    All 15-digit values were excluded at first, to keep IMEI and IMSI columns off the
    account target. Measured against a real NCRP register that was wrong: 28 of its 173
    accounts are 15 digits (`040026900000174`, `500101013942036` — Union/SBI lengths), and
    excluding them held the column's purity at 0.68, under the gate, so the register's
    account column typed as nothing at all. Only the MCC-prefixed IMSI shape is excluded
    now; an IMEI column cannot reach an account target anyway, because no bank profile
    declares one.
    """
    base = _account_candidate(v)
    s = base.replace(" ", "").replace("-", "").replace("/", "")
    d = _digits(s)
    if not (9 <= len(d) <= 20):
        return False
    if len(d) != len(s) and not s.isalnum():
        return False
    return not (_is_phone(base) or _is_imsi(base))


def _is_temporal(v: str) -> bool:
    return bool(_RE_DATETIME.match(v) or _RE_DATE_ONLY.match(v) or _RE_TIME_ONLY.match(v))


def _is_amount(v: str) -> bool:
    """Money-shaped. A long digit run with no money tell is an identifier, not a value."""
    if not _RE_AMOUNT.match(v) or _is_temporal(v):
        return False
    if _RE_MONEY_TELL.search(v):
        return True
    return len(_digits(v)) <= _MAX_PLAIN_AMOUNT_DIGITS


def _is_narration(v: str) -> bool:
    if _is_temporal(v):
        return False
    return len(v) >= 12 and (" " in v or "/" in v or "-" in v) and any(c.isalpha() for c in v)


def _is_cell_id(v: str) -> bool:
    if _is_temporal(v) or _RE_IPV4.match(v):
        return False
    return bool(_RE_CELL_ID.match(v))


def _plain_int(v: str, lo: int, hi: int) -> bool:
    """Bare integer in range. Separators and decimals are rejected on purpose: allowing
    them let a `5,000.00` debit column read as a duration or a byte count."""
    if not _RE_PLAIN_INT.match(v):
        return False
    return lo <= int(v) <= hi


#: Every semantic type this module can recognize, with its predicate.
_RECOGNIZERS: dict[str, object] = {
    "datetime": lambda v: bool(_RE_DATETIME.match(v)),
    "date": lambda v: bool(_RE_DATE_ONLY.match(v)),
    "time": lambda v: bool(_RE_TIME_ONLY.match(v)),
    "amount": _is_amount,
    "phone": _is_phone,
    "imei": _is_imei,
    "imsi": _is_imsi,
    "account_like": _is_acct_like,
    "ipv4": lambda v: bool(_RE_IPV4.match(v)),
    "ipv6": lambda v: bool(_RE_IPV6.match(v)) and not _RE_TIME_ONLY.match(v),
    "upi_id": lambda v: bool(_RE_UPI.match(v)),
    "narration": _is_narration,
    "person_name": lambda v: bool(_RE_PERSON.match(v)) and " " in v and not any(
        c.isdigit() for c in v),
    "cell_id": _is_cell_id,
    "currency_code": lambda v: bool(_RE_CURRENCY.match(v)),
    "direction_code": lambda v: v.strip().lower() in _DIRECTION_WORDS,
    "port": lambda v: _plain_int(v, 1, 65535),
    "duration": lambda v: _plain_int(v, 0, 86400 * 7),
    "bytes": lambda v: _plain_int(v, 0, 10**12),
}


def _as_int(value: str) -> int | None:
    """Integer value of a cell, or None if it isn't a finite number.

    `int(float(v))` was the first version and it lost eleven whole CDR files. A real LEA
    export carries a cell that floats to infinity, and `int(float("inf"))` raises
    OverflowError — not the ValueError being caught — so the exception escaped to
    `_parse_one`, which recorded the file as a zero-row reject. Same table count, 118,510
    rows gone. Non-finite values are the ones to guard, not just unparseable ones.
    """
    try:
        f = float(str(value).replace(",", ""))
    except (ValueError, TypeError, OverflowError):
        return None
    if f != f or f in (float("inf"), float("-inf")):    # NaN or +/-Inf
        return None
    try:
        return int(f)
    except (ValueError, OverflowError):
        return None


#: Fraction of the 1..N range a serial column's distinct values must cover.
_MIN_SERIAL_COVERAGE = 0.7
#: Fraction of a serial column's values that must parse as integers at all.
_MIN_SERIAL_PARSED = 0.85


#: Header words that mark a column as describing the *handler* of a record rather than
#: its subject. Measured on a real complaint register: `Mobile Number` sat beside
#: `Name of Complain reported officer` / `Designation` / `police Station`, and it is the
#: investigating officer's phone, not the account holder's. The data settles it — 94 of 98
#: officers have exactly one mobile, while only 10 of 32 accounts do, so the phone is a
#: function of the officer. Emitting an account-to-phone link from those rows would merge
#: 32 mule accounts into police-officer entities, and bridge unrelated mule accounts to
#: each other through a shared officer phone. One constable's number already appears
#: against two different accounts. That is manufactured evidence that reads as success,
#: and it is what rule 3 ("never fabricate an identity link") exists to prevent.
_ADMIN_ROLE_WORDS = {
    "officer", "designation", "constable", "inspector", "nodal", "superintendent",
    "police", "thana", "investigating", "reported", "handler", "branch", "manager",
    "nodalofficer", "deo", "dsp", "sho", "io",
}


def has_admin_role_columns(headers: list[str]) -> bool:
    """True when the table carries handler/officer columns.

    Phone columns in such a table are administrative contacts, so they are not offered to
    subject-phone targets. Refusing is the safe direction: a missed link costs a lead,
    an invented one puts an innocent person inside a correlation hit.
    """
    for header in headers:
        if set(normalize_header(header).split()) & _ADMIN_ROLE_WORDS:
            return True
    return False


def _is_serial(values: list[str]) -> bool:
    """True when the column is a row counter (1,2,3...) rather than data.

    Vetoed explicitly rather than left to purity thresholds: a serial column is 9-20
    digits long only by accident, and an NCRP export's serial column read as an account
    number is a bug this pipeline has already been bitten by.

    Strict ascending order was the first rule and it was too strict. A multi-page PDF
    register restarts its `S No.` on every page, so the sequence is not sorted — and on
    real complaint PDFs the column then typed as money and claimed the balance target.
    Coverage of the 1..N range is what actually identifies a counter, order is not.
    """
    if len(values) < 5:
        return False
    nums = []
    for v in values:
        n = _as_int(v)
        if n is not None:
            nums.append(n)
    # Requiring every value to parse was too strict on real PDFs: a complaint register
    # repeats its `S No.` heading on each page and pdfplumber bleeds stray cells into the
    # first column, so four junk values out of 119 kept the counter typed as money.
    if len(nums) < _MIN_SERIAL_PARSED * len(values) or len(nums) < 5:
        return False
    uniq = sorted(set(nums))
    if uniq[0] > 3 or uniq[-1] > len(nums) * 3:
        return False
    span = uniq[-1] - uniq[0] + 1
    return len(uniq) / span >= _MIN_SERIAL_COVERAGE


def _column_types(values: list[str]) -> dict[str, float]:
    """Semantic type -> purity (fraction of sampled values matching), gated."""
    sampled = sample_values(values)
    if len(sampled) < _MIN_SAMPLES:
        return {}
    if _is_serial(sampled):
        return {"serial": 1.0}

    n = len(sampled)
    out: dict[str, float] = {}
    for name, ok in _RECOGNIZERS.items():
        hits = sum(1 for v in sampled if ok(v))
        purity = hits / n
        floor = _MIN_PURITY_TIME if name in ("datetime", "date", "time") else _MIN_PURITY
        if purity >= floor:
            out[name] = round(purity, 3)

    unique_ratio = len(set(sampled)) / n

    # A rupee column of 1, 2, 6 is not money — it is a code. Requiring either a visible
    # money tell or a value large enough to be a transaction keeps small-integer code
    # columns (Layer, category) off the amount/debit/balance targets.
    if "amount" in out:
        tells = sum(1 for v in sampled if _RE_MONEY_TELL.search(v))
        biggest = max((len(_digits(v)) for v in sampled), default=0)
        if tells / n < 0.2 and biggest < 3:
            out.pop("amount")

    # Separating an account column from a UTR/reference column. Uniqueness alone was the
    # first rule and it misread real evidence: an NCRP register lists a different mule
    # account on every row, so it is ~100% unique and was demoted to a reference — losing
    # the one column in the case that carries account and mobile on the same row.
    # Length spread is the better signal. A UTR column is uniformly 12 digits; account
    # numbers vary in length across banks (10, 12, 14, 16 in the same register), and a
    # single-bank statement's account column repeats instead of being unique.
    if "account_like" in out and unique_ratio > 0.95:
        lengths = {len(_digits(v)) for v in sampled if _is_acct_like(v)}
        if len(lengths) <= 1:
            out["reference_like"] = out.pop("account_like")

    # A single date+time column beats reading it as a bare date.
    if "datetime" in out:
        out.pop("date", None)
    out["_unique_ratio"] = round(unique_ratio, 3)
    return out


# --------------------------------------------------------------------------------------
# canonical target <- semantic type
# --------------------------------------------------------------------------------------

#: Which semantic types may fill which canonical target. Small and explicit on purpose:
#: the canonical vocabulary is fixed (see config/profiles/**), and an explicit table is
#: auditable in a way a learned mapping is not — which matters when the output is evidence.
_TARGET_TYPES: dict[str, tuple[str, ...]] = {
    "timestamp_start": ("datetime", "date"),
    "timestamp_end": ("datetime",),
    "datetime_col": ("datetime",),
    "date_col": ("date", "datetime"),
    "time_col": ("time",),
    "end_date_col": ("date", "datetime"),
    "end_time_col": ("time",),
    "account_no": ("account_like",),
    "account_holder": ("person_name",),
    "debit": ("amount",),
    "credit": ("amount",),
    "amount": ("amount",),
    "attributes.balance": ("amount",),
    "attributes.narration": ("narration",),
    "attributes.ref_no": ("reference_like", "account_like"),
    "attributes.currency": ("currency_code",),
    "entity_phone": ("phone",),
    "counterparty_phone": ("phone",),
    "phone": ("phone",),
    "msisdn": ("phone",),
    "caller": ("phone",),
    "called": ("phone",),
    "imei": ("imei",),
    "imsi": ("imsi",),
    "ip": ("ipv4", "ipv6"),
    "ip_public": ("ipv4", "ipv6"),
    "ip_private": ("ipv4", "ipv6"),
    "attributes.dest_ip": ("ipv4", "ipv6"),
    "attributes.port": ("port",),
    "attributes.dest_port": ("port",),
    "attributes.cell_id": ("cell_id",),
    "attributes.duration": ("duration",),
    "attributes.session_duration": ("duration",),
    "attributes.bytes_up": ("bytes",),
    "attributes.bytes_down": ("bytes",),
    "direction": ("direction_code",),
}

#: Targets that make a phone a MERGE KEY for the record's subject. `PHONE` is in
#: `entity_resolution.merge_key_types`, so filling one of these from an administrative
#: contact column merges entities transitively — see `_ADMIN_ROLE_WORDS`.
_SUBJECT_PHONE_TARGETS = frozenset({
    "entity_phone", "counterparty_phone", "phone", "msisdn", "caller", "called",
})


# --------------------------------------------------------------------------------------
# fuzzy header similarity (tiebreak only)
# --------------------------------------------------------------------------------------

#: Abbreviations real exports use. Expanded before comparison so `Withdrawal Amt.`
#: reaches `Debit Amount` and `Txn Dt` reaches `Transaction Date` — the exact class of
#: miss that zeroed a fully parseable statement's score.
_ABBREV = {
    "amt": "amount", "amnt": "amount", "dt": "date", "txn": "transaction",
    "tran": "transaction", "trans": "transaction", "trn": "transaction",
    "ac": "account", "acc": "account", "acct": "account", "a/c": "account",
    "no": "number", "num": "number", "nbr": "number", "wdl": "withdrawal",
    "dep": "deposit", "bal": "balance", "desc": "description", "narr": "narration",
    "ref": "reference", "cr": "credit", "dr": "debit", "tm": "time",
    "mob": "mobile", "ph": "phone", "cust": "customer", "particulars": "narration",
    "details": "narration", "remarks": "narration", "value": "value",
}


def normalize_header(header: str) -> str:
    """Lowercase, strip punctuation and parentheticals, expand abbreviations."""
    s = str(header).lower()
    s = re.sub(r"\(.*?\)", " ", s)              # "Withdrawal Amount (INR )" -> "withdrawal amount"
    s = re.sub(r"[^a-z0-9/]+", " ", s)
    tokens = [_ABBREV.get(t, t) for t in s.split() if t]
    return " ".join(tokens)


def header_similarity(header: str, alias: str) -> float:
    """Token-set overlap blended with character-level ratio, both on normalized forms."""
    a, b = normalize_header(header), normalize_header(alias)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    jaccard = len(ta & tb) / len(ta | tb)
    ratio = SequenceMatcher(None, a, b).ratio()
    return round(max(jaccard, 0.6 * jaccard + 0.4 * ratio), 3)


def _best_alias_score(header: str, spec: dict) -> float:
    return max((header_similarity(header, a) for a in spec.get("aliases", [])), default=0.0)


# --------------------------------------------------------------------------------------
# the matcher
# --------------------------------------------------------------------------------------

#: Confidence a value-gated claim starts from. The value gate is the evidence; the header
#: only orders competing claims, so a nameless column still maps.
_BASE_CONFIDENCE = 0.55

#: Words that say which way money moved. `debit` and `credit` are value-identical — both
#: are just rupee columns — so nothing but the label separates them, and getting it wrong
#: inverts the direction of a transaction, which is evidence rather than cosmetics.
_DEBIT_WORDS = {"out", "withdrawal", "withdrawn", "withdraw", "paid", "payment", "debit",
                "dr", "outflow", "sent", "outgoing", "expense", "spent"}
_CREDIT_WORDS = {"in", "deposit", "received", "receipt", "credit", "cr", "inflow",
                 "recd", "incoming", "income"}
#: Applied to the header score for debit/credit only.
_DIRECTION_BONUS = 0.30
#: A mutually-exclusive amount pair is a debit/credit pair, not a signed single column.
_PAIR_BONUS = 0.20
_PAIR_PENALTY = 0.40
#: Share of value-bearing rows in which exactly one of two columns is filled, before the
#: two are treated as a debit/credit pair.
_MIN_EXCLUSIVITY = 0.85


def _direction_hint(header: str, target: str) -> float:
    if target not in ("debit", "credit"):
        return 0.0
    tokens = set(normalize_header(header).split())
    want, other = ((_DEBIT_WORDS, _CREDIT_WORDS) if target == "debit"
                   else (_CREDIT_WORDS, _DEBIT_WORDS))
    if tokens & want:
        return _DIRECTION_BONUS
    if tokens & other:
        return -_DIRECTION_BONUS
    return 0.0


def _as_float(value) -> float | None:
    try:
        f = float(re.sub(r"[^\d.\-]", "", str(value)))
    except (ValueError, TypeError):
        return None
    return None if f != f else f


def _orient_pair(pair: tuple[str, str], columns: dict[str, list],
                 balance_col: str | None) -> tuple[str, str]:
    """Decide which half of a Dr/Cr pair is the debit. Returns (debit, credit).

    This has to be decided from values, and it matters more than it looks. On a printed
    statement the columns have no names at all — they arrive as `column_4` and `column_5` —
    so the first version fell through to the candidate sort, which broke the tie
    ALPHABETICALLY: `credit` sorts before `debit`, so the debit column became credit and
    every direction in the file was inverted. A wrong direction is worse than a missing
    one; it turns money leaving an account into money arriving.

    The balance column settles it: on rows where the debit column is populated the running
    balance falls. Where there is no balance column the printed-statement convention
    (withdrawal column left of deposit column) is used, and the file is review-flagged
    anyway because a value-claimed profile never clears the auto-detect threshold.
    """
    a, b = pair
    if balance_col:
        balances = [_as_float(v) for v in columns.get(balance_col) or []]
        score = {a: 0, b: 0}
        for i in range(1, len(balances)):
            if balances[i] is None or balances[i - 1] is None:
                continue
            delta = balances[i] - balances[i - 1]
            if delta == 0:
                continue
            for header in (a, b):
                col = columns.get(header) or []
                value = col[i] if i < len(col) else None
                if value is not None and str(value).strip():
                    score[header] += 1 if delta < 0 else -1
        if score[a] != score[b]:
            debit = a if score[a] > score[b] else b
            return debit, (b if debit == a else a)
    return a, b


def _fill_rate(values: list) -> float:
    """Share of rows carrying any value. Distinguishes a balance from a Dr/Cr column."""
    if not values:
        return 0.0
    filled = sum(1 for v in values if v is not None and str(v).strip() != "")
    return filled / len(values)


#: A balance is carried on essentially every row; debit and credit are sparse by nature.
_BALANCE_MIN_FILL = 0.9


def _exclusive_amount_pair(amount_cols: list[str],
                           columns: dict[str, list]) -> tuple[str, str] | None:
    """Find two amount columns where each row fills exactly one — a debit/credit pair.

    Structural table context rather than per-column typing: a balance column is filled on
    every row, and a signed single-amount column has no partner at all, so exclusivity is
    what distinguishes a real Dr/Cr pair from either. Without this a `Money Out` column
    with an unfamiliar name lands on the signed `amount` target and every debit is
    recorded as a credit.
    """
    best, best_score = None, 0.0
    for i, a in enumerate(amount_cols):
        for b in amount_cols[i + 1:]:
            va, vb = columns.get(a) or [], columns.get(b) or []
            n = min(len(va), len(vb))
            if n < _MIN_SAMPLES:
                continue
            both = exclusive = 0
            for k in range(n):
                fa = va[k] is not None and str(va[k]).strip() != ""
                fb = vb[k] is not None and str(vb[k]).strip() != ""
                if fa or fb:
                    both += 1
                    if fa != fb:
                        exclusive += 1
            if both < _MIN_SAMPLES:
                continue
            score = exclusive / both
            if score >= _MIN_EXCLUSIVITY and score > best_score:
                best, best_score = (a, b), score
    return best


def profile_targets(profile: dict) -> dict[str, dict]:
    return profile.get("field_map", {}) or {}


def infer_targets(headers: list[str], columns: dict[str, list], profile: dict,
                  already_mapped: set[str] | None = None) -> dict[str, dict]:
    """Infer {header: {target, confidence, type, purity, header_score}} from values.

    `already_mapped` names canonical targets the profile's own aliases resolved. Those are
    never re-assigned — a real header match always wins, so this only ever fills gaps.
    """
    fields = profile_targets(profile)
    if not fields:
        return {}
    taken = set(already_mapped or ())

    # (score, header, target, evidence) for every value-gated candidate pairing.
    candidates: list[tuple[float, str, str, dict]] = []
    typed = {h: _column_types(columns.get(h, [])) for h in headers}

    amount_cols = [h for h in headers if "amount" in (typed.get(h) or {})]
    pair = _exclusive_amount_pair(amount_cols, columns) if len(amount_cols) > 1 else None
    admin_table = has_admin_role_columns(headers)

    balance_col = None
    debit_col = credit_col = None
    if pair:
        filled = [(h, _fill_rate(columns.get(h) or [])) for h in amount_cols
                  if h not in pair]
        filled = [(h, f) for h, f in filled if f >= _BALANCE_MIN_FILL]
        if filled:
            balance_col = max(filled, key=lambda x: x[1])[0]
        debit_col, credit_col = _orient_pair(pair, columns, balance_col)

    for header in headers:
        types = typed.get(header) or {}
        if not types or "serial" in types:
            continue
        in_pair = bool(pair and header in pair)
        for target, spec in fields.items():
            if target in taken:
                continue
            allowed = _TARGET_TYPES.get(target)
            if not allowed:
                continue
            if admin_table and target in _SUBJECT_PHONE_TARGETS:
                # An officer's contact number is not the subject of the record.
                continue
            # Orientation is settled by the balance delta, not by a score tie.
            if debit_col is not None and header == debit_col and target == "credit":
                continue
            if credit_col is not None and header == credit_col and target == "debit":
                continue
            if balance_col is not None and header == balance_col and \
                    target in ("debit", "credit"):
                continue
            best_type, best_purity = None, 0.0
            for t in allowed:
                if types.get(t, 0.0) > best_purity:
                    best_type, best_purity = t, types[t]
            if not best_type:
                continue                      # value gate failed — no claim, by design
            hscore = _best_alias_score(header, spec)
            score = _BASE_CONFIDENCE + 0.25 * best_purity + 0.20 * hscore
            score += _direction_hint(header, target)
            if pair:
                # A Dr/Cr pair means this is a two-column statement, so the signed
                # single-`amount` path is not in play for ANY column here. Left unpenalised
                # on a real printed statement the always-populated balance column took
                # `amount`, and `_bank_amount_direction` then reported the running balance
                # as the transaction value on every row that had no credit.
                if target == "amount":
                    score -= _PAIR_PENALTY
                if in_pair and target in ("debit", "credit"):
                    score += _PAIR_BONUS
                elif in_pair and target == "attributes.balance":
                    score -= _PAIR_PENALTY
                elif not in_pair and target == "attributes.balance" and \
                        _fill_rate(columns.get(header) or []) >= _BALANCE_MIN_FILL:
                    # Populated on every row while the pair alternates — that is the ledger
                    # balance, and naming it lets `_norm_bank` record it instead of losing it.
                    score += _PAIR_BONUS
            candidates.append((round(score, 4), header, target, {
                "type": best_type, "purity": best_purity, "header_score": hscore,
            }))

    # One-to-one assignment, highest score first. Greedy rather than Hungarian: the
    # matrix is a handful of columns wide and a greedy pass is auditable line by line,
    # which matters more here than the last fraction of optimality.
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    out: dict[str, dict] = {}
    used_targets: set[str] = set()
    for score, header, target, evidence in candidates:
        if header in out or target in used_targets:
            continue
        out[header] = {"target": target, "confidence": min(score, 0.95), **evidence}
        used_targets.add(target)
    return out


#: Ceiling for a value-only claim. Kept under `config.auto_detect_threshold()` so such a
#: file is always flagged `needs_manual_mapping`, and so any genuine header match wins.
_MAX_VALUE_CONFIDENCE = 0.54
#: Distinct targets at which a value-only claim is considered fully evidenced.
_TARGET_SATURATION = 6
#: Timezone a profile is assumed to be in unless it says otherwise.
_DEFAULT_SOURCE_TZ = "IST"

_TIME_ANCHORS = ("timestamp_start", "datetime_col", "date_col", "timestamp_end")
_SUBJECT_ANCHORS = ("account_no", "amount", "debit", "credit", "entity_phone", "phone",
                    "msisdn", "caller", "imei", "imsi", "ip_public", "ip_private")


def value_profile_score(headers: list[str], columns: dict[str, list],
                        profile: dict) -> tuple[float, dict]:
    """Score a profile purely on whether the file's VALUES fit its field types.

    Used when header matching has already failed. Returns (confidence, inferred_map),
    where confidence is 0.0 for "no claim". Rank competing profiles with
    `value_claim_rank`, not with this number — it is deliberately capped and therefore
    ties.

    Three gates, each closing a way this could do harm rather than good:

      * a profile needs a time anchor AND a subject anchor. A file with three
        amount-shaped columns and no clock is not a transaction table. Same bar
        `detector._fallback_score` sets.
      * `match.required_all` is honoured. It means "this shape is mandatory" and no
        fallback may bypass it — the header path already treats it as a hard gate.
      * a profile declaring a non-default `source_tz` is never claimed on values alone.
        `crypto_exchange_ledger` is `source_tz: UTC`, and it declares seven fields where
        `bank_generic` declares twelve. Ranked on values only, it would win a real rupee
        statement and shift every timestamp by 5.5 hours — silently reintroducing the
        exact timeline corruption the A1 fix closed. A timezone is a claim about
        provenance, and values cannot evidence it; its header columns can.
    """
    match = profile.get("profile", {}).get("match") or profile.get("match", {})
    hset = {h.strip().lower() for h in headers if h}
    req_all = [a.strip().lower() for a in match.get("required_all", [])]
    if req_all and not all(a in hset for a in req_all):
        return 0.0, {}
    source_tz = (profile.get("profile", {}).get("source_tz") or _DEFAULT_SOURCE_TZ)
    if str(source_tz).upper() != _DEFAULT_SOURCE_TZ:
        return 0.0, {}

    inferred = infer_targets(headers, columns, profile)
    if not inferred:
        return 0.0, {}
    targets = {v["target"] for v in inferred.values()}
    if not any(t in targets for t in _TIME_ANCHORS):
        return 0.0, {}
    if not any(t in targets for t in _SUBJECT_ANCHORS):
        return 0.0, {}

    # Absolute evidence, not coverage. A ratio rewards a profile for declaring few
    # fields, which is backwards: the profile that maps MORE of the file understands it
    # better. Coverage let a 7-field profile outrank a 12-field one on the same table.
    evidence = min(len(targets) / _TARGET_SATURATION, 1.0)
    mean_conf = sum(v["confidence"] for v in inferred.values()) / len(inferred)
    return round(min(evidence * mean_conf, _MAX_VALUE_CONFIDENCE), 3), inferred


def value_claim_rank(inferred: dict) -> tuple[int, float]:
    """Ranking key for competing value-only claims: most targets, then best mean
    confidence. Separate from the reported confidence, which is capped and so ties."""
    if not inferred:
        return (0, 0.0)
    targets = {v["target"] for v in inferred.values()}
    mean_conf = sum(v["confidence"] for v in inferred.values()) / len(inferred)
    return (len(targets), round(mean_conf, 4))
