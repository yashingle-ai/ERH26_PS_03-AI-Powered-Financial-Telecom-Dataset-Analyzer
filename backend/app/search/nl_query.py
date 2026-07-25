"""Natural-language query (F1) — rule-based interpreter over the investigation (FR-19).

Deliberately offline/deterministic: maps plain-language questions to structured filters over
events/entities. (An LLM→DSL upgrade can plug in here later using the latest Claude models,
but rule-based keeps it dependency-free, auditable, and safe for evidentiary use.)

Supported intents:
  - "transfers/transactions over/above N"        -> transactions >= N
  - "calls to/from <number>"                      -> calls involving that phone
  - "events on YYYY-MM-DD"                        -> events on that date
  - "high|medium risk entities"                   -> risk-banded entities
  - "transfers within M minutes of a call ..."    -> correlation coincidences
"""

from __future__ import annotations

import re


def _entity_label(data, eid):
    return (data["entities"].get(eid, {}) or {}).get("label", eid)


def answer(query: str, data: dict) -> dict:
    q = (query or "").lower().strip()

    # correlation intent
    if "within" in q and ("call" in q or "transfer" in q) and ("minute" in q or "min" in q):
        hits = data.get("correlation_hits", [])
        rows = [{"entity": h["entity_label"], "when": h["transaction"]["time"],
                 "amount": h["transaction"].get("amount"), "why": h["explanation"][:90]}
                for h in hits[:200]]
        return {"explanation": f"{len(hits)} call+IP+transfer coincidence(s).", "rows": rows}

    # risk-band intent
    m = re.search(r"\b(high|medium|low)\b.*risk|risk.*\b(high|medium|low)\b", q)
    if m and "entit" in q:
        band = next(b for b in ("high", "medium", "low") if b in q)
        ents = [r for r in data["risk"].values() if r["band"] == band]
        ents.sort(key=lambda r: -r["risk_score"])
        rows = [{"entity": r["label"], "risk": r["risk_score"],
                 "flags": ", ".join(sorted({f["rule"] for f in r["rule_flags"]}))}
                for r in ents[:200]]
        return {"explanation": f"{len(ents)} {band}-risk entities.", "rows": rows}

    # amount threshold intent
    m = re.search(r"(?:over|above|greater than|>)\s*₹?\s*([\d,]+)", q)
    if m and ("transfer" in q or "transaction" in q or "amount" in q):
        thr = float(m.group(1).replace(",", ""))
        txns = [e for e in data["events"]
                if e["event_type"] == "TRANSACTION" and (e.get("amount") or 0) >= thr]
        txns.sort(key=lambda e: -(e.get("amount") or 0))
        rows = [{"from": _entity_label(data, e.get("entity_id")),
                 "to": _entity_label(data, e.get("counterparty_entity_id")),
                 "amount": e.get("amount"), "when": str(e.get("timestamp_start"))}
                for e in txns[:200]]
        return {"explanation": f"{len(txns)} transactions ≥ {thr:g}.", "rows": rows}

    # calls to/from a number
    m = re.search(r"calls?\s+(?:to|from|with|of)\s+\+?(\d[\d ]{6,})", q)
    if m:
        num = re.sub(r"\D", "", m.group(1))
        calls = [e for e in data["events"] if e["event_type"] == "CALL"
                 and (num in str(e.get("primary")) or num in str(e.get("counterparty")))]
        rows = [{"a": str(e.get("primary")), "b": str(e.get("counterparty")),
                 "when": str(e.get("timestamp_start")),
                 "dur": (e.get("attributes") or {}).get("duration")} for e in calls[:200]]
        return {"explanation": f"{len(calls)} calls involving {num}.", "rows": rows}

    # events on a date
    m = re.search(r"(\d{4}-\d{2}-\d{2})", q)
    if m:
        day = m.group(1)
        evs = [e for e in data["events"] if str(e.get("timestamp_start"))[:10] == day]
        rows = [{"type": e["event_type"], "entity": _entity_label(data, e.get("entity_id")),
                 "amount": e.get("amount"), "when": str(e.get("timestamp_start"))}
                for e in evs[:200]]
        return {"explanation": f"{len(evs)} events on {day}.", "rows": rows}

    return {"explanation": "Sorry, I couldn't parse that. Try: 'transfers over 100000', "
                           "'calls to 9099102222', 'events on 2024-08-01', "
                           "'high risk entities'.", "rows": None}
