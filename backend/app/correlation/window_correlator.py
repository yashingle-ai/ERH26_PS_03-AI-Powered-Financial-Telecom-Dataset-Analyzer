"""Windowed cross-dataset correlation (FR-9, NFR-2).

The signature evidence: a money transfer that coincides — within a configurable window
W — with a phone call AND an active internet (IP) session for the same entity. This is
the "call + IP + transfer within a window" the problem statement calls decisive evidence.

Runs per entity on its unified timeline. Every hit references the underlying records
(provenance) so it is defensible.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import timedelta

from ..core import config


def _overlaps(session: dict, lo, hi) -> bool:
    start = session["timestamp_start"]
    end = session.get("timestamp_end") or start
    return start <= hi and end >= lo


def _calls_by_participant(events: list[dict]) -> dict[str, list[dict]]:
    """An entity is 'on a call' whether it is the caller or the callee, so index both."""
    idx: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        if ev["event_type"] != "CALL":
            continue
        if ev.get("entity_id"):
            idx[ev["entity_id"]].append(ev)
        if ev.get("counterparty_entity_id"):
            idx[ev["counterparty_entity_id"]].append(ev)
    return idx


def correlate(timeline_by_entity: dict[str, list[dict]], entities: dict,
              events: list[dict], window_minutes: int | None = None) -> list[dict]:
    w = window_minutes or config.correlation_window_minutes()
    delta = timedelta(minutes=w)
    hits: list[dict] = []
    calls_idx = _calls_by_participant(events)

    for eid, ev_list in timeline_by_entity.items():
        txns = [e for e in ev_list if e["event_type"] == "TRANSACTION"]
        calls = calls_idx.get(eid, [])
        sessions = [e for e in ev_list if e["event_type"] == "IP_SESSION"]
        if not (txns and calls and sessions):
            continue

        # review fix H3: sort once + binary-search the call window instead of scanning all
        # calls per transaction (was O(T*C)); sessions sorted by start for a bisect prefilter.
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
            # sessions starting after hi cannot overlap; earlier ones may (long sessions)
            si = bisect.bisect_right(sess_starts, hi)
            sess_in = [s for s in sessions_sorted[:si] if _overlaps(s, lo, hi)]
            if calls_in and sess_in:
                call = min(calls_in, key=lambda c: abs(c["timestamp_start"] - t))
                sess = sess_in[0]
                hits.append({
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
    return hits
