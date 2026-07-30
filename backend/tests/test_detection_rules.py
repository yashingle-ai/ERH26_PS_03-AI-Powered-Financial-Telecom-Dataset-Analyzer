

def test_noise_floor_adapts_down_never_up():
    """A ₹10,000 "tiny transfer" floor sat at the real case's p90, hiding 90% of it.

    The floor exists to drop benign small hops. Fixed in absolute rupees it was below
    the synthetic fixture's median (₹26,015) but at the p90 of the real case
    (median ₹997) — layering and circular-flow were searching a tenth of the graph.
    It may only ever move down.
    """
    from backend.app.detection.rules import adaptive_amount_floor

    small = [{"amount": a, "asset": "INR"} for a in (500, 900, 997, 2000, 3000)]
    assert adaptive_amount_floor(small, 10000) == 997      # lowered to the case median

    large = [{"amount": a, "asset": "INR"} for a in (20000, 26015, 40000, 900000)]
    assert adaptive_amount_floor(large, 10000) == 10000    # already fits — unchanged

    assert adaptive_amount_floor([], 10000) == 10000       # no data: keep the config
    assert adaptive_amount_floor(small, 0) == 0            # gate off stays off
    # crypto amounts are not comparable to an INR floor and must not skew it
    crypto = [{"amount": 0.004, "asset": "BTC"}] * 5
    assert adaptive_amount_floor(crypto, 10000) == 10000


def test_eligibility_report_separates_never_ran_from_found_nothing():
    """A rule that could not apply must not look like a rule that found nothing."""
    from backend.app.detection.rules import eligibility_report

    cfg = {"rules": {
        "structuring": {"enabled": True, "reporting_threshold_inr": 1000000,
                        "just_below_band_pct": 0.10, "min_occurrences": 3, "weight": 0.2},
        "layering": {"enabled": True, "min_hops": 3, "max_span_hours": 48,
                     "min_amount_inr": 10000, "weight": 0.15},
        "mule_account": {"enabled": False},
    }}
    transfers = [{"from_entity": "A", "to_entity": "B", "amount": 997,
                  "asset": "INR", "time": None}]
    rows = {r["rule"]: r for r in eligibility_report({}, transfers, cfg)}

    # the typology genuinely does not occur — eligible 0, and it says why
    assert rows["structuring"]["eligible"] == 0
    assert "does not occur here" in rows["structuring"]["note"]

    # the floor was lowered to fit the case, and that is reported
    assert rows["layering"]["eligible"] == 1
    assert "noise floor lowered" in rows["layering"]["note"]

    # a disabled rule is distinguishable from both
    assert rows["mule_account"]["enabled"] is False
    assert rows["mule_account"]["eligible"] is None


# ── the eligibility report must actually reach the product ─────────────────────────

def test_eligibility_reaches_the_investigation_and_the_report():
    """`rules.eligibility_report` was written and tested but nothing called it, so the one
    artefact that separates "found nothing" from "could not run" was unreachable — the same
    shape F3 was in, where the report generator existed with no HTTP route."""
    from backend.app import pipeline
    from backend.app.reporting import service as reporting

    inv = pipeline.run("datasets/raw/smoke", window_minutes=10)
    assert inv.rule_eligibility, "apply_analysis did not populate rule_eligibility"

    names = {r["rule"] for r in inv.rule_eligibility}
    assert {"structuring", "mule_account", "layering"} <= names
    for row in inv.rule_eligibility:
        assert "enabled" in row and "fired" in row
        # `eligible` may be None only when the rule is disabled outright
        assert row["eligible"] is not None or not row["enabled"]

    data = reporting.payload_from_investigation(inv, "smoke", 10)
    table = reporting._eligibility_rows(data)
    assert table and table[0] == ["Rule", "Enabled", "Eligible", "Fired", "Note"]
    assert len(table) == len(inv.rule_eligibility) + 1


def test_a_rule_with_no_eligible_candidate_is_distinguishable_from_one_that_found_nothing():
    """The whole point: `fired=0, eligible=0` and `fired=0, eligible=1000` are different
    findings and must not render identically."""
    from backend.app.detection.rules import eligibility_report

    cfg = {"rules": {"structuring": {"enabled": True, "weight": 0.2,
                                     "reporting_threshold_inr": 1_000_000,
                                     "just_below_band_pct": 0.1,
                                     "min_occurrences": 3}}}
    # a case whose largest transfer is nowhere near the reporting threshold
    small = [{"amount": 5_000.0, "asset": "INR"} for _ in range(50)]
    row = {r["rule"]: r for r in eligibility_report({}, small, cfg)}["structuring"]
    assert row["eligible"] == 0
    assert row["fired"] == 0
    assert row["note"] and "does not occur here" in row["note"]
