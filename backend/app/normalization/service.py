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


def _bank_amount_direction(mapped) -> tuple[float | None, str | None]:
    """Resolve amount + direction from debit/credit columns or a signed Amount.

    Core-banking statements use separate debit/credit columns. Exchange / P2P
    wallet ledgers ship a single signed `Amount` (`-19` withdrawal, `0.10`
    deposit). Without the signed path those ledgers survived mapping then lost
    the value, or were rejected earlier when the account/timestamp aliases were
    also missing.
    """
    debit = nz.amount(mapped.get("debit"))
    credit = nz.amount(mapped.get("credit"))
    if debit:
        return debit, "DEBIT"
    if credit:
        return credit, "CREDIT"
    signed = nz.amount(mapped.get("amount"))
    if signed is None:
        return None, None
    if signed < 0:
        return abs(signed), "DEBIT"
    return signed, "CREDIT"


def _bank_asset(mapped) -> str:
    """INR by default; non-INR Currency columns (USDT/USDC/…) become CRYPTO:TOKEN."""
    currency = str(mapped.get("attributes.currency") or "").strip().upper()
    if currency and currency not in {"INR", "RS", "INR.", "RUPEE", "RUPEES"}:
        return f"CRYPTO:{currency}"
    return "INR"


def _norm_bank(mapped, identity, profile, prov, source_tz="IST") -> dict | None:
    ts = _event_time(mapped, source_tz) or nz.parse_dt(mapped.get("timestamp_start"), source_tz)
    # B4: account may be a per-row column (SOA/ICORE) or a header-block identity.
    # NCRP cells need cleaning (`-:3995…`, `acct\\nLayer : 1`) before they are merge keys.
    acct = nz.account_no(mapped.get("account_no")) or nz.account_no(identity.get("account_no"))
    if ts is None or not acct:
        return None
    amt, direction = _bank_amount_direction(mapped)

    narr = mapped.get("attributes.narration", "")
    mined = narration.mine(narr, profile)

    own = [("ACCOUNT_NO", acct)]
    # registered_mobile is the *header subject*'s phone. On NCRP complaint tables the
    # header subject is often the complainant while row accounts are mule layers —
    # attaching that phone to every row would falsely merge victim↔mule. Only bridge
    # when the event account is the header account (real statements / subject KYC).
    mob = nz.phone(identity.get("registered_mobile"))
    header_acct = nz.account_no(identity.get("account_no"))
    if mob and header_acct and acct == header_acct:
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

    currency = str(mapped.get("attributes.currency") or "").strip() or None
    return {
        "event_type": "TRANSACTION",
        "timestamp_start": ts, "timestamp_end": None,
        "amount": amt, "direction": direction,
        "primary": ("ACCOUNT_NO", acct),
        "counterparty": counterparty,
        "own_identifiers": own,
        "asset": _bank_asset(mapped),
        "attributes": {"narration": narr, "balance": nz.amount(mapped.get("attributes.balance")),
                       "ref_no": mapped.get("attributes.ref_no"), "mode": mined.get("mode"),
                       "holder": mapped.get("account_holder") or identity.get("account_holder"),
                       "currency": currency},
        "provenance": prov,
    }


def _msisdn_from_name(name: str) -> str | None:
    import re as _re
    m = _re.search(r"(?<!\d)([6-9]\d{9})(?!\d)", name or "")
    return nz.phone(m.group(1)) if m else None


def _clean_device_id(value) -> str | None:
    if value is None:
        return None
    import re as _re
    d = _re.sub(r"\D", "", str(value))
    return d if len(d) >= 14 else None


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

    # IMEI/IMSI on operator CDR belong to the *report target*, not every A-party.
    # Attach as merge keys only when A-party is that target: explicit target_phone
    # column, or MSISDN embedded in the filename (common LEA export naming).
    # Do not put Target/A aliases on both entity_phone and target_phone — field_mapper
    # keeps one alias→target and the overlap previously nullified entity_phone.
    own = [("PHONE", a)]
    subject = nz.phone(mapped.get("target_phone")) or _msisdn_from_name(
        str((prov or {}).get("source_file") or ""))
    if subject and a == subject:
        imei = _clean_device_id(mapped.get("imei"))
        imsi = _clean_device_id(mapped.get("imsi"))
        if imei:
            own.append(("IMEI", imei))
        if imsi:
            own.append(("IMSI", imsi))

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


def _ipv6_prefix64(addr: str | None) -> str | None:
    """Subscriber-scoped IPv6 network (first 4 hextets). None for IPv4 / unparseable."""
    if not addr or ":" not in str(addr):
        return None
    try:
        import ipaddress
        net = ipaddress.ip_network(f"{addr}/64", strict=False)
        return str(net.network_address)
    except ValueError:
        parts = str(addr).split(":")
        if len(parts) >= 4:
            return ":".join(parts[:4]) + "::"
        return None


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
        sub = _msisdn_from_name(prov.get("source_file", ""))
    pub = nz.ip(mapped.get("ip_public"))
    priv = nz.ip(mapped.get("ip_private"))
    if not sub and not pub and not priv:
        return None

    own = []
    if sub:
        own.append(("PHONE", sub))
    # Prefer public IP as the displayed address; still record private/source for /64 link.
    if pub:
        own.append(("IP", pub))
    elif priv:
        own.append(("IP", priv))
    imei = _clean_device_id(mapped.get("imei"))
    imsi = _clean_device_id(mapped.get("imsi"))
    if imei:
        own.append(("IMEI", imei))
    if imsi:
        own.append(("IMSI", imsi))

    primary = ("PHONE", sub) if sub else (("IP", pub) if pub else ("IP", priv))
    return {
        "event_type": "IP_SESSION",
        "timestamp_start": ts, "timestamp_end": end,
        "amount": None, "direction": None,
        "primary": primary,
        "counterparty": None,
        "own_identifiers": own,
        "asset": None,
        "attributes": {"public_ip": pub, "private_ip": priv,
                       "ip_version": mapped.get("attributes.ip_version"),
                       "port": mapped.get("attributes.port"),
                       "bytes_up": mapped.get("attributes.bytes_up"),
                       "bytes_down": mapped.get("attributes.bytes_down"),
                       "dest_ip": nz.ip(mapped.get("attributes.dest_ip"))},
        "provenance": prov,
    }


def enrich_ipdr_prefix_phones(events: list[dict]) -> int:
    """Attach MSISDN to IP-only IPDR rows that share an IPv6 /64 with a phone-bearing session.

    TRAI IPDR lists the delegated /64 as Source IP; IP-range exports list a host inside
    that /64. Without this pass the host rows stay IP-primary and never join the
    subscriber entity that already has the phone — so CALL+IP correlation cannot see them.
    Returns how many sessions were upgraded.
    """
    prefix_to_phone: dict[str, str] = {}
    for ev in events:
        if ev.get("event_type") != "IP_SESSION":
            continue
        phone = next((v for t, v in (ev.get("own_identifiers") or []) if t == "PHONE"), None)
        if not phone:
            continue
        attrs = ev.get("attributes") or {}
        for addr in (attrs.get("public_ip"), attrs.get("private_ip")):
            p64 = _ipv6_prefix64(addr)
            if p64:
                prefix_to_phone.setdefault(p64, phone)

    upgraded = 0
    for ev in events:
        if ev.get("event_type") != "IP_SESSION":
            continue
        if any(t == "PHONE" for t, _ in (ev.get("own_identifiers") or [])):
            continue
        attrs = ev.get("attributes") or {}
        phone = None
        for addr in (attrs.get("public_ip"), attrs.get("private_ip")):
            p64 = _ipv6_prefix64(addr)
            if p64 and p64 in prefix_to_phone:
                phone = prefix_to_phone[p64]
                break
        if not phone:
            continue
        own = list(ev.get("own_identifiers") or [])
        own.insert(0, ("PHONE", phone))
        ev["own_identifiers"] = own
        ev["primary"] = ("PHONE", phone)
        upgraded += 1
    return upgraded


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
            # A session is who, from where, to where, on which port, and when. Keying on
            # just (subscriber, public IP, start) collapsed every concurrent session of
            # one subscriber into a single event: TRAI exports repeat the MSISDN on every
            # row and often leave Public IP blank, so 37 of 75 real rows were dropped as
            # "duplicates" when they were distinct connections to different destinations.
            # Losing which destinations were contacted is losing the evidence itself.
            key = ("I", e.get("primary"), a.get("public_ip"), a.get("private_ip"),
                   a.get("port"), a.get("dest_ip"), t,
                   e["timestamp_end"].isoformat() if e.get("timestamp_end") else "")
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
        no_time = no_identifier = 0
        for raw in pf.records:
            prov = {**raw.get("_provenance", {}), "profile": pf.profile_id}
            mapped = field_mapper.map_record(raw, profile, getattr(pf, "value_map", None))
            ev = (fn(mapped, pf.header_identity, profile, prov, source_tz)
                  if pf.source_type == "BANK" else fn(mapped, prov, source_tz))
            if ev is None:
                # WHICH precondition failed. All three normalisers gate on a timestamp and then on
                # an identifier, and the two failures want opposite responses: a row with no
                # timestamp can never become an event however well it is mapped — it is reference
                # data — while a row that HAS a time and lost its identifier is a mapping gap worth
                # closing. Reported as one reason this was 60,325 rows on `fir-65-2024`, 16.5% of
                # everything parsed, with no way to tell which half was actionable.
                #
                # Recomputed here rather than returned from the normalisers, so their signatures
                # and behaviour are untouched: this is a diagnosis of a decision already made.
                if _event_time(mapped, source_tz) is None:
                    no_time += 1
                else:
                    no_identifier += 1
            else:
                events.append(ev)
        base = {"file": pf.path, "source_type": pf.source_type,
                "profile": pf.profile_id, "rows": len(pf.records)}
        if no_time:
            rejects.append({**base, "rejected": no_time,
                            "reason": "row has no timestamp — cannot become an event"})
        if no_identifier:
            rejects.append({**base, "rejected": no_identifier,
                            "reason": "row has a timestamp but no mapped primary identifier"})

    upgraded = enrich_ipdr_prefix_phones(events)
    if upgraded:
        from ..core.logging_config import get_logger
        get_logger(__name__).info(
            "IPDR /64 enrichment: attached MSISDN to %d IP-only sessions", upgraded)

    events, dup = _dedupe(events)
    if dup:
        # Not lost evidence: these rows parsed successfully and were then recognised as
        # the same event arriving twice (a CDR shipped as both .csv and "- Reports.xlsx").
        # Counting them beside rows that could not be read overstates the gap — on the
        # real case they were roughly a third of `rejected_rows`. `rows` is set so the
        # entry cannot be bucketed as an infinite rejection rate.
        rejects.append({"file": "(cross-file)", "reason": "duplicate events removed",
                        "rows": dup, "rejected": dup, "evidentiary": False})
    return events, rejects
