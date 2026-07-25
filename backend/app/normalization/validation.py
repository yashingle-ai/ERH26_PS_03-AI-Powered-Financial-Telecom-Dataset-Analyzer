"""Data-quality validation (A5) — bank running-balance consistency.

For each bank account, sort transactions by time and verify that
    prev_balance + credit - debit == balance (within tolerance).
Breaks indicate a misparse, out-of-order rows, missing rows, or tampering — surfaced as a
data-quality report (not dropped), so the analyst knows the ledger isn't internally consistent.
"""

from __future__ import annotations

from collections import defaultdict

from ..core.logging_config import get_logger

log = get_logger(__name__)


def check_balances(events: list[dict], tolerance: float = 1.0) -> list[dict]:
    by_acct: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        if e["event_type"] != "TRANSACTION" or (e.get("asset") or "INR") != "INR":
            continue
        bal = (e.get("attributes") or {}).get("balance")
        if bal is None:
            continue
        by_acct[e["primary"][1]].append(e)

    report: list[dict] = []
    for acct, evs in by_acct.items():
        evs = sorted(evs, key=lambda e: e["timestamp_start"])
        prev = None
        checked = breaks = 0
        first_break = None
        for e in evs:
            bal = (e["attributes"] or {}).get("balance")
            amt = e.get("amount") or 0.0
            delta = amt if e.get("direction") == "CREDIT" else -amt
            if prev is not None:
                checked += 1
                if abs((prev + delta) - bal) > tolerance:
                    breaks += 1
                    if first_break is None:
                        first_break = (e.get("attributes") or {}).get("ref_no")
            prev = bal
        if breaks:
            report.append({"account": acct, "checked": checked, "breaks": breaks,
                           "first_break_ref": first_break,
                           "consistency": round(1 - breaks / checked, 3) if checked else None})
    if report:
        log.warning("balance-consistency: %d account(s) with ledger breaks", len(report))
    return sorted(report, key=lambda r: -r["breaks"])
