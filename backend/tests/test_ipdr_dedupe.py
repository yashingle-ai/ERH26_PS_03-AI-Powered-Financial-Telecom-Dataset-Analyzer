"""IP_SESSION de-duplication must separate distinct sessions from re-exported ones."""

from datetime import datetime, timedelta, timezone

from backend.app.normalization.service import _dedupe

IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2024, 12, 26, 13, 57, 28, tzinfo=IST)


def _session(dest_ip=None, port=None, private_ip="2409:40d2:1328:a31c::", start=T0, end=None):
    return {
        "event_type": "IP_SESSION",
        "timestamp_start": start,
        "timestamp_end": end,
        "primary": ("PHONE", "+918535088505"),
        "attributes": {"public_ip": None, "private_ip": private_ip,
                       "port": port, "dest_ip": dest_ip},
    }


def test_concurrent_sessions_to_different_destinations_are_kept():
    """TRAI exports repeat the MSISDN on every row and often leave Public IP blank.

    Keyed on (subscriber, public_ip, start) alone, every concurrent session of one
    subscriber collapsed to a single event — 37 of 75 real rows were dropped as
    duplicates when they were distinct connections. Which destinations were contacted
    is the evidence.
    """
    events = [
        _session(dest_ip="142.250.183.', 1", port="443"),
        _session(dest_ip="157.240.16.35", port="443"),
        _session(dest_ip="142.250.183.', 1", port="8080"),
    ]
    kept, dropped = _dedupe(events)
    assert len(kept) == 3, kept
    assert dropped == 0


def test_the_same_session_re_exported_still_dedupes():
    """The safety property: one export as .txt and .xlsx must not double-count.

    Widening the key can only retain more, so this is the case that could regress.
    """
    events = [_session(dest_ip="157.240.16.35", port="443"),
              _session(dest_ip="157.240.16.35", port="443")]
    kept, dropped = _dedupe(events)
    assert len(kept) == 1
    assert dropped == 1


def test_sessions_differing_only_by_end_time_are_distinct():
    a = _session(dest_ip="157.240.16.35", end=T0 + timedelta(minutes=4))
    b = _session(dest_ip="157.240.16.35", end=T0 + timedelta(minutes=9))
    kept, dropped = _dedupe([a, b])
    assert len(kept) == 2
    assert dropped == 0


def test_call_and_transaction_dedupe_are_untouched():
    """Only the IP_SESSION branch changed; the other two keys must behave as before."""
    call = {"event_type": "CALL", "timestamp_start": T0,
            "primary": ("PHONE", "+919000000001"),
            "counterparty": ("PHONE", "+919000000002"),
            "attributes": {"duration": 60}}
    kept, dropped = _dedupe([call, dict(call)])
    assert len(kept) == 1 and dropped == 1

    txn = {"event_type": "TRANSACTION", "timestamp_start": T0,
           "primary": ("ACCOUNT_NO", "123"), "counterparty": None,
           "amount": 5000.0, "direction": "CREDIT", "attributes": {"ref_no": "R1"}}
    kept, dropped = _dedupe([txn, dict(txn)])
    assert len(kept) == 1 and dropped == 1
