"""Field mapper — raw record columns -> canonical field targets via profile aliases (FR-4)."""

from __future__ import annotations


def _alias_index(profile: dict) -> dict[str, str]:
    """Map lowercased alias -> canonical target key."""
    idx: dict[str, str] = {}
    for target, spec in profile.get("field_map", {}).items():
        for alias in spec.get("aliases", []):
            idx[alias.strip().lower()] = target
    return idx


def map_record(raw: dict, profile: dict) -> dict:
    """Return {canonical_target: value} for one raw record using the profile aliases."""
    idx = _alias_index(profile)
    out: dict = {}
    for header, value in raw.items():
        if header == "_provenance":
            continue
        target = idx.get(str(header).strip().lower())
        if target:
            out[target] = value
    return out
