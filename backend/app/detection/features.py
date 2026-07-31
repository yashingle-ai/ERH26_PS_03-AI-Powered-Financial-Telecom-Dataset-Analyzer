"""Per-entity feature engineering for detection (Doc 06 §11)."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta


def build(events: list[dict], transfers: list[dict], correlation_hits: list[dict],
          medium_hits: list[dict] | None = None) -> dict[str, dict]:
    """Per-entity features for detection.

    `medium_hits` is optional so existing callers keep working; without it
    `coincidence_medium_count` stays 0 and behaviour is unchanged.
    """
    feats: dict[str, dict] = defaultdict(lambda: {
        "txn_count": 0, "total_in": 0.0, "total_out": 0.0, "coincidence_medium_count": 0,
        #: True when this entity's money flows came from the transfer graph rather than from
        #: its own statement. Surfaced so a flag raised on counterparty-side evidence is not
        #: mistaken for one raised on an account we actually hold.
        "from_transfers_only": False,
        "credits": [], "debits": [], "counterparties_in": set(), "counterparties_out": set(),
        "distinct_ips": set(), "distinct_imeis": set(), "night_events": 0, "total_events": 0,
        "coincidence_count": 0, "call_times": [], "txn_times": [],
    })

    for e in events:
        eid = e.get("entity_id")
        if not eid:
            continue
        f = feats[eid]
        f["total_events"] += 1
        hour = e["timestamp_start"].hour
        if hour <= 5 or hour >= 23:
            f["night_events"] += 1
        for (t, v) in e.get("own_identifiers", []):
            if t == "IP":
                f["distinct_ips"].add(v)
            elif t == "IMEI":
                f["distinct_imeis"].add(v)
        if e["event_type"] == "CALL":
            f["call_times"].append(e["timestamp_start"])
        if e["event_type"] == "TRANSACTION":
            f["txn_count"] += 1
            f["txn_times"].append(e["timestamp_start"])
            amt = e.get("amount") or 0.0
            asset = e.get("asset") or "INR"
            if e.get("direction") == "CREDIT":
                f["total_in"] += amt
                f["credits"].append((e["timestamp_start"], amt, asset))
            elif e.get("direction") == "DEBIT":
                f["total_out"] += amt
                f["debits"].append((e["timestamp_start"], amt, asset))

    # Transfers are participant-aware: `to_entity` may be a counterparty resolved from a UPI
    # VPA rather than an account whose statement we hold. Gating on `in feats` — membership
    # built from primary associations only — dropped those edges entirely.
    for tr in transfers:
        feats[tr["from_entity"]]["counterparties_out"].add(tr["to_entity"])
        feats[tr["to_entity"]]["counterparties_in"].add(tr["from_entity"])

    # Fill the money-flow vector from the transfer graph for entities that have none of
    # their own. `mule_account` needs fan-in AND rapid forwarding; fan-in already came from
    # transfers, but `max_rapid_forward` is derived from credits/debits, which are collected
    # per PRIMARY entity. On `fir-65-2024` that left the rule with 7,358 eligible entities
    # and 0 fired: a mule visible only as the counterparty of someone else's transfer — which
    # is what a real case looks like, since you hold the victim's statement and not the
    # mule's — carried an empty vector at any threshold.
    #
    # Only entities with no primary-side transactions are filled, so an entity whose own
    # statement is present keeps using it and nothing double-counts.
    #
    # In practice this fills PAYEES only: `money_flow.build_transfers` takes every payer from
    # a DEBIT leg's `entity_id`, so a `from_entity` always has a statement and always has
    # `txn_count > 0`. Measured on the demo set — all 74 filled entities are payees. The payer
    # branch is kept because `transfers` is a plain list this function does not own, and a
    # future source of edges (a bank's own remittance report, say) need not be statement-
    # derived; it must not silently skip half the graph if one appears.
    for tr in transfers:
        amount, when = tr.get("amount"), tr.get("time")
        if amount is None or when is None:
            continue
        # A self-edge would credit and debit the same entity at the same instant for the same
        # amount, which reads as 100% rapid forwarding and satisfies both halves of
        # `mule_account` off one row. `build_transfers` already refuses payer == payee; this
        # is the guard for any other producer, because the false positive it prevents is the
        # kind that would be quoted in a report.
        if tr["from_entity"] == tr["to_entity"]:
            continue
        asset = tr.get("asset") or "INR"
        payer, payee = feats[tr["from_entity"]], feats[tr["to_entity"]]
        if payer["txn_count"] == 0:
            payer["total_out"] += float(amount)
            payer["debits"].append((when, float(amount), asset))
            payer["from_transfers_only"] = True
        if payee["txn_count"] == 0:
            payee["total_in"] += float(amount)
            payee["credits"].append((when, float(amount), asset))
            payee["from_transfers_only"] = True

    # STRONG and MEDIUM are both call+transfer coincidences; STRONG additionally has an
    # overlapping IP session. Counting STRONG only meant `call_transfer_coincidence` — named
    # for the pair, not the triple — could never fire while STRONG was 0, which it is on both
    # real cases. Kept as separate counters so a hit's tier stays visible.
    for h in correlation_hits:
        feats[h["entity_id"]]["coincidence_count"] += 1
    for h in medium_hits or ():
        feats[h["entity_id"]]["coincidence_medium_count"] += 1

    # Derived scalars
    for eid, f in feats.items():
        f["fan_in"] = len(f["counterparties_in"])
        f["fan_out"] = len(f["counterparties_out"])
        f["n_ips"] = len(f["distinct_ips"])
        f["n_imeis"] = len(f["distinct_imeis"])
        f["night_ratio"] = f["night_events"] / f["total_events"] if f["total_events"] else 0.0
        f["inout_ratio"] = (f["total_out"] / f["total_in"]) if f["total_in"] else 0.0
        f["max_rapid_forward"] = _max_rapid_forward(f["credits"], f["debits"])
        f["max_calls_hour"] = _max_in_window(f["call_times"], 60)
        f["max_dormancy_days"] = _max_gap_days(f["txn_times"])
    return feats


def _max_in_window(times: list, minutes: int) -> int:
    """Max number of events within any sliding window of `minutes` (comm-burst signal)."""
    if not times:
        return 0
    ts = sorted(times)
    win = timedelta(minutes=minutes)
    best = 1
    j = 0
    for i in range(len(ts)):
        while ts[i] - ts[j] > win:
            j += 1
        best = max(best, i - j + 1)
    return best


def _max_gap_days(times: list) -> float:
    """Largest gap (days) between consecutive transactions — dormant-then-active signal."""
    if len(times) < 2:
        return 0.0
    ts = sorted(times)
    return max((ts[i] - ts[i - 1]).total_seconds() for i in range(1, len(ts))) / 86400.0


def _max_rapid_forward(credits, debits, hold_minutes: int = 120) -> float:
    """Largest fraction of a credit forwarded out within the hold window.

    A3: computed within the same asset only — you can't 'forward' an INR credit as a
    crypto debit, and mixing the two produces meaningless ratios.
    """
    best = 0.0
    debits = sorted(debits, key=lambda d: d[0])
    for tc, ac, asset in credits:
        if not ac:
            continue
        hi = tc + timedelta(minutes=hold_minutes)
        forwarded = sum(ad for (td, ad, da) in debits if da == asset and tc <= td <= hi)
        best = max(best, min(1.0, forwarded / ac))
    return round(best, 3)
