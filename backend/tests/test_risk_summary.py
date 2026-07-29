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


def test_deduped_events_are_not_counted_as_unreadable():
    """A de-duplicated event parsed fine — it is not a row we failed to read.

    `rejected_rows` mixed three things: rows that could not be mapped, blank layout
    rows, and events dropped as duplicates after a successful parse. On the real case
    the duplicates were roughly a third of the total, which made the headline look like
    a far larger evidence gap than it was.
    """
    inv = _inv({})
    inv.rejects = [
        {"file": "a.csv", "reason": "row missing timestamp / primary identifier",
         "rows": 100, "rejected": 40},
        {"file": "(cross-file)", "reason": "duplicate events removed",
         "rows": 52633, "rejected": 52633, "evidentiary": False},
        {"file": "b.xlsx", "reason": "blank / layout row (no content)",
         "rows": 7, "rejected": 7, "evidentiary": False},
    ]
    s = inv.summary()
    # the total keeps its original meaning so older figures still compare
    assert s["rejected_rows"] == 40 + 52633 + 7
    # but the number that means "evidence we could not read" excludes both
    assert s["unmapped_rows"] == 40
    assert s["non_evidentiary_rows"] == 52633 + 7
