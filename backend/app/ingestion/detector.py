"""Type / format / profile detection (FR-4, Doc 04 DP-1..3).

Given a file, decide:
  - format: xlsx | csv | pdf
  - source type + profile: which mapping profile best matches the headers, with a
    confidence score. Below the configured threshold -> flagged for manual mapping.
"""

from __future__ import annotations

from pathlib import Path

from ..core import config
from . import value_typer

FORMAT_BY_EXT = {
    ".xlsx": "xlsx", ".xls": "xlsx", ".csv": "csv", ".txt": "csv", ".pdf": "pdf",
    ".docx": "docx",
}

# Leading bytes that identify a container regardless of what the file is named.
_MAGIC_ZIP = b"PK\x03\x04"      # xlsx / docx (both are ZIP)
_MAGIC_OLE2 = b"\xd0\xcf\x11\xe0"  # legacy .xls / .doc
_MAGIC_PDF = b"%PDF"
# AppleDouble sidecar ("._name") written when copying from macOS to a non-HFS volume.
_MAGIC_APPLEDOUBLE = b"\x00\x05\x16\x07"


def sniff_container(path: str) -> str | None:
    """Identify a file by its leading bytes: 'zip' | 'ole2' | 'pdf' | 'appledouble' | 'text'.

    Returns None if the file can't be read. Extensions lie constantly in real case
    material — evidence arrives as .xls that is really xlsx, .xlsx that is really an
    AppleDouble stub, and .xls that is really a fixed-width text report — so the bytes
    decide the parser and the extension only breaks ties.
    """
    try:
        with Path(path).open("rb") as fh:
            head = fh.read(8)
    except OSError:
        return None
    if head.startswith(_MAGIC_ZIP):
        return "zip"
    if head.startswith(_MAGIC_OLE2):
        return "ole2"
    if head.startswith(_MAGIC_PDF):
        return "pdf"
    if head.startswith(_MAGIC_APPLEDOUBLE):
        return "appledouble"
    return "text"


def detect_format(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext not in FORMAT_BY_EXT:
        raise ValueError(f"Unsupported file format: {ext}")

    by_ext = FORMAT_BY_EXT[ext]
    kind = sniff_container(path)
    if kind is None:
        return by_ext

    if kind == "appledouble":
        raise ValueError("AppleDouble resource fork, not a data file")
    if kind == "pdf":
        return "pdf"
    if kind == "zip":
        # Both xlsx and docx are ZIP archives; only the extension separates them.
        return "docx" if ext == ".docx" else "xlsx"
    if kind == "ole2":
        # Legacy Excel — pandas dispatches to xlrd. A legacy .doc also lands here and
        # will fail in the reader, which is reported as a per-file reject.
        return "xlsx"
    # Plain text: trust the extension for csv/txt, otherwise treat as delimited text
    # (a .xls that is really a text report parses as one column and is rejected cleanly,
    # rather than blowing up the Excel reader with an opaque engine error).
    return by_ext if by_ext in ("csv", "pdf") else "csv"


def _profile_aliases(profile: dict) -> set[str]:
    aliases: set[str] = set()
    for spec in profile.get("field_map", {}).values():
        for a in spec.get("aliases", []):
            aliases.add(a.strip().lower())
    return aliases


#: Canonical targets that make a table unambiguously a transaction/event record.
#: A mappability fallback needs a time anchor plus something to hang it on.
_ANCHOR_TIME = ("timestamp_start", "datetime_col", "date_col")
_ANCHOR_SUBJECT = ("account_no", "amount", "debit", "credit", "phone", "msisdn",
                   "caller", "called", "ip", "imei", "imsi")

#: Distinct canonical targets a profile must map before it may claim a file whose
#: headers miss every `required_any` token.
_FALLBACK_MIN_TARGETS = 3

#: Ceiling for a fallback match. Kept under `auto_detect_threshold()` so such a file is
#: always flagged `needs_manual_mapping`, and so any profile that matched properly wins.
_FALLBACK_MAX_CONFIDENCE = 0.49


def _mapped_targets(headers_set: set[str], profile: dict) -> list[str]:
    out = []
    for target, spec in profile.get("field_map", {}).items():
        aliases = {a.strip().lower() for a in spec.get("aliases", [])}
        if aliases & headers_set:
            out.append(target)
    return out


def _fallback_score(hset: set[str], profile: dict) -> float:
    """Score a profile that failed `required_any` but can still map the file.

    `match.required_any` and `field_map.aliases` are two independent lists that must
    agree, and they drift: a real statement headed
    `Trans Date and Time | Transaction Details | Debit | Credit | Balance` maps six
    canonical targets cleanly, yet scored 0.0 because `required_any` wanted the exact
    string "debit amount". The file was fully parseable and the profile refused it.

    Rather than keep patching tokens — the same drift returns with the next bank — a
    profile may claim a file it can demonstrably map. The bar is deliberately high (a
    time anchor, a subject, and several targets) and the confidence deliberately low, so
    this only ever *adds* recognition and never outranks a genuine match.
    """
    targets = _mapped_targets(hset, profile)
    if len(targets) < _FALLBACK_MIN_TARGETS:
        return 0.0
    if not any(t in targets for t in _ANCHOR_TIME):
        return 0.0
    if not any(t in targets for t in _ANCHOR_SUBJECT):
        return 0.0
    fields = profile.get("field_map", {})
    return min(len(targets) / len(fields), _FALLBACK_MAX_CONFIDENCE)


def score_profile(headers: list[str], profile: dict) -> float:
    """Fraction of profile *fields* matched by the file headers (0..1).

    A field counts as matched if ANY of its aliases appears in the headers, so a
    field with many spelling variants isn't penalized. A `match.required_any` header
    must be present or the score is zeroed, so an IPDR file is never mistaken for a
    CDR file just because both carry IMEI.
    """
    hset = {h.strip().lower() for h in headers if h}
    # `match` lives under the `profile:` block in every profile YAML. Reading it from the
    # top level silently returned {} for all of them, so this gate never fired and the
    # exact failure it exists to prevent was live: real TRAI IPDR exports were scoring as
    # cdr_vodafone_idea purely on shared IMEI/IMSI columns, and were normalized as CALL
    # events. The top-level lookup is kept as a fallback for flat profile dicts.
    match = profile.get("profile", {}).get("match") or profile.get("match", {})

    # required_all was declared in the schema but never enforced. It stays a hard gate:
    # unlike required_any it expresses "this shape is mandatory", so no fallback applies.
    req_all = [a.strip().lower() for a in match.get("required_all", [])]
    if req_all and not all(a in hset for a in req_all):
        return 0.0

    req_any = [a.strip().lower() for a in match.get("required_any", [])]
    if req_any and not any(a in hset for a in req_any):
        return _fallback_score(hset, profile)

    fields = profile.get("field_map", {})
    if not fields:
        return 0.0
    matched = 0
    for spec in fields.values():
        aliases = {a.strip().lower() for a in spec.get("aliases", [])}
        if aliases & hset:
            matched += 1
    return matched / len(fields)


def detect_profile(headers: list[str], columns: dict[str, list] | None = None) -> dict:
    """Return best-matching profile with confidence + source type across all groups.

    `columns` is {header: [values...]} for the same table. When supplied, the file's own
    values are used as a second, independent line of evidence — see `value_typer` for the
    reasoning. It is used two ways, both strictly additive:

      1. as a **last-resort claim** when no profile matched on headers at all. This is the
         file-level drop: an unmatched file gets `source_type=None` and normalization
         rejects it whole, so a bank with unfamiliar column spellings loses every row.
      2. as a **gap filler** on whichever profile wins, for canonical targets its own
         aliases did not resolve. This is the row-level drop: `_norm_bank` returns None
         when it has no timestamp or no account, and both are highly recognizable from
         values regardless of what the column is called.

    Header matching always wins where it succeeds; nothing here can overwrite it.
    """
    best = {"profile": None, "confidence": 0.0, "source": None}
    for group, plist in config.profiles().items():
        for profile in plist:
            conf = score_profile(headers, profile)
            if conf > best["confidence"]:
                best = {
                    "profile": profile,
                    "confidence": round(conf, 3),
                    "source": profile.get("profile", {}).get("source"),
                }

    value_map: dict = {}
    if columns and value_typer.enabled():
        if best["profile"] is None or best["confidence"] == 0.0:
            # (1) nothing claimed this file on names. Ask the values instead.
            for _group, plist in config.profiles().items():
                for profile in plist:
                    vconf, inferred = value_typer.value_profile_score(
                        headers, columns, profile)
                    if vconf > best["confidence"]:
                        best = {
                            "profile": profile,
                            "confidence": vconf,
                            "source": profile.get("profile", {}).get("source"),
                        }
                        value_map = inferred
        if best["profile"] is not None and not value_map:
            # (2) fill only what the winning profile's aliases left unmapped.
            hset = {h.strip().lower() for h in headers if h}
            value_map = value_typer.infer_targets(
                headers, columns, best["profile"],
                already_mapped=set(_mapped_targets(hset, best["profile"])))

    best["value_map"] = value_map
    best["needs_manual_mapping"] = best["confidence"] < config.auto_detect_threshold()
    return best
