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


def sample_values(values: list) -> list[str]:
    """Non-empty string values, evenly spread, capped at `_SAMPLE`."""
    cleaned = [str(v).strip() for v in values if v is not None and str(v).strip() != ""]
    if len(cleaned) <= _SAMPLE:
        return cleaned
    stride = len(cleaned) / _SAMPLE
    return [cleaned[int(i * stride)] for i in range(_SAMPLE)]


# --------------------------------------------------------------------------------------
# value recognizers
# --------------------------------------------------------------------------------------

_DATE = r"(?:\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}" \
        r"|\d{1,2}[-\s]?[A-Za-z]{3,9}[-\s]?\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s*\d{4})"
_TIME = r"(?:[01]?\d|2[0-3])[:.]\d{2}(?:[:.]\d{2})?(?:\.\d+)?\s*(?:[AaPp][Mm])?"

_RE_DATE_ONLY = re.compile(rf"^{_DATE}$")
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
    """A bank/wallet account identifier: mostly digits, 9-20 long, not a phone/IMEI.

    Deliberately shape-only. Whether such a column IS the account (rather than a UTR or
    a cheque number) is settled by `_TARGET_TYPES` plus the cardinality rule in
    `_column_types`, not here.
    """
    s = v.replace(" ", "").replace("-", "").replace("/", "")
    d = _digits(s)
    if not (9 <= len(d) <= 20):
        return False
    if len(d) != len(s) and not s.isalnum():
        return False
    return not (_is_phone(v) or len(d) == 15)


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


def _is_serial(values: list[str]) -> bool:
    """True when the column is a row counter (1,2,3...) rather than data.

    A serial column is digits 9-20 long only by accident of length, but it is also
    ascending and contiguous — and an NCRP export's serial column being read as an
    account number is a bug this pipeline has already been bitten by, so it is vetoed
    explicitly rather than left to purity thresholds.
    """
    if len(values) < 5:
        return False
    nums = []
    for v in values:
        try:
            nums.append(int(float(v.replace(",", ""))))
        except (ValueError, AttributeError):
            return False
    if nums != sorted(nums) or nums[0] > 3:
        return False
    span = nums[-1] - nums[0] + 1
    return span <= len(nums) * 2


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
    # A per-row-unique long digit column is a reference/UTR, not an account. Accounts
    # repeat: a statement has one, a bulk dump has a few hundred across thousands of rows.
    if "account_like" in out and unique_ratio > 0.95:
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
            best_type, best_purity = None, 0.0
            for t in allowed:
                if types.get(t, 0.0) > best_purity:
                    best_type, best_purity = t, types[t]
            if not best_type:
                continue                      # value gate failed — no claim, by design
            hscore = _best_alias_score(header, spec)
            score = _BASE_CONFIDENCE + 0.25 * best_purity + 0.20 * hscore
            score += _direction_hint(header, target)
            if in_pair:
                # Two columns that never both carry a value are a Dr/Cr pair. Reading
                # either as the signed `amount` column, or as the balance, loses direction.
                if target in ("debit", "credit"):
                    score += _PAIR_BONUS
                elif target in ("amount", "attributes.balance"):
                    score -= _PAIR_PENALTY
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


def value_profile_score(headers: list[str], columns: dict[str, list],
                        profile: dict) -> tuple[float, dict]:
    """Score a profile purely on whether the file's VALUES fit its field types.

    Used when header matching has already failed. Returns (score, inferred_map).
    A profile needs a time anchor and a subject before it may claim a file on values
    alone — the same bar `detector._fallback_score` sets, for the same reason: a file
    with three amount-shaped columns and no clock is not a transaction table.
    """
    inferred = infer_targets(headers, columns, profile)
    if not inferred:
        return 0.0, {}
    targets = {v["target"] for v in inferred.values()}
    has_time = any(t in targets for t in
                   ("timestamp_start", "datetime_col", "date_col", "timestamp_end"))
    has_subject = any(t in targets for t in
                      ("account_no", "amount", "debit", "credit", "entity_phone",
                       "phone", "msisdn", "caller", "imei", "imsi",
                       "ip_public", "ip_private"))
    if not (has_time and has_subject):
        return 0.0, {}
    fields = profile_targets(profile)
    coverage = len(targets) / max(len(fields), 1)
    mean_conf = sum(v["confidence"] for v in inferred.values()) / len(inferred)
    return round(min(coverage * mean_conf * 1.6, 0.54), 3), inferred
