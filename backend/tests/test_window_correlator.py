"""FR-9 correlator: STRONG (call+IP+txn) and MEDIUM (call+txn) tiers."""

from datetime import datetime, timedelta, timezone

from backend.app.correlation import window_correlator as wc

IST = timezone(timedelta(hours=5, minutes=30))


def _ev(etype, eid, t, *, cp=None, amount=None):
    return {
        "event_type": etype,
        "entity_id": eid,
        "counterparty_entity_id": cp,
        "timestamp_start": t,
        "timestamp_end": t + timedelta(minutes=5) if etype == "IP_SESSION" else None,
        "amount": amount,
        "direction": "DEBIT" if etype == "TRANSACTION" else None,
        "attributes": {"public_ip": "1.2.3.4"} if etype == "IP_SESSION" else {},
        "provenance": {"source_file": "t"},
    }


def test_strong_when_all_three_legs_in_window():
    t0 = datetime(2024, 6, 9, 15, 50, tzinfo=IST)
    eid = "E1"
    events = [
        _ev("TRANSACTION", eid, t0, amount=90000),
        _ev("CALL", eid, t0 + timedelta(minutes=1)),
        _ev("IP_SESSION", eid, t0 - timedelta(minutes=1)),
    ]
    hits = wc.correlate({eid: events}, {eid: {"label": "x"}}, events, window_minutes=10)
    strong, medium = wc.split_by_tier(hits)
    assert len(strong) == 1
    assert strong[0]["tier"] == wc.TIER_STRONG
    assert strong[0]["ip_session"] is not None
    assert medium == []


def test_medium_when_call_and_txn_without_ip():
    t0 = datetime(2024, 6, 9, 15, 50, tzinfo=IST)
    eid = "E1"
    events = [
        _ev("TRANSACTION", eid, t0, amount=100),
        _ev("CALL", eid, t0 + timedelta(minutes=2)),
    ]
    hits = wc.correlate({eid: events}, {eid: {"label": "x"}}, events, window_minutes=10)
    strong, medium = wc.split_by_tier(hits)
    assert strong == []
    assert len(medium) == 1
    assert medium[0]["tier"] == wc.TIER_MEDIUM
    assert medium[0]["ip_session"] is None


def test_txn_only_yields_nothing():
    t0 = datetime(2024, 6, 9, 15, 50, tzinfo=IST)
    eid = "E1"
    events = [_ev("TRANSACTION", eid, t0, amount=100)]
    hits = wc.correlate({eid: events}, {eid: {"label": "x"}}, events, window_minutes=10)
    assert hits == []


def test_strong_count_unchanged_when_medium_also_possible():
    """Entity with all three legs must not also emit a MEDIUM for the same txn."""
    t0 = datetime(2024, 6, 9, 15, 50, tzinfo=IST)
    eid = "E1"
    events = [
        _ev("TRANSACTION", eid, t0, amount=50),
        _ev("CALL", eid, t0),
        _ev("IP_SESSION", eid, t0),
    ]
    hits = wc.correlate({eid: events}, {eid: {"label": "x"}}, events, window_minutes=10)
    strong, medium = wc.split_by_tier(hits)
    assert len(strong) == 1
    assert medium == []


def test_correlation_counts_upi_phone_as_transfer_participant():
    """Bank TXN primary is an account; UPI narration phone is counterparty."""
    t0 = datetime(2024, 6, 9, 15, 50, tzinfo=IST)
    phone_eid = "E_PHONE"
    acct_eid = "E_ACCT"
    events = [
        _ev("TRANSACTION", acct_eid, t0, cp=phone_eid, amount=90000),
        _ev("CALL", phone_eid, t0 + timedelta(minutes=1)),
        _ev("IP_SESSION", phone_eid, t0 - timedelta(minutes=1)),
    ]
    timeline = {
        acct_eid: [events[0]],
        phone_eid: [events[1], events[2]],
    }
    entities = {
        phone_eid: {"label": "upi-phone"},
        acct_eid: {"label": "bank-acct"},
    }
    hits = wc.correlate(timeline, entities, events, window_minutes=10)
    strong, _medium = wc.split_by_tier(hits)
    assert len(strong) >= 1
    assert strong[0]["entity_id"] == phone_eid
    assert strong[0]["tier"] == wc.TIER_STRONG
