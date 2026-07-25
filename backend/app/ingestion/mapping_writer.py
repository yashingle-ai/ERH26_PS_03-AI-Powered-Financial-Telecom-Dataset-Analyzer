"""Manual column-mapping (B5) — persist an analyst-defined profile.

When a file is flagged `needs_manual_mapping`, the analyst maps its columns to canonical
targets in the UI; this writes a profile YAML under config/profiles/<group>/, after which
the file (and any like it) auto-detects and parses on the next run — no code change.
"""

from __future__ import annotations

import re

import yaml

from ..core import config

_GROUP_BY_SOURCE = {"BANK": "banks", "CDR": "cdr", "IPDR": "ipdr", "CRYPTO": "crypto"}


def save_profile(profile_id: str, source: str, event_type: str,
                 field_aliases: dict[str, list[str]], required_any: list[str]) -> str:
    """field_aliases: {canonical_target: [source column names]}. Returns the written path."""
    group = _GROUP_BY_SOURCE.get(source.upper(), "misc")
    safe = re.sub(r"[^a-z0-9_]+", "_", profile_id.lower()).strip("_") or "custom"
    doc = {
        "profile": {"id": safe, "source": source.upper(), "event_type": event_type.upper(),
                    "match": {"required_any": required_any, "required_all": []}},
        "field_map": {tgt: {"aliases": als} for tgt, als in field_aliases.items() if als},
    }
    out_dir = config.CONFIG_DIR / "profiles" / group
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{safe}.yaml"
    with open(path, "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True)
    config.profiles.cache_clear()          # reload profiles so it takes effect immediately
    return str(path)


# Canonical targets the UI offers per source type
CANONICAL_TARGETS = {
    "BANK": ["timestamp_start", "attributes.narration", "debit", "credit",
             "attributes.balance", "attributes.ref_no", "account_no", "account_holder"],
    "CDR": ["entity_phone", "counterparty_phone", "date_col", "time_col",
            "attributes.duration", "direction", "imei", "imsi",
            "attributes.cell_id", "attributes.location"],
    "IPDR": ["entity_phone", "ip_public", "date_col", "time_col",
             "end_date_col", "end_time_col"],
    "CRYPTO": ["from_addr", "to_addr", "amount", "datetime_col", "attributes.token"],
}
