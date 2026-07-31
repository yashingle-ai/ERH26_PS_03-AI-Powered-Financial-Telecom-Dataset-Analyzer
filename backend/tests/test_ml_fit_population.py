"""The Isolation Forest must be fitted on entities we hold records for, not on counterparties.

`features.build` gives a feature vector to any entity named in a transfer, which is correct
for the rules — fan-in is real evidence about a payee. It is wrong for the ML arm: on the demo
dataset 74 of 104 entities are seen only as somebody else's payee, and each carries a vector
whose single non-zero cell is a transfer-derived credit. Fitting over that mixture makes
"a counterparty with one credit" the definition of normal, so a real account holder becomes an
outlier by construction.

Measured before this restriction was put back: 29 of the 30 observed entities moved by more
than 0.05, mean |delta| 0.252, max 0.414 — at `ml_weight` 0.3 an average of 7.6 risk-score
points and a worst case of 12.4, against bands whose high boundary is 70. None of it was
caused by anything those entities did.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.app.detection import service as detsvc
from backend.app.normalization import normalizers as nz

IST = nz.CANONICAL_TZ
T0 = datetime(2024, 5, 15, 10, 0, tzinfo=IST)


def _txn(eid, cp, amount, direction, minute=0):
    return {"event_type": "TRANSACTION", "timestamp_start": T0 + timedelta(minutes=minute),
            "amount": amount, "direction": direction, "entity_id": eid,
            "counterparty_entity_id": cp, "own_identifiers": [], "attributes": {}}


def _observed_events(n=12):
    """`n` entities with records of their own, enough to clear the 8-sample ML floor."""
    out = []
    for i in range(n):
        out.append(_txn(f"OBS{i}", None, 10_000.0 * (i + 1), "CREDIT", minute=i))
        out.append(_txn(f"OBS{i}", None, 5_000.0 * (i + 1), "DEBIT", minute=i + 1))
    return out


def _transfer(src, dst, amount, minute=0):
    return {"from_entity": src, "to_entity": dst, "amount": amount, "asset": "INR",
            "time": T0 + timedelta(minutes=minute), "ref": f"R{src}{dst}{minute}"}


def test_counterparty_only_entities_are_excluded_from_the_fit():
    events = _observed_events()
    transfers = [_transfer(f"OBS{i}", f"CP{i}", 1_000.0, minute=i) for i in range(12)]

    risk = detsvc.detect(events, transfers, [], {})
    observed = {f"OBS{i}" for i in range(12)}
    assert all(risk[e]["ml_scored"] is True for e in observed)
    assert all(risk[f"CP{i}"]["ml_scored"] is False for i in range(12)), \
        "an entity with no records of its own has no behavioural profile to score"
    assert all(risk[f"CP{i}"]["ml_score"] == 0.0 for i in range(12))


def test_adding_counterparties_does_not_move_an_observed_entity_ml_score():
    """The regression this guards: who ELSE is in the population must not change your score.

    The added edges are deliberately between counterparties only. Routing them through the
    observed entities instead would change those entities' own `fan_out`, which is one of the
    thirteen ML features — a legitimate reason for a score to move, and not the one under test.
    An early version of this test did exactly that and failed at 1.0 -> 0.998, which is the
    distinction being drawn: your own evidence may move your score, other people's may not.
    """
    events = _observed_events()
    few = [_transfer("OBS0", "CP0", 1_000.0)]
    many = few + [_transfer(f"CPX{i}", f"CPY{i}", 1_000.0, minute=i) for i in range(1, 80)]

    lean = detsvc.detect(events, few, [], {})
    fat = detsvc.detect(events, many, [], {})
    assert len(fat) > len(lean) + 100, "the extra population must actually be present"
    for i in range(12):
        eid = f"OBS{i}"
        assert lean[eid]["ml_score"] == fat[eid]["ml_score"], (
            f"{eid} was rescored by the arrival of counterparties: "
            f"{lean[eid]['ml_score']} -> {fat[eid]['ml_score']}")
        assert lean[eid]["risk_score"] == fat[eid]["risk_score"]


def test_ml_scored_is_false_when_the_case_is_too_small_to_model():
    """Gap D5 — under 8 observed entities the forest is skipped and every score is 0.0. That
    zero has to be distinguishable from a measured 0.0, or "not anomalous" and "never
    examined" read the same."""
    events = [_txn("A", None, 1_000.0, "CREDIT"), _txn("B", None, 2_000.0, "DEBIT")]
    risk = detsvc.detect(events, [], [], {})
    assert all(r["ml_scored"] is False for r in risk.values())
    assert all(r["ml_score"] == 0.0 for r in risk.values())


def test_a_counterparty_only_entity_still_gets_a_rules_based_score():
    """Excluding it from the ML fit must not exclude it from detection — the rules half is
    the defensible half, and a mule seen only as a payee is exactly what a real case holds."""
    events = _observed_events()
    # six payers into one account, then straight out again: fan-in plus rapid forwarding
    transfers = [_transfer(f"OBS{i}", "MULE", 100_000.0, minute=i) for i in range(6)]
    transfers.append(_transfer("MULE", "EXIT", 600_000.0, minute=7))

    risk = detsvc.detect(events, transfers, [], {})
    assert risk["MULE"]["ml_scored"] is False
    assert risk["MULE"]["risk_score"] > 0, "rules must still score an unobserved entity"
    assert any(f["rule"] == "mule_account" for f in risk["MULE"]["rule_flags"])
