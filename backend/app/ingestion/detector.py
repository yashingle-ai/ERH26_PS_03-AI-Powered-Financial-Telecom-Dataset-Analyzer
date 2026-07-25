"""Type / format / profile detection (FR-4, Doc 04 DP-1..3).

Given a file, decide:
  - format: xlsx | csv | pdf
  - source type + profile: which mapping profile best matches the headers, with a
    confidence score. Below the configured threshold -> flagged for manual mapping.
"""

from __future__ import annotations

from pathlib import Path

from ..core import config

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

    req_any = [a.strip().lower() for a in match.get("required_any", [])]
    if req_any and not any(a in hset for a in req_any):
        return 0.0

    # required_all was declared in the schema but never enforced.
    req_all = [a.strip().lower() for a in match.get("required_all", [])]
    if req_all and not all(a in hset for a in req_all):
        return 0.0

    fields = profile.get("field_map", {})
    if not fields:
        return 0.0
    matched = 0
    for spec in fields.values():
        aliases = {a.strip().lower() for a in spec.get("aliases", [])}
        if aliases & hset:
            matched += 1
    return matched / len(fields)


def detect_profile(headers: list[str]) -> dict:
    """Return best-matching profile with confidence + source type across all groups."""
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
    best["needs_manual_mapping"] = best["confidence"] < config.auto_detect_threshold()
    return best
