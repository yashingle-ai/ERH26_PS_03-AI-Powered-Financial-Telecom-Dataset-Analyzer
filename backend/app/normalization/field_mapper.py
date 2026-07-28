"""Field mapper — raw record columns -> canonical field targets via profile aliases (FR-4)."""

from __future__ import annotations

import re


def _norm_header(value: str) -> str:
    """Collapse PDF/OCR header noise so aliases still match.

    NCRP complaint PDFs embed newlines inside column titles
    (`Account No./ (Wallet\\n/PG/PA) ID`). Exact string match against the profile
    then fails and every row is rejected for "missing timestamp / primary".
    """
    return re.sub(r"\s+", " ", str(value).strip().lower())


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

    One header may also feed multiple targets (e.g. Target/A → entity_phone and
    target_phone). Aliases that appear under several field_map entries are applied
    to every matching target.
    """
    # alias -> list of (target, rank) so shared headers can fill several fields
    idx: dict[str, list[tuple[str, int]]] = {}
    for target, spec in profile.get("field_map", {}).items():
        for position, alias in enumerate(spec.get("aliases", [])):
            key = _norm_header(alias)
            idx.setdefault(key, []).append((target, position))

    out: dict = {}
    chosen: dict[str, tuple[bool, int]] = {}     # target -> (is_empty, alias rank)

    for header, value in raw.items():
        if header == "_provenance":
            continue
        key = _norm_header(header)
        targets = idx.get(key) or []
        if not targets:
            continue
        if isinstance(value, str):
            value = value.strip().strip("'\"")
        for target, rank in targets:
            candidate = (value is None or value == "", rank)
            if target not in chosen or candidate < chosen[target]:
                chosen[target] = candidate
                out[target] = value
    return out


def _alias_index(profile: dict) -> dict[str, str]:
    """Map normalized alias -> canonical target (first declared wins). Kept for tests."""
    idx: dict[str, str] = {}
    for target, spec in profile.get("field_map", {}).items():
        for alias in spec.get("aliases", []):
            idx.setdefault(_norm_header(alias), target)
    return idx


def _alias_rank(profile: dict) -> dict[str, int]:
    """Map normalized alias -> its position in the profile's alias list."""
    rank: dict[str, int] = {}
    for spec in profile.get("field_map", {}).values():
        for position, alias in enumerate(spec.get("aliases", [])):
            rank.setdefault(_norm_header(alias), position)
    return rank
