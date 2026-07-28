"""Windowed cross-dataset correlation (FR-9, NFR-2).

Two tiers — the STRONG rule is unchanged (FR-9); MEDIUM surfaces call+transfer
coincidences when no IP session is available for the entity in window W:

  STRONG — money transfer + call + IP session within W (decisive evidence).
  MEDIUM — money transfer + call within W, no overlapping IP session.

Every hit carries an explicit `tier` field so an analyst cannot confuse the two.
`correlation_hits` in the summary counts STRONG only; MEDIUM is reported separately.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import timedelta

from ..core import config

TIER_STRONG = "STRONG"
TIER_MEDIUM = "MEDIUM"


def _overlaps(session: dict, lo, hi) -> bool:
    start = session["timestamp_start"]
    end = session.get("timestamp_end") or start
    return start <= hi and end >= lo


def _by_participant(events: list[dict], event_type: str) -> dict[str, list[dict]]:
    """Index events by primary *and* counterparty entity.

    An entity participates in a call as caller or callee, and in a transfer as the
    account holder *or* the UPI/phone counterparty mined from narration. FR-9 needs
    that counterparty view: real cases often have phone-keyed CDR/IPDR and only see
    the bank side as a VPA phone on the other end of a transfer.
    """
    idx: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        if ev["event_type"] != event_type:
            continue
        if ev.get("entity_id"):
            idx[ev["entity_id"]].append(ev)
        cp = ev.get("counterparty_entity_id")
        if cp and cp != ev.get("entity_id"):
            idx[cp].append(ev)
    return idx


def _hit_base(eid, entities, w, txn, call) -> dict:
    t = txn["timestamp_start"]
    return {
        "entity_id": eid,
        "entity_label": entities.get(eid, {}).get("label"),
        "window_minutes": w,
        "transaction": {
            "time": t.isoformat(),
            "amount": txn.get("amount"),
            "direction": txn.get("direction"),
            "ref_no": (txn.get("attributes") or {}).get("ref_no"),
            "provenance": txn.get("provenance"),
        },
        "call": {
            "time": call["timestamp_start"].isoformat(),
            "counterparty_entity_id": call.get("counterparty_entity_id"),
            "provenance": call.get("provenance"),
        },
    }


def correlate(timeline_by_entity: dict[str, list[dict]], entities: dict,
              events: list[dict], window_minutes: int | None = None) -> list[dict]:
    """Return STRONG and MEDIUM hits (each with `tier`). Caller splits for the summary."""
    w = window_minutes or config.correlation_window_minutes()
    delta = timedelta(minutes=w)
    hits: list[dict] = []
    calls_idx = _by_participant(events, "CALL")
    txns_idx = _by_participant(events, "TRANSACTION")

    # Entities that only appear as transfer counterparties still need a pass.
    candidate_eids = set(timeline_by_entity) | set(txns_idx) | set(calls_idx)

    for eid in candidate_eids:
        ev_list = timeline_by_entity.get(eid, [])
        txns = txns_idx.get(eid) or [e for e in ev_list if e["event_type"] == "TRANSACTION"]
        calls = calls_idx.get(eid, [])
        sessions = [e for e in ev_list if e["event_type"] == "IP_SESSION"]
        # Need at least transfer + call; IP is required only for STRONG.
        if not (txns and calls):
            continue

        calls_sorted = sorted(calls, key=lambda c: c["timestamp_start"])
        call_times = [c["timestamp_start"] for c in calls_sorted]
        sessions_sorted = sorted(sessions, key=lambda s: s["timestamp_start"])
        sess_starts = [s["timestamp_start"] for s in sessions_sorted]

        for txn in txns:
            t = txn["timestamp_start"]
            lo, hi = t - delta, t + delta
            li = bisect.bisect_left(call_times, lo)
            ri = bisect.bisect_right(call_times, hi)
            calls_in = calls_sorted[li:ri]
            if not calls_in:
                continue
            call = min(calls_in, key=lambda c: abs(c["timestamp_start"] - t))
            base = _hit_base(eid, entities, w, txn, call)

            si = bisect.bisect_right(sess_starts, hi)
            sess_in = [s for s in sessions_sorted[:si] if _overlaps(s, lo, hi)]
            if sess_in:
                sess = sess_in[0]
                hits.append({
                    **base,
                    "tier": TIER_STRONG,
                    "ip_session": {
                        "start": sess["timestamp_start"].isoformat(),
                        "end": (sess.get("timestamp_end") or sess["timestamp_start"]).isoformat(),
                        "ip": (sess.get("attributes") or {}).get("public_ip"),
                        "provenance": sess.get("provenance"),
                    },
                    "explanation": (
                        f"Transfer of {txn.get('amount')} at {t.isoformat()} coincided with a "
                        f"call at {call['timestamp_start'].isoformat()} while entity was online "
                        f"from IP {(sess.get('attributes') or {}).get('public_ip')} "
                        f"(within {w} min)."
                    ),
                })
            else:
                hits.append({
                    **base,
                    "tier": TIER_MEDIUM,
                    "ip_session": None,
                    "explanation": (
                        f"Transfer of {txn.get('amount')} at {t.isoformat()} coincided with a "
                        f"call at {call['timestamp_start'].isoformat()} within {w} min "
                        f"(no overlapping IP session — MEDIUM tier)."
                    ),
                })
    return hits


def split_by_tier(hits: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (strong_hits, medium_hits)."""
    strong = [h for h in hits if h.get("tier") == TIER_STRONG]
    medium = [h for h in hits if h.get("tier") == TIER_MEDIUM]
    return strong, medium
