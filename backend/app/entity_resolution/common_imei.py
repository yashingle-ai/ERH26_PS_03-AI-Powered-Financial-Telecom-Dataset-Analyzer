"""LEA Common-IMEI report → LINK events (handset ↔ phone / IPDR session).

Operators ship spreadsheets named like `CDR__*Common_IMEI_Report.xlsx` whose
columns are the MSISDNs under study and whose `Number` column is an IMEI. A
`Yes` cell means that handset was used on that number — exactly the KYC-style
bridge entity resolution already consumes via `entity_map.csv`.

IPDR variants use session-file stems as columns instead of phones; when those
stems appear in already-normalized IP_SESSION provenance we resolve them to
the session's MSISDN and emit IMEI↔PHONE links.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..core.logging_config import get_logger
from ..ingestion import service as ing
from ..normalization import normalizers as nz

log = get_logger(__name__)

_YES = {"yes", "y", "1", "true"}
_SKIP_COLS = {"number", "count", "handset details", "handset", "remarks", "s no", "s.no", "sno"}


def _digits(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _imei(value: str) -> str | None:
    d = _digits(value)
    # IMEI is 14–16 digits in these exports (check-digit sometimes dropped/extra).
    if 14 <= len(d) <= 16:
        return d
    return None


def _link(ids: list, source_file: str) -> dict:
    return {
        "event_type": "LINK", "timestamp_start": None, "timestamp_end": None,
        "amount": None, "direction": None,
        "primary": ids[0], "counterparty": None, "own_identifiers": ids,
        "attributes": {"source": "common_imei_report"},
        "provenance": {"source_file": source_file},
    }


def _session_to_phone(events: list[dict]) -> dict[str, str]:
    """Map IPDR provenance file stems / fragments → MSISDN."""
    out: dict[str, str] = {}
    for ev in events:
        if ev.get("event_type") != "IP_SESSION":
            continue
        phone = next((v for t, v in (ev.get("own_identifiers") or []) if t == "PHONE"), None)
        if not phone:
            prim = ev.get("primary")
            if prim and prim[0] == "PHONE":
                phone = prim[1]
        if not phone:
            continue
        src = str((ev.get("provenance") or {}).get("source_file") or "")
        # provenance may be "zip → member.csv" — take every path-like fragment
        for part in re.split(r"[→>/\\]", src):
            stem = Path(part.strip()).stem
            if not stem:
                continue
            out[stem] = phone
            out[stem.lower()] = phone
            # TRAI member names are long; also index the leading id token
            head = stem.split("_")[0]
            if head.isdigit() and len(head) >= 6:
                out[head] = phone
    return out


def _links_from_grid(path: Path, headers: list, records: list,
                     session_phones: dict[str, str]) -> list[dict]:
    if not headers or not records:
        return []
    cols = [str(h) for h in headers]
    # phone columns: exact 10-digit Indian MSISDN headers
    phone_cols = [c for c in cols if re.fullmatch(r"\d{10}", c or "")]
    # session columns: everything else that isn't metadata
    session_cols = [
        c for c in cols
        if c.lower().strip() not in _SKIP_COLS and c not in phone_cols
    ]
    links: list[dict] = []
    src = path.name
    for row in records:
        imei = _imei(row.get("Number") or row.get("number") or "")
        if not imei:
            continue
        for col in phone_cols:
            if str(row.get(col) or "").strip().lower() not in _YES:
                continue
            phone = nz.phone(col)
            if phone:
                links.append(_link([("IMEI", imei), ("PHONE", phone)], src))
        for col in session_cols:
            if str(row.get(col) or "").strip().lower() not in _YES:
                continue
            phone = session_phones.get(col) or session_phones.get(col.lower())
            if not phone:
                # column may be truncated in Excel; match by prefix / containment
                for stem, ph in session_phones.items():
                    if col.startswith(stem) or stem.startswith(col) or col in stem:
                        phone = ph
                        break
            if phone:
                links.append(_link([("IMEI", imei), ("PHONE", phone)], src))
    return links


def load_common_imei_links(input_dir: str, events: list[dict] | None = None) -> list[dict]:
    """Walk the case tree for Common IMEI reports and emit LINK events."""
    root = Path(input_dir)
    if not root.exists():
        return []
    session_phones = _session_to_phone(events or [])
    links: list[dict] = []
    seen: set[tuple] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        # NARROW ON PURPOSE. Operators ship a whole `Common_*_Report` family in the same folder
        # and the others are not identity evidence:
        #
        #   Common_IMEI_Report        Number=IMEI,    columns=MSISDN   -> identity. This one.
        #   IPDR_-_Common_IMEI_Report Number=IMEI,    columns=session  -> identity. This one.
        #   Common_A_B_Report         Number=MSISDN,  columns=MSISDN   -> a COMMS edge, and its
        #       Number column also carries SMS sender IDs (`VG-ViCARE`), which are not subscribers.
        #       Two A-parties sharing a B-party says nothing about who owns what.
        #   Common_First_Cell_ID_*    Number=CELL ID, columns=MSISDN   -> a LOCATION edge. Merging
        #       a tower into a phone entity would fuse every handset that ever used that cell.
        #
        # Matching `common_*_report` instead of `common_imei` looks like five free files and is in
        # fact rule 3 — fabricating identity links. Widen this only with the column semantics of
        # the new report established first; `test_common_imei_refuses.py` pins the refusals.
        if "common_imei" not in name and "common imei" not in name:
            continue
        if path.suffix.lower() not in {".xlsx", ".xls", ".csv"}:
            continue
        try:
            parsed = ing.parse_file_multi(str(path))
        except Exception as e:
            log.warning("common IMEI report unreadable %s: %s", path.name, e)
            continue
        for pf in parsed:
            for link in _links_from_grid(path, pf.headers or [], pf.records, session_phones):
                key = tuple(sorted(link["own_identifiers"]))
                if key in seen:
                    continue
                seen.add(key)
                links.append(link)
    if links:
        log.info("loaded %d Common-IMEI links from %s", len(links), root)
    return links
