"""Analyst-supplied entity mapping (KYC / CAF bridge) — review follow-up.

Cross-domain correlation (call+IP+transfer) needs a shared identifier linking a bank
account (or wallet) to a phone. Real structured exports often lack it, but investigators
hold that mapping (KYC / CAF / registered-mobile). Drop an `entity_map.csv` in the dataset
folder and the pipeline will merge the mapped identifiers into one entity, enabling
cross-domain fusion — no code change.

Supported CSV shapes (header row required):
  1. Wide:    account_no, phone[, wallet, upi_id, imei, imsi]   (one row per subject)
  2. Generic: type_a, value_a, type_b, value_b                  (one row per link)

Each mapping becomes a LINK pseudo-event whose co-occurring identifiers merge in entity
resolution. LINK events carry no timestamp and are excluded from timeline/detection.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..core.logging_config import get_logger
from ..normalization import normalizers as nz

log = get_logger(__name__)

_WIDE_TYPES = {"account_no": "ACCOUNT_NO", "phone": "PHONE", "wallet": "ACCOUNT_NO",
               "upi_id": "UPI_ID", "imei": "IMEI", "imsi": "IMSI"}


def _norm_id(id_type: str, value: str):
    value = (value or "").strip()
    if not value:
        return None
    if id_type == "PHONE":
        value = nz.phone(value) or value
    return (id_type, value)


def load_link_events(input_dir: str, filename: str = "entity_map.csv") -> list[dict]:
    path = Path(input_dir) / filename
    if not path.exists():
        return []
    links: list[dict] = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        # Skip `#` comments and blank lines. This file is filled in by hand by a case
        # officer, so it will carry notes — and a commented instruction parsed as a data row
        # would enter entity resolution as an identifier.
        reader = csv.DictReader(
            ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#"))
        cols = {c.strip().lower(): c for c in (reader.fieldnames or [])}
        generic = {"type_a", "value_a", "type_b", "value_b"} <= set(cols)
        for row in reader:
            ids: list = []
            if generic:
                a = _norm_id(row[cols["type_a"]].strip().upper(), row[cols["value_a"]])
                b = _norm_id(row[cols["type_b"]].strip().upper(), row[cols["value_b"]])
                ids = [x for x in (a, b) if x]
            else:
                for col_l, id_type in _WIDE_TYPES.items():
                    if col_l in cols and row.get(cols[col_l]):
                        nid = _norm_id(id_type, row[cols[col_l]])
                        if nid:
                            ids.append(nid)
            if len(ids) >= 2:
                links.append({
                    "event_type": "LINK", "timestamp_start": None, "timestamp_end": None,
                    "amount": None, "direction": None,
                    "primary": ids[0], "counterparty": None, "own_identifiers": ids,
                    "attributes": {"source": "entity_map"}, "provenance": {"source_file": filename},
                })
    log.info("loaded %d KYC/entity-map links from %s", len(links), path)
    return links
