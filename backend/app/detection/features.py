"""Per-entity feature engineering for detection (Doc 06 §11)."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta


def build(events: list[dict], transfers: list[dict], correlation_hits: list[dict]) -> dict[str, dict]:
    feats: dict[str, dict] = defaultdict(lambda: {
        "txn_count": 0, "total_in": 0.0, "total_out": 0.0,
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

    for tr in transfers:
        if tr["from_entity"] in feats:
            feats[tr["from_entity"]]["counterparties_out"].add(tr["to_entity"])
        if tr["to_entity"] in feats:
            feats[tr["to_entity"]]["counterparties_in"].add(tr["from_entity"])

    for h in correlation_hits:
        if h["entity_id"] in feats:
            feats[h["entity_id"]]["coincidence_count"] += 1

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
