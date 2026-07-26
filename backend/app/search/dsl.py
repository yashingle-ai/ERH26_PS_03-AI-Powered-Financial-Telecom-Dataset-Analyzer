"""Structured query DSL (F1) — the contract between natural language and the data.

The rule-based interpreter in `nl_query.py` answers five hardcoded phrasings. Tested
against the real case it answered 0 of 8 questions an investigator actually asks ("who did
X call most often?", "calls between 2am and 5am", "which numbers shared an IMEI?"), because
those need aggregation, not pattern matching.

This module defines a small, closed query language and executes it **locally** over an
Investigation. An LLM may translate a question into a `QuerySpec` (see `llm_planner.py`),
but it never sees case data and never emits code — it fills in a validated object, and
this executor decides what that means. That keeps the answer auditable: every result can
be traced to a spec the analyst can read, and a malformed spec fails validation rather
than running.

Design constraints (research/07, SR-R4):
  - no free-text passthrough: every field is an enum or a primitive
  - no raw SQL, ever
  - `total` is always reported alongside `rows` so truncation is visible
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Target(str, Enum):
    EVENTS = "events"
    ENTITIES = "entities"
    CORRELATIONS = "correlations"


class Op(str, Enum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    CONTAINS = "contains"
    IN = "in"
    BETWEEN = "between"


class Field_(str, Enum):
    """Queryable fields. Closed set — an unknown field fails validation, not silently."""

    EVENT_TYPE = "event_type"
    TIMESTAMP = "timestamp"
    HOUR_OF_DAY = "hour_of_day"
    DATE = "date"
    AMOUNT = "amount"
    DIRECTION = "direction"
    DURATION = "duration"
    ENTITY_ID = "entity_id"
    ENTITY_LABEL = "entity_label"
    COUNTERPARTY = "counterparty"
    PHONE = "phone"
    ACCOUNT_NO = "account_no"
    IMEI = "imei"
    IMSI = "imsi"
    IP = "ip"
    CELL_ID = "cell_id"
    LOCATION = "location"
    RISK_SCORE = "risk_score"
    RISK_BAND = "risk_band"
    RULE_FLAG = "rule_flag"
    #: Q4 — every searchable text field at once, for "mentions X anywhere" questions.
    ANY_TEXT = "any_text"


class Filter(BaseModel):
    model_config = {"extra": "forbid"}

    field: Field_
    op: Op
    value: Any = None
    values: list[Any] | None = Field(default=None, description="For `in` / `between`.")


class Aggregate(str, Enum):
    COUNT = "count"
    SUM_AMOUNT = "sum_amount"
    AVG_AMOUNT = "avg_amount"
    MAX_AMOUNT = "max_amount"


class Metric(str, Enum):
    """Per-group values a `having` clause can test (Q2)."""

    COUNT = "count"
    SUM_AMOUNT = "sum_amount"
    AVG_AMOUNT = "avg_amount"
    MAX_AMOUNT = "max_amount"
    FIRST_SEEN = "first_seen"     # ISO date of the group's earliest event
    LAST_SEEN = "last_seen"       # ISO date of the group's latest event


class Having(BaseModel):
    """A condition applied *after* grouping.

    Q2: questions about absence ("numbers that stopped calling after August", "accounts
    with no activity since March") are properties of a whole group, not of any single
    row, so a pre-group filter cannot express them. Without this the planner fell back to
    a plain grouping and returned the *busiest* numbers — the opposite of the question.
    """

    model_config = {"extra": "forbid"}

    metric: Metric
    op: Op
    value: Any = None
    values: list[Any] | None = None


class Anchor(str, Enum):
    """A point in the data that a relative window is measured from (Q1)."""

    FIRST_EVENT = "first_event"
    LAST_EVENT = "last_event"
    FIRST_TRANSACTION = "first_transaction"
    LAST_TRANSACTION = "last_transaction"
    FIRST_CALL = "first_call"
    LAST_CALL = "last_call"


class RelativeWindow(BaseModel):
    """A calendar window positioned relative to an anchor event (Q1).

    "The day before the last transaction" cannot be a filter, because the date is not
    known until the data has been read. Previously the planner dropped the relative clause
    and returned every transaction. Resolved here in a first pass, then applied as a date
    range.
    """

    model_config = {"extra": "forbid"}

    anchor: Anchor
    offset_days: int = Field(default=0, description="Days from the anchor; negative = before.")
    span_days: int = Field(default=1, ge=1, description="Length of the window in days.")


class GroupContains(BaseModel):
    """Keep only groups whose events cover *every* listed value (Q3).

    "Numbers that called both A and B" is a set-intersection question: it holds of a
    group, and no single event satisfies it.
    """

    model_config = {"extra": "forbid"}

    field: Field_
    values: list[str]


class QuerySpec(BaseModel):
    """A validated, executable query. This is what the LLM fills in — nothing else."""

    model_config = {"extra": "forbid"}

    target: Target
    filters: list[Filter] = Field(default_factory=list)
    relative_window: RelativeWindow | None = None
    group_by: Field_ | None = None
    aggregate: Aggregate = Aggregate.COUNT
    having: list[Having] = Field(default_factory=list)
    group_must_include: GroupContains | None = None
    order_desc: bool = True
    limit: int = Field(default=100, ge=1, le=2000)
    explanation: str = Field(
        default="",
        description="One plain sentence describing what this query returns, for the analyst.",
    )


# ── field extraction ──────────────────────────────────────────────────────────

def _ids_of(entity: dict, kind: str) -> list[str]:
    return [str(v) for k, v in (entity.get("identifiers") or set()) if k == kind]


def _event_value(ev: dict, f: Field_, entities: dict) -> Any:
    attrs = ev.get("attributes") or {}
    ts = ev.get("timestamp_start")
    match f:
        case Field_.EVENT_TYPE:
            return ev.get("event_type")
        case Field_.TIMESTAMP:
            return ts.isoformat() if isinstance(ts, datetime) else None
        case Field_.HOUR_OF_DAY:
            return ts.hour if isinstance(ts, datetime) else None
        case Field_.DATE:
            return ts.date().isoformat() if isinstance(ts, datetime) else None
        case Field_.AMOUNT:
            return ev.get("amount")
        case Field_.DIRECTION:
            return ev.get("direction")
        case Field_.DURATION:
            return attrs.get("duration")
        case Field_.ENTITY_ID:
            return ev.get("entity_id")
        case Field_.ENTITY_LABEL:
            return (entities.get(ev.get("entity_id")) or {}).get("label")
        case Field_.COUNTERPARTY:
            cp = ev.get("counterparty")
            return f"{cp[0]}:{cp[1]}" if isinstance(cp, (tuple, list)) and len(cp) >= 2 else None
        case Field_.PHONE:
            p = ev.get("primary")
            return p[1] if isinstance(p, (tuple, list)) and p[0] == "PHONE" else None
        case Field_.ACCOUNT_NO:
            p = ev.get("primary")
            return p[1] if isinstance(p, (tuple, list)) and p[0] == "ACCOUNT_NO" else None
        case Field_.IMEI:
            return attrs.get("imei")
        case Field_.IMSI:
            return attrs.get("imsi")
        case Field_.IP:
            return attrs.get("public_ip") or attrs.get("ip")
        case Field_.CELL_ID:
            return attrs.get("cell_id")
        case Field_.LOCATION:
            return attrs.get("location")
        case Field_.ANY_TEXT:
            # Q4: one haystack of every human-readable field, so "mentions X anywhere"
            # does not require the analyst to know which column X lives in.
            cp = ev.get("counterparty")
            parts = [
                ev.get("event_type"), ev.get("direction"),
                (entities.get(ev.get("entity_id")) or {}).get("label"),
                attrs.get("narration"), attrs.get("location"), attrs.get("cell_id"),
                attrs.get("imei"), attrs.get("imsi"),
                attrs.get("public_ip") or attrs.get("ip"),
                f"{cp[1]}" if isinstance(cp, (tuple, list)) and len(cp) >= 2 else None,
                (ev.get("provenance") or {}).get("source_file"),
            ]
            return " ".join(str(p) for p in parts if p)
    return None


def _entity_value(row: dict, f: Field_, entities: dict) -> Any:
    ent = entities.get(row.get("entity_id")) or {}
    match f:
        case Field_.ENTITY_ID:
            return row.get("entity_id")
        case Field_.ENTITY_LABEL:
            return row.get("label")
        case Field_.RISK_SCORE:
            return row.get("risk_score")
        case Field_.RISK_BAND:
            return row.get("band")
        case Field_.RULE_FLAG:
            return [f["rule"] for f in (row.get("rule_flags") or [])]
        case Field_.PHONE:
            return _ids_of(ent, "PHONE")
        case Field_.ACCOUNT_NO:
            return _ids_of(ent, "ACCOUNT_NO")
        case Field_.IMEI:
            return _ids_of(ent, "IMEI")
        case Field_.IMSI:
            return _ids_of(ent, "IMSI")
    return None


# ── filtering ─────────────────────────────────────────────────────────────────

def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


#: Fields whose values are phone numbers, in one form or another.
_PHONE_FIELDS = {Field_.PHONE, Field_.COUNTERPARTY}


def _phone_key(value: Any) -> str | None:
    """Last 10 digits, for comparing phone numbers written in different forms.

    Normalization stores E.164 ("+919702000558"), but an analyst types the number the way
    it appears in the case file ("9702000558"), and that is what a question carries. A
    plain equality test therefore never matched and the query silently returned nothing —
    the worst failure mode for a forensic tool. Comparing the subscriber-number suffix
    makes "9702000558", "919702000558" and "+91 97020 00558" all match.
    """
    digits = re.sub(r"\D", "", str(value))
    return digits[-10:] if len(digits) >= 10 else None


def _matches(actual: Any, flt: Filter) -> bool:
    # A list-valued field (an entity's phones) matches if ANY element matches.
    if isinstance(actual, list):
        return any(_matches(a, flt) for a in actual)
    if actual is None:
        return False

    op, want, wants = flt.op, flt.value, flt.values or []

    if flt.field in _PHONE_FIELDS and op in (Op.EQ, Op.NEQ, Op.CONTAINS):
        a, w = _phone_key(actual), _phone_key(want)
        if a and w:
            return (a == w) if op is not Op.NEQ else (a != w)

    if op is Op.EQ:
        return str(actual).lower() == str(want).lower()
    if op is Op.NEQ:
        return str(actual).lower() != str(want).lower()
    if op is Op.CONTAINS:
        return str(want).lower() in str(actual).lower()
    if op is Op.IN:
        return any(str(actual).lower() == str(w).lower() for w in wants)
    if op is Op.BETWEEN:
        a, lo, hi = _num(actual), _num(wants[0] if wants else None), _num(wants[1] if len(wants) > 1 else None)
        if a is None or lo is None or hi is None:
            return str(wants[0]) <= str(actual) <= str(wants[-1]) if wants else False
        return lo <= a <= hi

    a, w = _num(actual), _num(want)
    if a is None or w is None:                 # fall back to lexicographic (dates)
        a, w = str(actual), str(want)
    return {
        Op.GT: a > w, Op.GTE: a >= w, Op.LT: a < w, Op.LTE: a <= w,
    }[op]


# ── execution ─────────────────────────────────────────────────────────────────

_ANCHOR_TYPE = {
    Anchor.FIRST_TRANSACTION: "TRANSACTION", Anchor.LAST_TRANSACTION: "TRANSACTION",
    Anchor.FIRST_CALL: "CALL", Anchor.LAST_CALL: "CALL",
}
_ANCHOR_IS_LAST = {Anchor.LAST_EVENT, Anchor.LAST_TRANSACTION, Anchor.LAST_CALL}


def _resolve_window(win: RelativeWindow, events: list[dict]) -> tuple[date, date] | None:
    """Turn an anchor + offset into a concrete [start, end) date range (Q1).

    Resolved against the *unfiltered* events so "the day before the last transaction"
    means the last transaction in the case, not the last one that survived the filters.
    """
    want = _ANCHOR_TYPE.get(win.anchor)
    stamps = [
        e["timestamp_start"] for e in events
        if isinstance(e.get("timestamp_start"), datetime)
        and (want is None or e.get("event_type") == want)
    ]
    if not stamps:
        return None
    anchor = (max(stamps) if win.anchor in _ANCHOR_IS_LAST else min(stamps)).date()
    start = anchor + timedelta(days=win.offset_days)
    return start, start + timedelta(days=win.span_days)


def _in_window(ev: dict, window: tuple[date, date]) -> bool:
    ts = ev.get("timestamp_start")
    if not isinstance(ts, datetime):
        return False
    return window[0] <= ts.date() < window[1]


def execute(spec: QuerySpec, inv) -> dict:
    """Run a validated spec against an Investigation. Pure local computation."""
    entities = inv.entities

    if spec.target is Target.EVENTS:
        pool = inv.events

        def getter(row: dict, f: Field_):
            return _event_value(row, f, entities)
    elif spec.target is Target.ENTITIES:
        pool = list(inv.risk.values())

        def getter(row: dict, f: Field_):
            return _entity_value(row, f, entities)
    else:
        pool = inv.correlation_hits

        def getter(row: dict, f: Field_):
            return row.get(f.value)

    window = None
    if spec.relative_window is not None and spec.target is Target.EVENTS:
        window = _resolve_window(spec.relative_window, inv.events)
        if window is None:
            return {"rows": [], "total": 0, "truncated": False,
                    "note": "no events available to anchor the relative window"}

    rows = [r for r in pool
            if (window is None or _in_window(r, window))
            and all(_matches(getter(r, f.field), f) for f in spec.filters)]

    if spec.group_by is not None:
        out = _grouped(rows, spec, getter)
        if window:
            out["window"] = [window[0].isoformat(), window[1].isoformat()]
        return out

    total = len(rows)
    if spec.target is Target.EVENTS:
        # Event timestamps are timezone-aware, so the fallback must be too — sorting an
        # aware datetime against a naive one raises TypeError.
        rows.sort(key=lambda e: e.get("timestamp_start") or datetime.min.replace(tzinfo=UTC),
                  reverse=spec.order_desc)
        shaped = [_shape_event(e, entities) for e in rows[: spec.limit]]
    elif spec.target is Target.ENTITIES:
        rows.sort(key=lambda r: r.get("risk_score") or 0, reverse=spec.order_desc)
        shaped = [
            {"entity": r.get("label"), "entity_id": r.get("entity_id"),
             "risk": r.get("risk_score"), "band": r.get("band"),
             "flags": ", ".join(sorted({f["rule"] for f in (r.get("rule_flags") or [])}))}
            for r in rows[: spec.limit]
        ]
    else:
        shaped = [
            {"entity": h.get("entity_label"), "when": h.get("transaction", {}).get("time"),
             "amount": h.get("transaction", {}).get("amount"),
             "why": (h.get("explanation") or "")[:120]}
            for h in rows[: spec.limit]
        ]
    out = {"rows": shaped, "total": total, "truncated": total > len(shaped)}
    if window:
        # Surface the resolved dates: "the day before the last transaction" is only
        # auditable if the analyst can see which day that turned out to be.
        out["window"] = [window[0].isoformat(), window[1].isoformat()]
    return out


def _shape_event(e: dict, entities: dict) -> dict:
    ts = e.get("timestamp_start")
    prov = e.get("provenance") or {}
    return {
        "type": e.get("event_type"),
        "when": ts.isoformat() if isinstance(ts, datetime) else None,
        "entity": (entities.get(e.get("entity_id")) or {}).get("label"),
        "amount": e.get("amount"),
        "direction": e.get("direction"),
        "source_file": prov.get("source_file"),
    }


def _as_list(v: Any) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _metric(items: list[dict], m: Metric) -> Any:
    """One aggregate value for a group, for a `having` test."""
    if m is Metric.COUNT:
        return len(items)
    if m in (Metric.FIRST_SEEN, Metric.LAST_SEEN):
        stamps = [i["timestamp_start"] for i in items
                  if isinstance(i.get("timestamp_start"), datetime)]
        if not stamps:
            return None
        chosen = max(stamps) if m is Metric.LAST_SEEN else min(stamps)
        return chosen.date().isoformat()      # compared lexicographically; ISO sorts right
    amts = [a for a in (_num(i.get("amount")) for i in items) if a is not None]
    if not amts:
        return 0.0
    if m is Metric.SUM_AMOUNT:
        return sum(amts)
    if m is Metric.AVG_AMOUNT:
        return sum(amts) / len(amts)
    return max(amts)


def _as_filter(h: Having) -> Filter:
    """Reuse the row comparator for group metrics — one comparison semantics, not two."""
    return Filter(field=Field_.ANY_TEXT, op=h.op, value=h.value, values=h.values)


#: Placeholders operators use for "no value". Grouping on them produces a meaningless
#: bucket that outranks every real one — on the real CDR, "-" topped an IMEI grouping
#: with 26,246 events, which reads as a finding and is not one.
_NULL_MARKERS = {"", "-", "--", "n/a", "na", "null", "none", "nil", "0", "unknown"}


def _grouped(rows: list[dict], spec: QuerySpec, getter) -> dict:
    buckets: dict[Any, list[dict]] = defaultdict(list)
    dropped = 0
    for r in rows:
        key = getter(r, spec.group_by)
        for k in (key if isinstance(key, list) else [key]):
            if k is None or str(k).strip().lower() in _NULL_MARKERS:
                dropped += 1
                continue
            buckets[k].append(r)

    def score(items: list[dict]) -> float:
        if spec.aggregate is Aggregate.COUNT:
            return len(items)
        amts = [a for a in (_num(i.get("amount")) for i in items) if a is not None]
        if not amts:
            return 0.0
        if spec.aggregate is Aggregate.SUM_AMOUNT:
            return sum(amts)
        if spec.aggregate is Aggregate.AVG_AMOUNT:
            return sum(amts) / len(amts)
        return max(amts)

    if spec.group_must_include is not None:      # Q3
        need = {_phone_key(v) or str(v).lower()
                for v in spec.group_must_include.values}
        gf = spec.group_must_include.field
        buckets = {
            k: v for k, v in buckets.items()
            if need <= {_phone_key(x) or str(x).lower()
                        for i in v
                        for x in _as_list(getter(i, gf))}
        }

    if spec.having:                              # Q2
        buckets = {k: v for k, v in buckets.items()
                   if all(_matches(_metric(v, h.metric), _as_filter(h)) for h in spec.having)}

    ranked = sorted(((k, score(v), len(v)) for k, v in buckets.items()),
                    key=lambda t: t[1], reverse=spec.order_desc)
    shaped = [{"key": str(k), spec.aggregate.value: round(s, 2), "events": n}
              for k, s, n in ranked[: spec.limit]]
    out = {"rows": shaped, "total": len(ranked), "truncated": len(ranked) > len(shaped)}
    if dropped:
        # Reported, never silent: the analyst must know the grouping ignored rows.
        out["skipped_blank"] = dropped
    return out


def schema_vocabulary() -> dict:
    """The static vocabulary handed to the planner. Contains no case data — only names."""
    return {
        "targets": [t.value for t in Target],
        "fields": [f.value for f in Field_],
        "operators": [o.value for o in Op],
        "aggregates": [a.value for a in Aggregate],
        "having_metrics": [m.value for m in Metric],
        "anchors": [a.value for a in Anchor],
        "event_types": ["TRANSACTION", "CALL", "IP_SESSION"],
        "risk_bands": ["low", "medium", "high"],
        "directions": ["DEBIT", "CREDIT", "IN", "OUT"],
    }


__all__ = ["Aggregate", "Anchor", "Field_", "Filter", "GroupContains", "Having",
           "Metric", "Op", "QuerySpec", "RelativeWindow", "Target",
           "execute", "schema_vocabulary"]
