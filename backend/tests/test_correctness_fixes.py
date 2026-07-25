"""Tests for the gap-analysis remediation: timezone (A1), dedup (A2), per-asset (A3),
new typologies (D3), and NL query (F1)."""

from datetime import datetime, timedelta, timezone

from backend.app.normalization import normalizers as nz
from backend.app.normalization import service as norm


def test_a1_utc_source_converted_to_ist():
    # crypto Time(UTC) must be shifted +5:30 to canonical IST, not mislabelled
    dt = nz.parse_dt("2025-01-08 12:32:30", source_tz="UTC")
    assert dt.utcoffset() == timedelta(hours=5, minutes=30)
    assert (dt.hour, dt.minute) == (18, 2)   # 12:32 UTC -> 18:02 IST


def test_a1_ist_source_unchanged():
    dt = nz.parse_dt("2025-01-08 12:32:30", source_tz="IST")
    assert (dt.hour, dt.minute) == (12, 32)


def test_a2_dedup_drops_identical_events():
    ist = timezone(timedelta(hours=5, minutes=30))
    t = datetime(2024, 8, 1, 10, 0, tzinfo=ist)
    ev = {"event_type": "CALL", "primary": ("PHONE", "+911"), "counterparty": ("PHONE", "+912"),
          "timestamp_start": t, "attributes": {"duration": 30}}
    deduped, dropped = norm._dedupe([dict(ev), dict(ev), dict(ev)])
    assert len(deduped) == 1 and dropped == 2


def test_a3_structuring_ignores_crypto_amounts():
    from backend.app.core import config
    from backend.app.detection import rules
    cfg = config.scoring_rules()
    thr = cfg["rules"]["structuring"]["reporting_threshold_inr"]
    just_below = thr * 0.95
    # 5 crypto credits just below the INR threshold must NOT trigger structuring
    feats = {"E1": {"credits": [(None, just_below, "CRYPTO:USDT")] * 5}}
    flags = rules.structuring(feats, cfg)
    assert flags == []
    feats2 = {"E2": {"credits": [(None, just_below, "INR")] * 5}}
    assert rules.structuring(feats2, cfg)   # INR does trigger


def test_nl_query_amount_and_risk():
    from backend.app.search import nl_query
    data = {"events": [{"event_type": "TRANSACTION", "amount": 500000,
                        "entity_id": "E1", "counterparty_entity_id": "E2",
                        "timestamp_start": "2024-08-01"}],
            "entities": {"E1": {"label": "A"}, "E2": {"label": "B"}},
            "risk": {"E1": {"label": "A", "risk_score": 80, "band": "high", "rule_flags": []}},
            "correlation_hits": []}
    a = nl_query.answer("transfers over 100000", data)
    assert a["rows"] and a["rows"][0]["amount"] == 500000
    b = nl_query.answer("high risk entities", data)
    assert b["rows"] and b["rows"][0]["entity"] == "A"
