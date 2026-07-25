"""Natural-language query: the structured DSL, its executor, and the LLM boundary.

The rule-based interpreter answered 0 of 8 realistic investigator questions when tested
against the real case. These tests pin the questions it could not answer to the DSL that
now can, and pin the guarantee that no case data crosses the network boundary.

Nothing here needs an API key — the executor is pure local computation and the planner is
tested through its guard and its no-key path.
"""

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.search import dsl, llm_planner
from backend.app.search.dsl import Aggregate, Field_, Filter, Op, QuerySpec, Target

IST = timezone(timedelta(hours=5, minutes=30))


class _Inv:
    """Minimal stand-in for pipeline.Investigation — only what the executor reads."""

    def __init__(self, events=None, entities=None, risk=None, hits=None):
        self.events = events or []
        self.entities = entities or {}
        self.risk = risk or {}
        self.correlation_hits = hits or []


def _call(a, b, hour, entity="e1", imei=None):
    return {
        "event_type": "CALL",
        "timestamp_start": datetime(2024, 8, 1, hour, 0, tzinfo=IST),
        "primary": ("PHONE", a), "counterparty": ("PHONE", b),
        "entity_id": entity, "amount": None, "direction": None,
        "attributes": {"duration": 60, "imei": imei}, "provenance": {"source_file": "cdr.csv"},
    }


def _txn(amount, entity="e1", hour=12):
    return {
        "event_type": "TRANSACTION",
        "timestamp_start": datetime(2024, 8, 1, hour, 0, tzinfo=IST),
        "primary": ("ACCOUNT_NO", "999"), "counterparty": None,
        "entity_id": entity, "amount": amount, "direction": "DEBIT",
        "attributes": {}, "provenance": {"source_file": "stmt.csv"},
    }


@pytest.fixture
def inv():
    events = [
        _call("+911", "+912", 3, imei="IMEI-A"),
        _call("+911", "+912", 4, imei="IMEI-A"),
        _call("+911", "+913", 14, imei="IMEI-B"),
        _txn(500_000), _txn(50_000),
    ]
    entities = {
        "e1": {"label": "Subject A", "identifiers": {("PHONE", "+911"), ("ACCOUNT_NO", "999")}},
    }
    risk = {
        "e1": {"entity_id": "e1", "label": "Subject A", "risk_score": 88.0,
               "band": "high", "rule_flags": [{"rule": "rapid_in_out"}]},
        "e2": {"entity_id": "e2", "label": "Subject B", "risk_score": 12.0,
               "band": "low", "rule_flags": []},
    }
    return _Inv(events, entities, risk)


# ── the questions the rule-based engine could not answer ──────────────────────

def test_who_did_x_call_most_often(inv):
    """'who did 9702000558 call most often?' — needs group-by, not pattern matching."""
    spec = QuerySpec(
        target=Target.EVENTS,
        filters=[Filter(field=Field_.EVENT_TYPE, op=Op.EQ, value="CALL")],
        group_by=Field_.COUNTERPARTY,
        aggregate=Aggregate.COUNT,
    )
    out = dsl.execute(spec, inv)
    assert out["rows"][0]["key"] == "PHONE:+912"
    assert out["rows"][0]["count"] == 2


def test_calls_between_2am_and_5am(inv):
    spec = QuerySpec(
        target=Target.EVENTS,
        filters=[
            Filter(field=Field_.EVENT_TYPE, op=Op.EQ, value="CALL"),
            Filter(field=Field_.HOUR_OF_DAY, op=Op.BETWEEN, values=[2, 5]),
        ],
    )
    out = dsl.execute(spec, inv)
    assert out["total"] == 2


def test_which_numbers_shared_an_imei(inv):
    spec = QuerySpec(target=Target.EVENTS, group_by=Field_.IMEI)
    out = dsl.execute(spec, inv)
    assert {r["key"] for r in out["rows"]} == {"IMEI-A", "IMEI-B"}


def test_transfers_over_a_threshold(inv):
    spec = QuerySpec(
        target=Target.EVENTS,
        filters=[
            Filter(field=Field_.EVENT_TYPE, op=Op.EQ, value="TRANSACTION"),
            Filter(field=Field_.AMOUNT, op=Op.GTE, value=100_000),
        ],
    )
    out = dsl.execute(spec, inv)
    assert out["total"] == 1 and out["rows"][0]["amount"] == 500_000


def test_high_risk_entities(inv):
    spec = QuerySpec(
        target=Target.ENTITIES,
        filters=[Filter(field=Field_.RISK_BAND, op=Op.EQ, value="high")],
    )
    out = dsl.execute(spec, inv)
    assert [r["entity"] for r in out["rows"]] == ["Subject A"]


def test_entity_identifier_filter_matches_any_value(inv):
    """An entity holds several phones; filtering on one must match the entity."""
    spec = QuerySpec(
        target=Target.ENTITIES,
        filters=[Filter(field=Field_.PHONE, op=Op.EQ, value="+911")],
    )
    assert dsl.execute(spec, inv)["total"] == 1


def test_sum_aggregate(inv):
    spec = QuerySpec(
        target=Target.EVENTS,
        filters=[Filter(field=Field_.EVENT_TYPE, op=Op.EQ, value="TRANSACTION")],
        group_by=Field_.DIRECTION,
        aggregate=Aggregate.SUM_AMOUNT,
    )
    out = dsl.execute(spec, inv)
    assert out["rows"][0]["sum_amount"] == 550_000.0


# ── truncation must be visible, not silent ────────────────────────────────────

def test_truncation_is_reported(inv):
    spec = QuerySpec(target=Target.EVENTS, limit=1)
    out = dsl.execute(spec, inv)
    assert out["total"] == 5 and len(out["rows"]) == 1 and out["truncated"] is True


def test_rule_engine_also_reports_total():
    """Both engines must return the same shape, or the UI can't trust either."""
    from backend.app.search import nl_query

    data = {"entities": {}, "risk": {}, "events": [], "correlation_hits": []}
    res = nl_query.answer("gibberish that parses as nothing", data)
    assert "total" in res and "truncated" in res


# ── the network boundary: no case data may leave ──────────────────────────────

def test_guard_rejects_bulk_payload():
    with pytest.raises(ValueError, match="capped at"):
        llm_planner._assert_no_case_data("x" * 600)


def test_guard_rejects_delimited_records():
    """A CSV fragment is a record dump, not a question."""
    with pytest.raises(ValueError, match="delimited"):
        llm_planner._assert_no_case_data(
            "919702000558,Incoming,918141122818,01-08-2024,00:04:06,1,2,3,4,5,6,7,8,9"
        )


def test_guard_rejects_multiline_payload():
    with pytest.raises(ValueError, match="multi-line"):
        llm_planner._assert_no_case_data("row1\nrow2\nrow3\nrow4\nrow5\nrow6\nrow7")


def test_guard_allows_a_real_question_containing_a_number():
    """'calls to 9702000558' is a legitimate question — digits alone are not case data."""
    llm_planner._assert_no_case_data("who did 9702000558 call most often?")


def test_planner_returns_none_without_api_key(monkeypatch):
    """Air-gapped deployments must fall back to rules, never fail."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm_planner.available() is False
    assert llm_planner.plan("who did X call most often?") is None


def test_schema_vocabulary_contains_no_case_data():
    """What we send is field names only — assert it stays that way."""
    vocab = dsl.schema_vocabulary()
    flat = str(vocab)
    assert "targets" in vocab and "fields" in vocab
    assert not any(ch.isdigit() and len(w) > 6 for w in flat.split() for ch in w)
