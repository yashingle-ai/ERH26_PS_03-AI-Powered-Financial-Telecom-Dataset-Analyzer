"""Every rule must measure the window it names in its own config.

Three keys were declared in `config/scoring_rules.yaml` and not honoured:

  * `structuring.window_hours` — never read. The timestamp was discarded at
    `for (_t, a, asset) in f["credits"]`, so three ₹9.5-lakh receipts *years apart* counted as
    smurfing. Structuring is a deliberate split of one sum; the burst is the whole signal.
  * `rapid_in_out.max_hold_minutes` — read only to build the flag text. The measurement came
    from one precomputed scalar fixed at 120 minutes, so every flag asserted "forwarded within
    60min" about a computation that had allowed 120. A forensic report stating a window that
    was not measured is the worst of the three, because it is wrong on the page.
  * `call_transfer_coincidence.window_minutes` — read by nothing at all; the window is applied
    upstream in correlation. Removed rather than wired, with the reason recorded in the config.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import yaml

from backend.app.core import config
from backend.app.detection import features as featmod
from backend.app.detection import rules as rulemod
from backend.app.normalization import normalizers as nz

IST = nz.CANONICAL_TZ
T0 = datetime(2024, 5, 15, 9, 0, tzinfo=IST)


def _credits(*offsets_hours, amount=950_000.0, asset="INR"):
    return [(T0 + timedelta(hours=h), amount, asset) for h in offsets_hours]


def _struct_cfg(window_hours=24, min_occurrences=3):
    return {"rules": {"structuring": {
        "enabled": True, "weight": 0.2, "reporting_threshold_inr": 1_000_000,
        "just_below_band_pct": 0.10, "min_occurrences": min_occurrences,
        "window_hours": window_hours}}}


# ── structuring must honour window_hours ────────────────────────────────────────────

def test_three_in_band_credits_inside_the_window_fire():
    feats = {"E1": {"credits": _credits(0, 2, 5)}}
    flags = rulemod.structuring(feats, _struct_cfg())
    assert len(flags) == 1
    assert "within 24h" in flags[0]["detail"]


def test_three_in_band_credits_spread_over_years_do_not_fire():
    """The defect, stated as a case: a business that receives large sums is not a smurf."""
    feats = {"E1": {"credits": _credits(0, 24 * 400, 24 * 800)}}
    assert rulemod.structuring(feats, _struct_cfg()) == []


def test_the_burst_is_found_even_when_it_sits_among_spread_out_credits():
    """A real account has both. The window must find the densest run, not judge the whole set."""
    feats = {"E1": {"credits": _credits(0, 24 * 300, 24 * 600, 24 * 600 + 1, 24 * 600 + 3)}}
    flags = rulemod.structuring(feats, _struct_cfg())
    assert len(flags) == 1
    assert "3 credits" in flags[0]["detail"], "the burst is 3, not the 5 in the band overall"
    assert "5 in the band overall" in flags[0]["detail"], "the wider count must still be visible"


def test_a_credit_on_the_window_edge_is_included():
    feats = {"E1": {"credits": _credits(0, 12, 24)}}
    assert rulemod.structuring(feats, _struct_cfg()) != []


def test_widening_the_window_changes_the_outcome():
    """If the key were still ignored, both arms would agree — which is how it hid."""
    feats = {"E1": {"credits": _credits(0, 40, 80)}}
    assert rulemod.structuring(feats, _struct_cfg(window_hours=24)) == []
    assert rulemod.structuring(feats, _struct_cfg(window_hours=100)) != []


# ── rapid_in_out must measure the window it prints ──────────────────────────────────

def _flow_cfg(rule, hold, pct=0.8, **extra):
    return {"rules": {rule: {"enabled": True, "weight": 0.2, "max_hold_minutes": hold,
                             "min_forwarded_pct": pct, **extra}}}


def _in_then_out(gap_minutes):
    """₹100,000 in, all of it out `gap_minutes` later."""
    return {"credits": [(T0, 100_000.0, "INR")],
            "debits": [(T0 + timedelta(minutes=gap_minutes), 100_000.0, "INR")],
            "fan_in": 9, "from_transfers_only": False}


def test_a_forward_beyond_the_configured_hold_does_not_fire():
    """90 minutes is outside `rapid_in_out`'s 60 and inside the old hardcoded 120, so this is
    exactly the case the two disagreed on."""
    feats = {"E1": _in_then_out(90)}
    assert rulemod.rapid_in_out(feats, _flow_cfg("rapid_in_out", 60)) == []


def test_the_same_forward_fires_when_the_hold_is_configured_wider():
    feats = {"E1": _in_then_out(90)}
    flags = rulemod.rapid_in_out(feats, _flow_cfg("rapid_in_out", 120))
    assert len(flags) == 1
    assert "within 120min" in flags[0]["detail"]


def test_the_printed_window_is_the_measured_window():
    """The defect in one assertion: whatever number the detail names, a forward just past it
    must not be what produced the flag."""
    for hold in (30, 60, 120, 240):
        feats = {"E1": _in_then_out(hold - 1)}
        flags = rulemod.rapid_in_out(feats, _flow_cfg("rapid_in_out", hold))
        assert flags and f"within {hold}min" in flags[0]["detail"]
        just_outside = {"E1": _in_then_out(hold + 1)}
        assert rulemod.rapid_in_out(just_outside, _flow_cfg("rapid_in_out", hold)) == []


def test_mule_account_uses_its_own_hold_not_rapid_in_out_s():
    """The two rules configure different windows — 120 and 60 — and shared one scalar."""
    feats = {"E1": _in_then_out(90)}
    mule = _flow_cfg("mule_account", 120, pct=0.7, min_fan_in=5)
    flags = rulemod.mule_account(feats, mule)
    assert len(flags) == 1, "90min is inside mule_account's 120min hold"
    assert "within 120min" in flags[0]["detail"]
    assert rulemod.rapid_in_out(feats, _flow_cfg("rapid_in_out", 60)) == [], \
        "the same entity must not fire rapid_in_out, whose hold is 60min"


def test_the_ml_feature_keeps_its_own_documented_window():
    """`max_rapid_forward` is one scalar in the 13-feature ML vector and cannot serve two
    rules. Pinning it means changing a rule threshold does not silently re-fit the forest."""
    assert featmod.ML_HOLD_MINUTES == 120
    feats = featmod.build(
        [{"event_type": "TRANSACTION", "timestamp_start": T0, "amount": 100_000.0,
          "direction": "CREDIT", "entity_id": "E1", "own_identifiers": [], "attributes": {}},
         {"event_type": "TRANSACTION", "timestamp_start": T0 + timedelta(minutes=90),
          "amount": 100_000.0, "direction": "DEBIT", "entity_id": "E1",
          "own_identifiers": [], "attributes": {}}], [], [])
    assert feats["E1"]["max_rapid_forward"] == 1.0, "90min is inside the ML window of 120"


# ── the dead tunable must stay gone ─────────────────────────────────────────────────

def test_call_transfer_coincidence_declares_no_window_of_its_own():
    """It counts hits the correlation stage already windowed. A key here did nothing, which
    invites an analyst to widen the window in the wrong file and conclude the evidence is
    absent."""
    r = config.scoring_rules()["rules"]["call_transfer_coincidence"]
    assert "window_minutes" not in r


def test_every_declared_threshold_is_read_by_the_rule_that_declares_it():
    """The audit that found all three, kept as a test so a fourth cannot be added silently."""
    raw = yaml.safe_load(open(config.CONFIG_DIR / "scoring_rules.yaml", encoding="utf-8").read())
    src = open(rulemod.__file__, encoding="utf-8").read()
    unread = [f"{rule}.{key}"
              for rule, params in raw["rules"].items()
              for key in params
              if key not in ("enabled", "weight") and f'"{key}"' not in src
              and f"'{key}'" not in src]
    assert unread == [], f"declared but never read: {unread}"
