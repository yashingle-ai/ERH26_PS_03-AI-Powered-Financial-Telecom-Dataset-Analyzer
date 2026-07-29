"""The risk headline must not read as "nothing here" when it means something narrower."""

from backend.app.pipeline import Investigation


def _inv(risk):
    inv = Investigation.__new__(Investigation)
    for f in ("parsed_files", "events", "rejects", "transfers", "correlation_hits",
              "correlation_hits_medium"):
        setattr(inv, f, [])
    inv.entities = {}
    inv.risk = risk
    return inv


def test_summary_reports_band_distribution_and_top_score():
    """0 high with 25 medium is a different statement from 0 high with nothing at all.

    The band is deliberately hard to clear (high needs nearly every typology on one
    entity). Rescaling it per case would manufacture labels, so the summary explains
    itself instead.
    """
    risk = {f"E{i}": {"band": "medium", "risk_score": 52.5} for i in range(25)}
    risk.update({f"L{i}": {"band": "low", "risk_score": 10.0} for i in range(4159)})
    s = _inv(risk).summary()

    assert s["high_risk_entities"] == 0
    assert s["risk_bands"] == {"high": 0, "medium": 25, "low": 4159}
    assert s["top_risk_score"] == 52.5


def test_high_risk_count_still_matches_the_band():
    risk = {"A": {"band": "high", "risk_score": 82.0},
            "B": {"band": "medium", "risk_score": 55.0}}
    s = _inv(risk).summary()
    assert s["high_risk_entities"] == 1
    assert s["risk_bands"]["high"] == 1
    assert s["top_risk_score"] == 82.0


def test_empty_risk_does_not_crash_the_summary():
    s = _inv({}).summary()
    assert s["risk_bands"] == {"high": 0, "medium": 0, "low": 0}
    assert s["top_risk_score"] == 0.0
