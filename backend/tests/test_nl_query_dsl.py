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
        _call("+919702000558", "+919876543210", 3, imei="IMEI-A"),
        _call("+919702000558", "+919876543210", 4, imei="IMEI-A"),
        _call("+919702000558", "+919123456789", 14, imei="IMEI-B"),
        _txn(500_000), _txn(50_000),
    ]
    entities = {
        "e1": {"label": "Subject A", "identifiers": {("PHONE", "+919702000558"), ("ACCOUNT_NO", "999")}},
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
    from backend.app.search import answer as answer_mod

    spec = QuerySpec(
        target=Target.EVENTS,
        filters=[Filter(field=Field_.EVENT_TYPE, op=Op.EQ, value="CALL")],
        group_by=Field_.COUNTERPARTY,
        aggregate=Aggregate.COUNT,
        explanation="Group calls by counterparty, order by count desc.",
    )
    out = dsl.execute(spec, inv)
    assert out["rows"][0]["key"] == "PHONE:+919876543210"
    assert out["rows"][0]["count"] == 2

    plain = answer_mod.compose_answer(spec, out)
    # Investigator-facing answer — not the plan description.
    assert "Most frequent contact: +919876543210" in plain
    assert "2 calls" in plain
    assert "Group calls by counterparty" not in plain


def test_answer_for_empty_result_is_explicit(inv):
    from backend.app.search import answer as answer_mod

    spec = QuerySpec(
        target=Target.EVENTS,
        filters=[Filter(field=Field_.AMOUNT, op=Op.GTE, value=9_999_999)],
    )
    out = dsl.execute(spec, inv)
    plain = answer_mod.compose_answer(spec, out)
    assert plain.startswith("No matching events found")


def test_answer_for_high_risk_entities(inv):
    from backend.app.search import answer as answer_mod

    spec = QuerySpec(
        target=Target.ENTITIES,
        filters=[Filter(field=Field_.RISK_BAND, op=Op.EQ, value="high")],
    )
    out = dsl.execute(spec, inv)
    plain = answer_mod.compose_answer(spec, out)
    assert "Subject A" in plain
    assert "risk 88" in plain


def test_answer_never_requires_llm_rows(inv):
    """Regression: composing an answer must not call out — local template only."""
    from backend.app.search import answer as answer_mod

    spec = QuerySpec(
        target=Target.EVENTS,
        filters=[Filter(field=Field_.EVENT_TYPE, op=Op.EQ, value="CALL")],
        group_by=Field_.COUNTERPARTY,
    )
    out = dsl.execute(spec, inv)
    # Deliberately pass only the shaped result — no raw events.
    plain = answer_mod.compose_answer(spec, {
        "rows": out["rows"], "total": out["total"], "truncated": False,
    })
    assert plain.startswith("Most frequent contact:")


def test_offline_planner_who_called_most_often(inv):
    """No Gemini key required — common phrasing still becomes a QuerySpec + answer."""
    from backend.app.search import answer as answer_mod
    from backend.app.search import offline_planner

    spec = offline_planner.plan("who did 9702000558 call most often?")
    assert spec is not None
    assert spec.group_by is Field_.COUNTERPARTY
    out = dsl.execute(spec, inv)
    plain = answer_mod.compose_answer(spec, out)
    assert "Most frequent contact: +919876543210" in plain
    assert "2 calls" in plain


def test_offline_planner_transfers_over(inv):
    from backend.app.search import offline_planner

    spec = offline_planner.plan("transfers over 100000")
    assert spec is not None
    out = dsl.execute(spec, inv)
    assert out["total"] == 1


def test_offline_planner_calls_longer_than_duration(inv):
    """Verification F3 — 'calls longer than 10 minutes' must plan offline."""
    from backend.app.search import answer as answer_mod
    from backend.app.search import offline_planner

    spec = offline_planner.plan("find calls longer than 10 minutes")
    assert spec is not None
    assert any(f.field is Field_.DURATION and f.value == 600 for f in spec.filters)

    # Fixture calls are 60s; inject one long enough to hit the filter.
    long = dict(inv.events[0])
    long["attributes"] = {**(long.get("attributes") or {}), "duration": 900}
    inv.events.append(long)
    out = dsl.execute(spec, inv)
    plain = answer_mod.compose_answer(spec, out)
    assert out["total"] == 1
    assert "Found 1 call" in plain


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
        filters=[Filter(field=Field_.PHONE, op=Op.EQ, value="+919702000558")],
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
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert llm_planner.available() is False
    assert llm_planner.plan("who did X call most often?") is None


def test_planner_detects_either_gemini_key(monkeypatch):
    """The SDK honours GEMINI_API_KEY and GOOGLE_API_KEY; availability must match."""
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    assert llm_planner.available() is True


def test_queryspec_converts_to_a_gemini_schema():
    """Structured output constrains decoding — if the schema will not convert, the
    planner silently degrades to the rule engine on every call."""
    from google.genai._transformers import t_schema

    schema = t_schema(None, dsl.QuerySpec)
    assert schema.properties and "target" in schema.properties


def test_schema_vocabulary_is_static_and_data_free(inv):
    """The outbound vocabulary must depend only on the schema, never on the loaded case.

    Asserted structurally: every value is drawn from the DSL's own enums, and none of the
    fixture's identifiers (phones, accounts, entity labels) can appear in it.
    """
    vocab = dsl.schema_vocabulary()
    flat = str(vocab)

    known = (
        {t.value for t in Target} | {f.value for f in Field_}
        | {o.value for o in Op} | {a.value for a in Aggregate}
        | {m.value for m in dsl.Metric} | {a.value for a in dsl.Anchor}
        | {"TRANSACTION", "CALL", "IP_SESSION", "low", "medium", "high",
           "DEBIT", "CREDIT", "IN", "OUT"}
    )
    emitted = {v for values in vocab.values() for v in values}
    assert emitted <= known, f"vocabulary leaked non-schema values: {emitted - known}"

    for secret in ("+919702000558", "+919876543210", "999", "Subject A", "IMEI-A"):
        assert secret not in flat


# ── phone forms differ between the question and the data ──────────────────────

def test_phone_filter_matches_across_formats(inv):
    """Normalization stores E.164; an analyst types the number as it appears in the file.

    Found only by running the planner live: the model emitted "9702000558" while the
    pipeline held "+919702000558", so equality never matched and the query returned
    nothing — silently, which is the worst outcome for a forensic tool.
    """
    for typed in ("+919702000558", "9702000558", "919702000558", "+91 97020 00558"):
        spec = QuerySpec(
            target=Target.ENTITIES,
            filters=[Filter(field=Field_.PHONE, op=Op.EQ, value=typed)],
        )
        assert dsl.execute(spec, inv)["total"] == 1, f"failed for {typed!r}"


def test_counterparty_filter_matches_across_formats(inv):
    spec = QuerySpec(
        target=Target.EVENTS,
        filters=[Filter(field=Field_.COUNTERPARTY, op=Op.EQ, value="9876543210")],
    )
    assert dsl.execute(spec, inv)["total"] == 2


# ── blank placeholders must not win a grouping ────────────────────────────────

def test_grouping_skips_null_placeholders():
    """Operator exports use "-" for missing values; on the real CDR that bucket topped
    an IMEI grouping with 26,246 events, reading as a finding when it is the opposite."""
    events = [
        {"event_type": "CALL", "timestamp_start": datetime(2024, 8, 1, 1, tzinfo=IST),
         "primary": ("PHONE", "+919702000558"), "counterparty": None, "entity_id": "e1",
         "amount": None, "direction": None, "attributes": {"imei": marker},
         "provenance": {}}
        for marker in ("-", "N/A", "", "IMEI-REAL")
    ]
    out = dsl.execute(QuerySpec(target=Target.EVENTS, group_by=Field_.IMEI),
                      _Inv(events, {}, {}))

    assert [r["key"] for r in out["rows"]] == ["IMEI-REAL"]
    assert out["skipped_blank"] == 3


# ── Q1-Q4: the shapes the DSL could not express ───────────────────────────────
# Each was previously answered with a plausible but wrong result rather than refused,
# which is the dangerous failure mode for a forensic tool.

@pytest.fixture
def timeline():
    """Two subjects. A calls through August then stops; B keeps calling into October."""
    def call(a, b, day, month=8):
        return {"event_type": "CALL",
                "timestamp_start": datetime(2024, month, day, 12, tzinfo=IST),
                "primary": ("PHONE", a), "counterparty": ("PHONE", b),
                "entity_id": "e1", "amount": None, "direction": None,
                "attributes": {"narration": "", "location": "Surat"}, "provenance": {}}
    events = [
        call("+919000000001", "+919111111111", 5),
        call("+919000000001", "+919222222222", 20),          # A: last activity in August
        call("+919000000002", "+919111111111", 5),
        call("+919000000002", "+919111111111", 9, month=10),  # B: still active in October
        {"event_type": "TRANSACTION",
         "timestamp_start": datetime(2024, 9, 15, 10, tzinfo=IST),
         "primary": ("ACCOUNT_NO", "555"), "counterparty": None, "entity_id": "e1",
         "amount": 100.0, "direction": "DEBIT", "attributes": {}, "provenance": {}},
        {"event_type": "CALL",
         "timestamp_start": datetime(2024, 9, 14, 9, tzinfo=IST),   # day before that txn
         "primary": ("PHONE", "+919000000003"), "counterparty": ("PHONE", "+919333333333"),
         "entity_id": "e1", "amount": None, "direction": None,
         "attributes": {"narration": "UPI to KIRANA STORE"}, "provenance": {}},
    ]
    return _Inv(events, {}, {})


def test_q1_relative_window_day_before_last_transaction(timeline):
    """'what happened the day before the last transaction?' — the date is not knowable
    until the data is read, so this cannot be a filter."""
    spec = QuerySpec(
        target=Target.EVENTS,
        relative_window=dsl.RelativeWindow(
            anchor=dsl.Anchor.LAST_TRANSACTION, offset_days=-1, span_days=1),
    )
    out = dsl.execute(spec, timeline)

    assert out["total"] == 1
    assert out["rows"][0]["when"].startswith("2024-09-14")
    assert out["window"] == ["2024-09-14", "2024-09-15"]


def test_q1_window_with_no_anchor_reports_rather_than_lying(timeline):
    spec = QuerySpec(target=Target.EVENTS,
                     relative_window=dsl.RelativeWindow(anchor=dsl.Anchor.LAST_TRANSACTION))
    out = dsl.execute(spec, _Inv([], {}, {}))
    assert out["total"] == 0 and "note" in out


def test_q2_having_finds_numbers_that_stopped_calling(timeline):
    """'list numbers that stopped calling after August'.

    Previously this planned a plain grouping and returned the *busiest* numbers — the
    opposite of the question. `having last_seen < 2024-09-01` is the real predicate.
    """
    spec = QuerySpec(
        target=Target.EVENTS,
        filters=[Filter(field=Field_.EVENT_TYPE, op=Op.EQ, value="CALL")],
        group_by=Field_.PHONE,
        having=[dsl.Having(metric=dsl.Metric.LAST_SEEN, op=Op.LT, value="2024-09-01")],
    )
    out = dsl.execute(spec, timeline)

    keys = {r["key"] for r in out["rows"]}
    assert "+919000000001" in keys        # stopped in August
    assert "+919000000002" not in keys    # still active in October


def test_q2_having_count_threshold(timeline):
    spec = QuerySpec(
        target=Target.EVENTS,
        filters=[Filter(field=Field_.EVENT_TYPE, op=Op.EQ, value="CALL")],
        group_by=Field_.PHONE,
        having=[dsl.Having(metric=dsl.Metric.COUNT, op=Op.GTE, value=2)],
    )
    out = dsl.execute(spec, timeline)
    assert all(r["count"] >= 2 for r in out["rows"])


def test_q3_group_must_include_both_parties(timeline):
    """'which numbers called both A and B' — a set intersection over a group."""
    spec = QuerySpec(
        target=Target.EVENTS,
        group_by=Field_.PHONE,
        group_must_include=dsl.GroupContains(
            field=Field_.COUNTERPARTY,
            values=["+919111111111", "+919222222222"]),
    )
    out = dsl.execute(spec, timeline)

    # Only subject 1 called both; subject 2 called only the first.
    assert [r["key"] for r in out["rows"]] == ["+919000000001"]


def test_q4_any_text_searches_across_fields(timeline):
    """A term the analyst cannot map to one column — narration here, location elsewhere."""
    spec = QuerySpec(
        target=Target.EVENTS,
        filters=[Filter(field=Field_.ANY_TEXT, op=Op.CONTAINS, value="kirana")],
    )
    assert dsl.execute(spec, timeline)["total"] == 1

    spec = QuerySpec(
        target=Target.EVENTS,
        filters=[Filter(field=Field_.ANY_TEXT, op=Op.CONTAINS, value="surat")],
    )
    assert dsl.execute(spec, timeline)["total"] == 4
