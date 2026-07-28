"""Offline question → QuerySpec for the no-API-key path.

`llm_planner.plan` returns None without a Gemini key, and the five canned regexes in
`nl_query.py` cannot express aggregation ("who did X call most often?"). This module
covers the investigator phrasings that map cleanly onto the DSL so air-gapped runs
still produce a real `answer` + auditable `spec`, not a "sorry" string.
"""

from __future__ import annotations

import re

from .dsl import (
    Aggregate,
    Field_,
    Filter,
    Op,
    QuerySpec,
    Target,
)


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def plan(question: str) -> QuerySpec | None:
    q = (question or "").strip()
    if not q or len(q) > 500:
        return None
    ql = q.lower()

    # "who did 9702000558 call most often?" / "top contacts of 9702000558"
    m = re.search(
        r"(?:who\s+did\s+|top\s+contacts?\s+(?:of|for)\s+)"
        r"\+?([\d][\d\s\-]{6,})\s*(?:call\s+most\s+often)?",
        ql,
    ) or re.search(
        r"who\s+did\s+\+?([\d][\d\s\-]{6,})\s+call\s+most\s+often",
        ql,
    )
    if m and ("call" in ql or "contact" in ql):
        phone = _digits(m.group(1))
        return QuerySpec(
            target=Target.EVENTS,
            filters=[
                Filter(field=Field_.EVENT_TYPE, op=Op.EQ, value="CALL"),
                Filter(field=Field_.PHONE, op=Op.CONTAINS, value=phone),
            ],
            group_by=Field_.COUNTERPARTY,
            aggregate=Aggregate.COUNT,
            limit=5,
            explanation=f"Group calls involving {phone} by counterparty, ordered by count.",
        )

    # "calls between 2am and 5am"
    m = re.search(r"calls?\s+between\s+(\d{1,2})\s*(?:am|:\d{2})?\s+and\s+(\d{1,2})", ql)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return QuerySpec(
            target=Target.EVENTS,
            filters=[
                Filter(field=Field_.EVENT_TYPE, op=Op.EQ, value="CALL"),
                Filter(field=Field_.HOUR_OF_DAY, op=Op.BETWEEN, values=[lo, hi]),
            ],
            explanation=f"Calls with hour_of_day between {lo} and {hi}.",
        )

    # "calls longer than 10 minutes" / "find calls over 5 mins"
    m = re.search(
        r"calls?\s+(?:longer\s+than|over|greater\s+than|>)\s+(\d+)\s*"
        r"(minutes?|mins?|seconds?|secs?)\b",
        ql,
    )
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        seconds = n * 60 if unit.startswith("min") else n
        return QuerySpec(
            target=Target.EVENTS,
            filters=[
                Filter(field=Field_.EVENT_TYPE, op=Op.EQ, value="CALL"),
                Filter(field=Field_.DURATION, op=Op.GTE, value=seconds),
            ],
            explanation=f"Calls with duration ≥ {seconds} seconds.",
        )

    # "which numbers shared an IMEI" / "same IMEI"
    if "imei" in ql and ("share" in ql or "same" in ql or "which" in ql):
        return QuerySpec(
            target=Target.EVENTS,
            filters=[Filter(field=Field_.EVENT_TYPE, op=Op.EQ, value="CALL")],
            group_by=Field_.IMEI,
            aggregate=Aggregate.COUNT,
            explanation="Group calls by IMEI to find shared handsets.",
        )

    # "transfers/transactions over/above N"
    m = re.search(r"(?:over|above|greater than|>)\s*₹?\s*([\d,]+)", ql)
    if m and ("transfer" in ql or "transaction" in ql or "amount" in ql):
        thr = float(m.group(1).replace(",", ""))
        return QuerySpec(
            target=Target.EVENTS,
            filters=[
                Filter(field=Field_.EVENT_TYPE, op=Op.EQ, value="TRANSACTION"),
                Filter(field=Field_.AMOUNT, op=Op.GTE, value=thr),
            ],
            explanation=f"Transactions with amount ≥ {thr:g}.",
        )

    # "high/medium/low risk entities"
    if "risk" in ql and "entit" in ql:
        band = next((b for b in ("high", "medium", "low") if b in ql), None)
        if band:
            return QuerySpec(
                target=Target.ENTITIES,
                filters=[Filter(field=Field_.RISK_BAND, op=Op.EQ, value=band)],
                explanation=f"{band}-risk entities by risk_score.",
            )

    # "calls to/from NUMBER"
    m = re.search(r"calls?\s+(?:to|from|with|of)\s+\+?([\d][\d\s\-]{6,})", ql)
    if m:
        phone = _digits(m.group(1))
        return QuerySpec(
            target=Target.EVENTS,
            filters=[
                Filter(field=Field_.EVENT_TYPE, op=Op.EQ, value="CALL"),
                Filter(field=Field_.ANY_TEXT, op=Op.CONTAINS, value=phone),
            ],
            explanation=f"Calls involving {phone}.",
        )

    # "events on YYYY-MM-DD"
    m = re.search(r"events?\s+on\s+(\d{4}-\d{2}-\d{2})", ql)
    if m:
        day = m.group(1)
        return QuerySpec(
            target=Target.EVENTS,
            filters=[Filter(field=Field_.DATE, op=Op.EQ, value=day)],
            explanation=f"Events on {day}.",
        )

    # "transfers within N minutes of a call" → correlations
    if "within" in ql and ("call" in ql or "transfer" in ql) and ("minute" in ql or "min" in ql):
        return QuerySpec(
            target=Target.CORRELATIONS,
            explanation="Call + IP + transfer coincidences in the correlation window.",
        )

    return None
