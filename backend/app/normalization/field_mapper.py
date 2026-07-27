"""Field mapper — raw record columns -> canonical field targets via profile aliases (FR-4)."""

from __future__ import annotations


def _alias_index(profile: dict) -> dict[str, str]:
    """Map lowercased alias -> canonical target key."""
    idx: dict[str, str] = {}
    for target, spec in profile.get("field_map", {}).items():
        for alias in spec.get("aliases", []):
            idx[alias.strip().lower()] = target
    return idx


def _alias_rank(profile: dict) -> dict[str, int]:
    """Map lowercased alias -> its position in the profile's alias list.

    A profile lists aliases best-first, so position is a preference order.
    """
    rank: dict[str, int] = {}
    for spec in profile.get("field_map", {}).values():
        for position, alias in enumerate(spec.get("aliases", [])):
            rank[alias.strip().lower()] = position
    return rank


def map_record(raw: dict, profile: dict) -> dict:
    """Return {canonical_target: value} for one raw record using the profile aliases.

    Several columns often claim the same target — an ICORE statement carries
    `Tran_Date`, `pstd_dt` and `value_dt`, all timestamps. Resolving that by raw
    column order means whichever happens to sit rightmost wins, which is
    arbitrary: on real statements `pstd_dt` (`11DEC2019:09:07:02`) overwrote a
    clean `Tran_Date` and took 95% of bank rows down with it.

    Two rules instead, in order:
      1. a non-empty value always beats an empty one;
      2. among non-empty values, the alias the profile lists first wins.
    """
    idx = _alias_index(profile)
    rank = _alias_rank(profile)
    out: dict = {}
    chosen: dict[str, tuple[bool, int]] = {}     # target -> (is_empty, alias rank)

    for header, value in raw.items():
        if header == "_provenance":
            continue
        key = str(header).strip().lower()
        target = idx.get(key)
        if not target:
            continue
        # strip surrounding quotes real exports wrap around values ('919099102222')
        if isinstance(value, str):
            value = value.strip().strip("'\"")
        candidate = (value is None or value == "", rank.get(key, 10_000))
        if target not in chosen or candidate < chosen[target]:
            chosen[target] = candidate
            out[target] = value
    return out
