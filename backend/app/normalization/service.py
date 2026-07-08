"""Normalization service (Phase 2) — ParsedFile -> canonical event dicts.

Maps each raw record into the canonical model (Doc 06 §4), normalizes values, mines
bank narrations, and records the identifiers that belong to the SAME entity (for
entity resolution). Provenance is preserved on every event (NFR-7).

A canonical event dict:
  {
    event_type, timestamp_start, timestamp_end, amount, direction,
    primary: (id_type, id_value),            # entity the event belongs to
    counterparty: (id_type, id_value)|None,
    own_identifiers: [(id_type, id_value)],  # co-occurring identifiers of primary entity
    attributes: {...}, provenance: {...},
  }
"""

from __future__ import annotations

from . import field_mapper, narration
from . import normalizers as nz


def _direction_from_call_type(ct: str) -> str:
    ct = (ct or "").upper()
    if ct in ("MOC", "SMS-O", "OUT", "OUTGOING"):
        return "OUT"
    if ct in ("MTC", "SMS-T", "IN", "INCOMING"):
        return "IN"
    return "OUT"


def _norm_bank(mapped: dict, identity: dict, profile: dict, prov: dict) -> dict | None:
    ts = nz.parse_dt(mapped.get("timestamp_start"))
    acct = identity.get("account_no")
    if ts is None or not acct:
        return None
    debit = nz.amount(mapped.get("debit"))
    credit = nz.amount(mapped.get("credit"))
    if debit:
        amt, direction = debit, "DEBIT"
    elif credit:
        amt, direction = credit, "CREDIT"
    else:
        amt, direction = None, None

    narr = mapped.get("attributes.narration", "")
    mined = narration.mine(narr, profile)

    own = [("ACCOUNT_NO", acct)]
    mob = nz.phone(identity.get("registered_mobile"))
    if mob:
        own.append(("PHONE", mob))

    counterparty = None
    if mined.get("upi_id"):
        counterparty = ("UPI_ID", mined["upi_id"])
    elif mined.get("counterparty_name"):
        counterparty = ("BENEFICIARY", mined["counterparty_name"])

    return {
        "event_type": "TRANSACTION",
        "timestamp_start": ts, "timestamp_end": None,
        "amount": amt, "direction": direction,
        "primary": ("ACCOUNT_NO", acct),
        "counterparty": counterparty,
        "own_identifiers": own,
        "attributes": {"narration": narr, "balance": nz.amount(mapped.get("attributes.balance")),
                       "ref_no": mapped.get("attributes.ref_no"), "mode": mined.get("mode"),
                       "holder": identity.get("account_holder")},
        "provenance": prov,
    }


def _norm_cdr(mapped: dict, prov: dict) -> dict | None:
    ts = nz.parse_dt(mapped.get("timestamp_start"))
    a = nz.phone(mapped.get("entity_phone"))
    if ts is None or not a:
        return None
    b = nz.phone(mapped.get("counterparty_phone"))
    dur = mapped.get("attributes.duration")
    dur = int(float(dur)) if str(dur).strip() not in ("", "None") else None
    end = None
    if dur:
        from datetime import timedelta
        end = ts + timedelta(seconds=dur)

    own = [("PHONE", a)]
    if mapped.get("imei"):
        own.append(("IMEI", str(mapped["imei"]).strip()))
    if mapped.get("imsi"):
        own.append(("IMSI", str(mapped["imsi"]).strip()))

    return {
        "event_type": "CALL",
        "timestamp_start": ts, "timestamp_end": end,
        "amount": None, "direction": _direction_from_call_type(mapped.get("direction")),
        "primary": ("PHONE", a),
        "counterparty": ("PHONE", b) if b else None,
        "own_identifiers": own,
        "attributes": {"duration": dur, "call_type": mapped.get("direction"),
                       "cell_id": mapped.get("attributes.cell_id"),
                       "location": mapped.get("attributes.location")},
        "provenance": prov,
    }


def _norm_ipdr(mapped: dict, prov: dict) -> dict | None:
    ts = nz.parse_dt(mapped.get("timestamp_start"))
    sub = nz.phone(mapped.get("entity_phone"))
    if ts is None or not sub:
        return None
    end = nz.parse_dt(mapped.get("timestamp_end"))
    pub = nz.ip(mapped.get("ip_public"))

    own = [("PHONE", sub)]
    if pub:
        own.append(("IP", pub))
    if mapped.get("imei"):
        own.append(("IMEI", str(mapped["imei"]).strip()))
    if mapped.get("imsi"):
        own.append(("IMSI", str(mapped["imsi"]).strip()))

    return {
        "event_type": "IP_SESSION",
        "timestamp_start": ts, "timestamp_end": end,
        "amount": None, "direction": None,
        "primary": ("PHONE", sub),
        "counterparty": None,
        "own_identifiers": own,
        "attributes": {"public_ip": pub, "private_ip": nz.ip(mapped.get("ip_private")),
                       "port": mapped.get("attributes.port"),
                       "bytes_up": mapped.get("attributes.bytes_up"),
                       "bytes_down": mapped.get("attributes.bytes_down"),
                       "dest_ip": nz.ip(mapped.get("attributes.dest_ip"))},
        "provenance": prov,
    }


_NORMALIZERS = {"BANK": _norm_bank, "CDR": _norm_cdr, "IPDR": _norm_ipdr}


def normalize_parsed_files(parsed_files: list) -> tuple[list[dict], list[dict]]:
    events: list[dict] = []
    rejects: list[dict] = []
    for pf in parsed_files:
        if not pf.source_type or pf.source_type not in _NORMALIZERS:
            rejects.append({"file": pf.path, "reason": "unrecognized source type"})
            continue
        profile = {"narration_extract": {}}
        # find the actual profile dict (for narration patterns)
        from ..core import config
        for plist in config.profiles().values():
            for p in plist:
                if p.get("profile", {}).get("id") == pf.profile_id:
                    profile = p
        for raw in pf.records:
            prov = {**raw.get("_provenance", {}), "profile": pf.profile_id}
            mapped = field_mapper.map_record(raw, profile)
            fn = _NORMALIZERS[pf.source_type]
            ev = fn(mapped, pf.header_identity, profile, prov) if pf.source_type == "BANK" \
                else fn(mapped, prov)
            if ev is None:
                rejects.append({"file": pf.path, "row": prov.get("row"),
                                "reason": "missing timestamp or primary identifier"})
            else:
                events.append(ev)
    return events, rejects
