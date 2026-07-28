"""Compose a plain-text investigator answer from a QuerySpec and its local result.

The `/v1/query` endpoint used to return `explanation` — a description of the *plan*
("group calls by counterparty, order desc") — not an answer to the question. An
analyst asking "who did X call most often?" needs something like:

    Most frequent contact: +919876543210 — 47 calls.

This module templates that sentence **locally** from the validated spec and the
result rows. Case rows are never sent to an LLM to write prose (SR-R4 / §2).
"""

from __future__ import annotations

from typing import Any

from .dsl import Aggregate, Field_, QuerySpec, Target


def _fmt_key(key: Any) -> str:
    """PHONE:+9198… → +9198…; leave other keys alone."""
    s = str(key)
    for prefix in ("PHONE:", "ACCOUNT_NO:", "IP:", "IMEI:", "IMSI:", "UPI_ID:", "BENEFICIARY:"):
        if s.startswith(prefix):
            return s[len(prefix):]
    return s


def _noun(spec: QuerySpec) -> str:
    """What the rows are counting — used in 'N calls' / 'N transactions'."""
    et = None
    for f in spec.filters:
        if f.field is Field_.EVENT_TYPE and isinstance(f.value, str):
            et = f.value.upper()
            break
    if et == "CALL":
        return "call" if (spec.aggregate is Aggregate.COUNT) else "call amount"
    if et == "TRANSACTION":
        return "transaction" if (spec.aggregate is Aggregate.COUNT) else "transaction amount"
    if et == "IP_SESSION":
        return "IP session"
    if spec.target is Target.ENTITIES:
        return "entity"
    if spec.target is Target.CORRELATIONS:
        return "coincidence"
    return "event"


def _plural(n: int | float, word: str) -> str:
    n_i = int(n) if float(n) == int(n) else n
    if n_i == 1:
        return f"1 {word}"
    return f"{n_i} {word}s"


def _group_label(field: Field_ | None) -> str:
    if field is None:
        return "group"
    return {
        Field_.COUNTERPARTY: "contact",
        Field_.PHONE: "number",
        Field_.ACCOUNT_NO: "account",
        Field_.IMEI: "IMEI",
        Field_.IMSI: "IMSI",
        Field_.IP: "IP",
        Field_.ENTITY_LABEL: "entity",
        Field_.ENTITY_ID: "entity",
        Field_.CELL_ID: "cell",
        Field_.LOCATION: "location",
        Field_.DATE: "date",
        Field_.DIRECTION: "direction",
    }.get(field, field.value.replace("_", " "))


def _window_clause(window: list[str] | tuple[str, str] | None) -> str:
    if not window or len(window) < 2:
        return ""
    return f" (window {window[0]} → {window[1]})"


def _agg_phrase(row: dict, spec: QuerySpec) -> str:
    """'47 calls' or '₹5,00,000 total' depending on the aggregate."""
    noun = _noun(spec)
    if spec.aggregate is Aggregate.COUNT:
        n = row.get("count", row.get("events", 0))
        return _plural(n, noun.split()[0] if " " not in noun else noun)
    val = row.get(spec.aggregate.value)
    if val is None:
        return _plural(row.get("events", 0), "event")
    if spec.aggregate is Aggregate.SUM_AMOUNT:
        return f"sum ₹{val:,.2f}" if isinstance(val, (int, float)) else f"sum {val}"
    if spec.aggregate is Aggregate.AVG_AMOUNT:
        return f"avg ₹{val:,.2f}" if isinstance(val, (int, float)) else f"avg {val}"
    if spec.aggregate is Aggregate.MAX_AMOUNT:
        return f"max ₹{val:,.2f}" if isinstance(val, (int, float)) else f"max {val}"
    return str(val)


def compose_answer(
    spec: QuerySpec | None,
    result: dict,
    *,
    rules_explanation: str | None = None,
) -> str:
    """Build the analyst-facing answer string.

    `result` is the dict from `dsl.execute` (or the rules engine): rows, total,
    truncated, optional window/note/skipped_blank.
    """
    note = result.get("note")
    if note:
        return f"Could not answer as asked: {note}."

    rows = result.get("rows")
    total = int(result.get("total") or 0)
    window = result.get("window")

    # Offline rules path: explanation is already the answer.
    if spec is None:
        if rules_explanation:
            if rows is None:
                return rules_explanation
            return rules_explanation
        if rows is None:
            return "No answer — the question was not understood."
        return f"Found {total} matching result(s)."

    if not rows:
        target = {
            Target.EVENTS: "events",
            Target.ENTITIES: "entities",
            Target.CORRELATIONS: "correlation hits",
        }[spec.target]
        return f"No matching {target} found{_window_clause(window)}."

    # Grouped ranking — the flagship "who did X call most often?" shape.
    if spec.group_by is not None:
        top = rows[0]
        label = _group_label(spec.group_by)
        key = _fmt_key(top.get("key"))
        phrase = _agg_phrase(top, spec)
        head = f"Most frequent {label}: {key} — {phrase}"
        if total > 1:
            head += f". {total} distinct {label}s matched"
        if result.get("truncated"):
            head += f" (showing top {len(rows)})"
        head += _window_clause(window) + "."
        if result.get("skipped_blank"):
            head += f" {result['skipped_blank']} blank keys were excluded from the grouping."
        return head

    if spec.target is Target.ENTITIES:
        top = rows[0]
        name = top.get("entity") or top.get("entity_id") or "unknown"
        risk = top.get("risk")
        band = top.get("band")
        risk_bit = f" (risk {risk}" + (f", {band}" if band else "") + ")" if risk is not None else ""
        msg = f"Found {_plural(total, 'entity')}. Highest risk: {name}{risk_bit}."
        if result.get("truncated"):
            msg += f" Showing {len(rows)}."
        return msg

    if spec.target is Target.CORRELATIONS:
        msg = f"Found {_plural(total, 'call+IP+transfer coincidence')}{_window_clause(window)}."
        if rows:
            top = rows[0]
            bits = [str(top["entity"])] if top.get("entity") else []
            if top.get("amount") is not None:
                bits.append(f"₹{top['amount']}")
            if top.get("when"):
                bits.append(str(top["when"]))
            if bits:
                msg += f" Top hit: {', '.join(bits)}."
        return msg

    # Flat event list
    top = rows[0]
    when = top.get("when") or "unknown time"
    entity = top.get("entity") or "unknown entity"
    etype = (top.get("type") or "event").lower().replace("_", " ")
    amount = top.get("amount")
    amt_bit = f", ₹{amount}" if amount is not None else ""
    msg = (f"Found {_plural(total, _noun(spec).split()[0] if spec.filters else 'event')}"
           f"{_window_clause(window)}. "
           f"Latest: {etype} involving {entity} at {when}{amt_bit}.")
    if result.get("truncated"):
        msg += f" Showing {len(rows)} of {total}."
    return msg


__all__ = ["compose_answer"]
