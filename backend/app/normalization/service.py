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
    if any(k in ct for k in ("MOC", "SMS-O", "OUT", "OUTGOING", "A_OUT", "B_OUT")):
        return "OUT"
    if any(k in ct for k in ("MTC", "SMS-T", "IN", "INCOMING", "A_IN", "B_IN")):
        return "IN"
    return "OUT"


def _event_time(mapped: dict, source_tz: str = "IST"):
    """Resolve a timestamp from either a single datetime column or split date+time."""
    if mapped.get("datetime_col"):
        return nz.parse_dt(mapped["datetime_col"], source_tz)
    if mapped.get("timestamp_start"):
        return nz.parse_dt(mapped["timestamp_start"], source_tz)
    if mapped.get("date_col"):
        return nz.combine_date_time(mapped.get("date_col"), mapped.get("time_col"), source_tz)
    return None


def _norm_bank(mapped, identity, profile, prov, source_tz="IST") -> dict | None:
    ts = _event_time(mapped, source_tz) or nz.parse_dt(mapped.get("timestamp_start"), source_tz)
    # B4: account may be a per-row column (SOA/ICORE) or a header-block identity.
    acct = str(mapped.get("account_no") or identity.get("account_no") or "").strip()
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

    # Prefer a phone counterparty (bridges bank<->telecom, PHONE is a merge key) when the
    # narration carries a phone-based UPI VPA; else fall back to UPI VPA / beneficiary name.
    counterparty = None
    cp_phone = nz.phone(mined.get("counterparty_phone")) if mined.get("counterparty_phone") else None
    if cp_phone:
        counterparty = ("PHONE", cp_phone)
    elif mined.get("counterparty_account"):        # C4: account-VPA links to payee account
        counterparty = ("ACCOUNT_NO", mined["counterparty_account"])
    elif mined.get("upi_id"):
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
        "asset": "INR",
        "attributes": {"narration": narr, "balance": nz.amount(mapped.get("attributes.balance")),
                       "ref_no": mapped.get("attributes.ref_no"), "mode": mined.get("mode"),
                       "holder": mapped.get("account_holder") or identity.get("account_holder")},
        "provenance": prov,
    }


def _norm_cdr(mapped, prov, source_tz="IST") -> dict | None:
    ts = _event_time(mapped, source_tz)
    a = nz.phone(mapped.get("entity_phone"))
    if ts is None or not a:
        return None
    b = nz.phone(mapped.get("counterparty_phone"))
    dur = mapped.get("attributes.duration")
    try:
        dur = int(float(str(dur).strip())) if str(dur).strip() not in ("", "None", "nan") else None
    except ValueError:
        dur = None
    end = None
    if dur:
        from datetime import timedelta
        end = ts + timedelta(seconds=dur)

    # NOTE: in operator CDR the IMEI/IMSI columns belong to the *target subscriber* of the
    # report, not necessarily this row's A-party (the target may be the called party). So we
    # keep IMEI/IMSI as attributes only and do NOT use them to merge entities — otherwise
    # every number that ever called the target collapses into one entity.
    own = [("PHONE", a)]

    return {
        "event_type": "CALL",
        "timestamp_start": ts, "timestamp_end": end,
        "amount": None, "direction": _direction_from_call_type(mapped.get("direction")),
        "primary": ("PHONE", a),
        "counterparty": ("PHONE", b) if b else None,
        "own_identifiers": own,
        "asset": None,
        "attributes": {"duration": dur, "call_type": mapped.get("direction"),
                       "cell_id": mapped.get("attributes.cell_id"),
                       "location": mapped.get("attributes.location"),
                       "imei": mapped.get("imei"), "imsi": mapped.get("imsi"),
                       "circle": mapped.get("attributes.circle")},
        "provenance": prov,
    }


def _norm_ipdr(mapped, prov, source_tz="IST") -> dict | None:
    ts = _event_time(mapped, source_tz)
    if ts is None:
        return None
    if mapped.get("end_date_col"):
        end = nz.combine_date_time(mapped.get("end_date_col"), mapped.get("end_time_col"), source_tz)
    else:
        end = nz.parse_dt(mapped.get("timestamp_end"), source_tz)
    sub = nz.phone(mapped.get("entity_phone"))       # may be absent in IP-range IPDR
    if not sub:
        # C2: derive subscriber MSISDN from the filename (e.g. "9099102222_...ipdr.xlsx")
        import re as _re
        m = _re.search(r"(?<!\d)([6-9]\d{9})(?!\d)", prov.get("source_file", ""))
        if m:
            sub = nz.phone(m.group(1))
    pub = nz.ip(mapped.get("ip_public"))
    if not sub and not pub:
        return None

    own = []
    if sub:
        own.append(("PHONE", sub))
    if pub:
        own.append(("IP", pub))
    if mapped.get("imei"):
        own.append(("IMEI", str(mapped["imei"]).strip()))
    if mapped.get("imsi"):
        own.append(("IMSI", str(mapped["imsi"]).strip()))

    primary = ("PHONE", sub) if sub else ("IP", pub)
    return {
        "event_type": "IP_SESSION",
        "timestamp_start": ts, "timestamp_end": end,
        "amount": None, "direction": None,
        "primary": primary,
        "counterparty": None,
        "own_identifiers": own,
        "asset": None,
        "attributes": {"public_ip": pub, "private_ip": nz.ip(mapped.get("ip_private")),
                       "ip_version": mapped.get("attributes.ip_version"),
                       "port": mapped.get("attributes.port"),
                       "bytes_up": mapped.get("attributes.bytes_up"),
                       "bytes_down": mapped.get("attributes.bytes_down"),
                       "dest_ip": nz.ip(mapped.get("attributes.dest_ip"))},
        "provenance": prov,
    }


def _norm_crypto(mapped, prov, source_tz="UTC") -> dict | None:
    """Crypto wallet transfer -> a single-sided money-flow TRANSACTION (from -> to)."""
    ts = _event_time(mapped, source_tz)
    frm = (mapped.get("from_addr") or "").strip()
    to = (mapped.get("to_addr") or "").strip()
    if ts is None or not frm or not to:
        return None
    amt = nz.amount(mapped.get("amount"))
    ref = mapped.get("attributes.txn_hash")
    token = mapped.get("attributes.token") or "CRYPTO"
    from ..core import config
    rate = config.crypto_rate_inr(token)          # A4: approximate INR valuation
    value_inr = round(amt * rate, 2) if (amt is not None and rate) else None
    return {
        "event_type": "TRANSACTION",
        "timestamp_start": ts, "timestamp_end": None,
        "amount": amt, "direction": "DEBIT",
        "primary": ("ACCOUNT_NO", frm),          # wallet address as the account
        "counterparty": ("ACCOUNT_NO", to),
        "own_identifiers": [("ACCOUNT_NO", frm)],
        "asset": f"CRYPTO:{token}",              # A3: crypto value kept separate from INR
        "attributes": {"asset": "CRYPTO", "token": token, "value_inr": value_inr,
                       "ref_no": ref, "status": mapped.get("attributes.status"),
                       "narration": f"CRYPTO {token} {frm}->{to}"},
        "provenance": prov,
    }


_NORMALIZERS = {"BANK": _norm_bank, "CDR": _norm_cdr, "IPDR": _norm_ipdr,
                "CRYPTO": _norm_crypto}


def _dedupe(events: list[dict]) -> tuple[list[dict], int]:
    """A2 fix: drop duplicate events (same data present in multiple files, e.g. a CDR that
    exists as both a raw .csv and a '- Reports.xlsx'). Natural key per event type."""
    seen: set = set()
    out: list[dict] = []
    dropped = 0
    for e in events:
        t = e["timestamp_start"].isoformat() if e.get("timestamp_start") else ""
        a = e.get("attributes") or {}
        if e["event_type"] == "TRANSACTION":
            key = ("T", e.get("primary"), e.get("counterparty"), e.get("amount"),
                   e.get("direction"), a.get("ref_no"), t)
        elif e["event_type"] == "CALL":
            key = ("C", e.get("primary"), e.get("counterparty"), t, a.get("duration"))
        else:  # IP_SESSION
            key = ("I", e.get("primary"), a.get("public_ip"), t)
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        out.append(e)
    return out, dropped


def normalize_parsed_files(parsed_files: list) -> tuple[list[dict], list[dict]]:
    from ..core import config
    events: list[dict] = []
    rejects: list[dict] = []
    profiles_by_id: dict = {}
    for plist in config.profiles().values():
        for p in plist:
            profiles_by_id[p.get("profile", {}).get("id")] = p

    for pf in parsed_files:
        if not pf.source_type or pf.source_type not in _NORMALIZERS:
            rejects.append({"file": pf.path, "reason": "unrecognized source type",
                            "rows": len(pf.records)})
            continue
        profile = profiles_by_id.get(pf.profile_id, {"narration_extract": {}})
        source_tz = profile.get("profile", {}).get("source_tz", "IST")
        fn = _NORMALIZERS[pf.source_type]
        file_rejects = 0
        for raw in pf.records:
            prov = {**raw.get("_provenance", {}), "profile": pf.profile_id}
            mapped = field_mapper.map_record(raw, profile)
            ev = (fn(mapped, pf.header_identity, profile, prov, source_tz)
                  if pf.source_type == "BANK" else fn(mapped, prov, source_tz))
            if ev is None:
                file_rejects += 1
            else:
                events.append(ev)
        if file_rejects:
            rejects.append({"file": pf.path, "source_type": pf.source_type,
                            "profile": pf.profile_id, "rows": len(pf.records),
                            "rejected": file_rejects,
                            "reason": "row missing timestamp / primary identifier"})

    events, dup = _dedupe(events)
    if dup:
        rejects.append({"file": "(cross-file)", "reason": "duplicate events removed",
                        "rejected": dup})
    return events, rejects
