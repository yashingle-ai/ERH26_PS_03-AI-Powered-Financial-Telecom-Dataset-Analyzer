"""Money-flow reconstruction from double-entry transactions (shared UTR/ref).

Each real transfer appears twice in bank data — a DEBIT on the payer's account and a
CREDIT on the payee's account carrying the SAME reference number (UTR/RRN). Matching on
that shared reference gives a deterministic payer -> payee money-flow edge without needing
UPI resolution. Falls back to counterparty identifier when a matching leg is absent.
"""

from __future__ import annotations

from collections import defaultdict


def build_transfers(events: list[dict]) -> list[dict]:
    """Return directed transfers: {from_entity, to_entity, amount, time, ref}."""
    txns = [e for e in events if e["event_type"] == "TRANSACTION"]
    by_ref: dict[str, dict] = defaultdict(dict)
    transfers: list[dict] = []

    for e in txns:
        ref = (e.get("attributes") or {}).get("ref_no")
        if ref and e.get("direction") in ("DEBIT", "CREDIT"):
            by_ref[ref][e["direction"]] = e

    matched_refs = set()
    for ref, legs in by_ref.items():
        if "DEBIT" in legs and "CREDIT" in legs:
            payer = legs["DEBIT"].get("entity_id")
            payee = legs["CREDIT"].get("entity_id")
            if payer and payee and payer != payee:
                transfers.append({
                    "from_entity": payer, "to_entity": payee,
                    "amount": legs["DEBIT"].get("amount"),
                    "time": legs["DEBIT"]["timestamp_start"],
                    "ref": ref,
                })
                matched_refs.add(ref)

    # Fallback: debit legs whose credit counterpart isn't in the dataset -> use counterparty entity
    for e in txns:
        ref = (e.get("attributes") or {}).get("ref_no")
        if e.get("direction") == "DEBIT" and ref not in matched_refs:
            payer = e.get("entity_id")
            payee = e.get("counterparty_entity_id")
            if payer and payee and payer != payee:
                transfers.append({
                    "from_entity": payer, "to_entity": payee,
                    "amount": e.get("amount"), "time": e["timestamp_start"], "ref": ref,
                })
    return transfers
