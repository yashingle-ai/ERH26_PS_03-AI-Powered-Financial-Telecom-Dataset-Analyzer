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
}


def detect_format(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext not in FORMAT_BY_EXT:
        raise ValueError(f"Unsupported file format: {ext}")
    return FORMAT_BY_EXT[ext]


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
    match = profile.get("match", {})
    req_any = [a.strip().lower() for a in match.get("required_any", [])]
    if req_any and not any(a in hset for a in req_any):
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
