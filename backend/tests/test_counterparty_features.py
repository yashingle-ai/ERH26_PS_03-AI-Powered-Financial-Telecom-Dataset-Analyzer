"""Detection must be able to see a subject it only observes from the other side.

Both defects here were found by the rule eligibility report on `fir-65-2024`, which showed
`mule_account` and `call_transfer_coincidence` with **7,358 eligible entities and 0 fired**.
Neither is a threshold problem, which is why F1's calibration half was withdrawn.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.app.detection import features as featmod
from backend.app.detection import rules as rulemod
from backend.app.normalization import normalizers as nz

IST = nz.CANONICAL_TZ
T0 = datetime(2024, 5, 15, 10, 0, tzinfo=IST)


def _txn(eid, cp, amount, direction, minute=0):
    return {
        "event_type": "TRANSACTION",
        "timestamp_start": T0 + timedelta(minutes=minute),
        "amount": amount,
        "direction": direction,
        "entity_id": eid,
        "counterparty_entity_id": cp,
        "own_identifiers": [],
        "attributes": {},
    }


def _transfer(src, dst, amount, minute=0):
    return {"from_entity": src, "to_entity": dst, "amount": amount, "asset": "INR",
            "time": T0 + timedelta(minutes=minute), "ref": f"R{minute}"}


# ── counterparty-side money flows ──────────────────────────────────────────────────

def test_counterparty_only_entity_gets_flows_from_the_transfer_graph():
    """A mule visible only as the counterparty of someone else's transfer is what a real
    case looks like — you hold the victim's statement, not the mule's. Its feature vector was
    empty at any threshold, so `mule_account` could never fire on it."""
    events = [_txn("VICTIM", "MULE", 100_000.0, "DEBIT")]
    transfers = [_transfer("VICTIM", "MULE", 100_000.0)]

    feats = featmod.build(events, transfers, [])
    mule = feats["MULE"]
    assert mule["txn_count"] == 0, "the mule has no statement of its own"
    assert mule["total_in"] == 100_000.0
    assert mule["credits"], "credits must be filled from the transfer graph"
    assert mule["from_transfers_only"] is True


def test_an_entity_with_its_own_statement_is_not_double_counted():
    """Only entities with no primary-side transactions are filled, so an account whose
    statement is present keeps using it and its totals do not inflate."""
    events = [_txn("HOLDER", "OTHER", 50_000.0, "CREDIT")]
    transfers = [_transfer("OTHER", "HOLDER", 50_000.0)]

    feats = featmod.build(events, transfers, [])
    holder = feats["HOLDER"]
    assert holder["txn_count"] == 1
    assert holder["total_in"] == 50_000.0, "transfer-derived credit was added on top"
    assert holder["from_transfers_only"] is False


def test_an_observed_entity_with_no_transactions_is_also_filled():
    """The fill keys on `txn_count`, not on whether the entity has records at all — so a
    phone seen in the CDR that also turns up as a transfer counterparty gets those flows.

    That is intended: `txn_count == 0` means no statement of this entity is in the case, so
    the transfer graph is the only evidence of its money, and it is real evidence. But it does
    change the ML feature vector of an entity that IS in the anomaly fit — unlike a
    counterparty-only entity, which is excluded from the fit entirely — so it is a live path
    by which this change can move a fitted entity's score. Recorded here because that is the
    one mechanism capable of moving `FIR-0006-2025 U`'s top score, where MEDIUM hits are 0.
    """
    events = [{"event_type": "CALL", "timestamp_start": T0, "entity_id": "PHONE_ONLY",
               "own_identifiers": [], "attributes": {}}]
    feats = featmod.build(events, [_transfer("PAYER", "PHONE_ONLY", 40_000.0)], [])

    subject = feats["PHONE_ONLY"]
    assert subject["total_events"] == 1, "it has records of its own, so it IS in the ML fit"
    assert subject["txn_count"] == 0
    assert subject["total_in"] == 40_000.0
    assert subject["from_transfers_only"] is True


def test_fan_in_and_fan_out_include_counterparty_edges():
    """The transfers loop was gated on `in feats`, where membership came from primary
    associations only — so counterparty edges were dropped from fan-in entirely."""
    events = [_txn("VICTIM", None, 1.0, "DEBIT")]
    transfers = [_transfer(f"P{i}", "MULE", 10_000.0, minute=i) for i in range(6)]

    feats = featmod.build(events, transfers, [])
    assert feats["MULE"]["fan_in"] == 6
    assert feats["P0"]["fan_out"] == 1


def test_mule_account_fires_on_counterparty_evidence_and_says_so():
    """FR-13. The flag must state that the evidence is counterparty-side: a flag on an
    account we hold and one inferred from someone else's transfers are different strengths
    of finding."""
    events = [_txn("VICTIM", None, 1.0, "DEBIT")]
    # six payers in, then straight back out — fan-in plus rapid forwarding
    transfers = [_transfer(f"P{i}", "MULE", 100_000.0, minute=i) for i in range(6)]
    transfers.append(_transfer("MULE", "EXIT", 600_000.0, minute=7))

    feats = featmod.build(events, transfers, [])
    cfg = {"rules": {"mule_account": {"enabled": True, "weight": 0.15,
                                      "min_fan_in": 5, "min_forwarded_pct": 0.8}}}
    flags = rulemod.mule_account(feats, cfg)
    mine = [f for f in flags if f["entity_id"] == "MULE"]
    assert mine, f"mule_account did not fire; fan_in={feats['MULE']['fan_in']}"
    assert "counterparty-side" in mine[0]["detail"]


# ── MEDIUM correlation hits must reach the detector ────────────────────────────────

def _cfg_coincidence():
    return {"rules": {"call_transfer_coincidence": {"enabled": True, "weight": 0.15}}}


def test_call_transfer_coincidence_fires_on_a_medium_hit():
    """The rule is named for the pair, not the triple. `coincidence_count` was fed STRONG
    hits only, and STRONG is 0 on both real cases — 7,358 eligible, 0 fired."""
    feats = featmod.build([_txn("E1", None, 100.0, "DEBIT")], [], [],
                          medium_hits=[{"entity_id": "E1"}, {"entity_id": "E1"}])
    flags = rulemod.call_transfer_coincidence(feats, _cfg_coincidence())
    assert len(flags) == 1
    detail = flags[0]["detail"]
    assert "2 call+transfer" in detail
    assert "no overlapping IP session" in detail, "a MEDIUM hit must not read as call+IP+transfer"


def test_a_strong_hit_still_reads_as_call_ip_transfer():
    feats = featmod.build([_txn("E1", None, 100.0, "DEBIT")], [],
                          [{"entity_id": "E1"}], medium_hits=[])
    detail = rulemod.call_transfer_coincidence(feats, _cfg_coincidence())[0]["detail"]
    assert "call+IP+transfer" in detail
    assert "no overlapping IP" not in detail


def test_both_tiers_on_one_entity_are_reported_separately():
    feats = featmod.build([_txn("E1", None, 100.0, "DEBIT")], [],
                          [{"entity_id": "E1"}],
                          medium_hits=[{"entity_id": "E1"}, {"entity_id": "E1"}])
    detail = rulemod.call_transfer_coincidence(feats, _cfg_coincidence())[0]["detail"]
    assert "1 call+IP+transfer" in detail and "2 call+transfer" in detail


def test_no_coincidence_means_no_flag():
    feats = featmod.build([_txn("E1", None, 100.0, "DEBIT")], [], [], medium_hits=[])
    assert rulemod.call_transfer_coincidence(feats, _cfg_coincidence()) == []


def test_a_medium_only_hit_is_weighted_below_a_strong_one():
    """The tiers are not equal evidence. At the full weight, firing on MEDIUM handed every
    one of the 30 eligible demo entities an identical +10.5 risk points and promoted three
    into the medium band on a coincidence with no IP corroboration at all."""
    medium = featmod.build([_txn("E1", None, 100.0, "DEBIT")], [], [],
                           medium_hits=[{"entity_id": "E1"}])
    strong = featmod.build([_txn("E1", None, 100.0, "DEBIT")], [], [{"entity_id": "E1"}])
    cfg = _cfg_coincidence()

    w_medium = rulemod.call_transfer_coincidence(medium, cfg)[0]["weight"]
    w_strong = rulemod.call_transfer_coincidence(strong, cfg)[0]["weight"]
    assert w_medium < w_strong
    assert w_medium == 0.075, "absent medium_weight must default to half, not to the full weight"


def test_an_entity_with_both_tiers_keeps_the_strong_weight():
    """A corroborated hit is not diluted by also having uncorroborated ones."""
    feats = featmod.build([_txn("E1", None, 100.0, "DEBIT")], [], [{"entity_id": "E1"}],
                          medium_hits=[{"entity_id": "E1"}, {"entity_id": "E1"}])
    assert rulemod.call_transfer_coincidence(feats, _cfg_coincidence())[0]["weight"] == 0.15


def test_configured_medium_weight_is_honoured():
    cfg = {"rules": {"call_transfer_coincidence": {"enabled": True, "weight": 0.15,
                                                   "medium_weight": 0.02}}}
    feats = featmod.build([_txn("E1", None, 100.0, "DEBIT")], [], [],
                          medium_hits=[{"entity_id": "E1"}])
    flag = rulemod.call_transfer_coincidence(feats, cfg)[0]
    assert flag["weight"] == 0.02
    assert "weighted 0.02 not 0.15" in flag["detail"], "the report must state the tier's weight"


# ── a self-edge must not manufacture rapid forwarding ───────────────────────────────

def test_a_self_transfer_does_not_create_100_percent_forwarding():
    """One row crediting and debiting the same entity at the same instant satisfies both
    halves of `mule_account`. `build_transfers` refuses payer == payee, but `transfers` is a
    list this function does not own."""
    feats = featmod.build([_txn("V", None, 1.0, "DEBIT")],
                          [_transfer("SAME", "SAME", 500_000.0)], [])
    assert feats["SAME"]["max_rapid_forward"] == 0.0
    assert feats["SAME"]["credits"] == [] and feats["SAME"]["debits"] == []


def test_medium_hits_default_to_none_for_existing_callers():
    """`medium_hits` is optional so callers that predate it keep working unchanged."""
    feats = featmod.build([_txn("E1", None, 100.0, "DEBIT")], [], [])
    assert feats["E1"]["coincidence_medium_count"] == 0


# ── eligibility must be the rule's precondition, not the entity count ───────────────

def _feats_from(events, transfers, hits=(), medium=()):
    return featmod.build(events, transfers, list(hits), list(medium))


def test_mule_eligibility_counts_fan_in_not_every_entity():
    """`len(feats)` was reported for five of eight rules. On `fir-65-2024` that made
    `mule_account` read "9,996 eligible, 0 fired", which is an entity count wearing a
    diagnosis. Eligibility has to be the structural precondition — here, fan-in."""
    transfers = [_transfer(f"P{i}", "MULE", 10_000.0, minute=i) for i in range(6)]
    transfers += [_transfer("X", "THIN", 10_000.0, minute=20)]     # fan-in of 1
    feats = _feats_from([_txn("V", None, 1.0, "DEBIT")], transfers)
    cfg = {"rules": {"mule_account": {"enabled": True, "weight": 0.15,
                                      "min_fan_in": 5, "min_forwarded_pct": 0.8}}}

    row = {r["rule"]: r for r in rulemod.eligibility_report(feats, transfers, cfg)}
    assert row["mule_account"]["eligible"] == 1, "only MULE reaches fan-in >= 5"
    assert row["mule_account"]["eligible"] < len(feats)


def test_rapid_in_out_eligibility_requires_money_seen_both_ways():
    """Forwarding is only observable when money is seen arriving AND leaving. A terminal
    payee — which is what a counterparty-only entity is when you hold the victim's statement
    and not the mule's — can never satisfy it, and that is a fact about the evidence."""
    transfers = [_transfer("A", "TERMINAL", 5_000.0)]              # in only
    transfers.append(_transfer("PASS", "B", 5_000.0, minute=2))    # out only
    feats = _feats_from([_txn("V", None, 1.0, "DEBIT")], transfers)
    cfg = {"rules": {"rapid_in_out": {"enabled": True, "weight": 0.2,
                                      "min_forwarded_pct": 0.8, "max_hold_minutes": 60}}}

    row = {r["rule"]: r for r in rulemod.eligibility_report(feats, transfers, cfg)}
    assert row["rapid_in_out"]["eligible"] == 0
    assert row["rapid_in_out"]["note"] and "one-hop" in row["rapid_in_out"]["note"]


def test_zero_eligible_carries_a_sentence_explaining_the_evidence():
    """`fired=0` must not read as "nothing suspicious here" when the reason is that the
    typology's precondition does not occur in the case at all."""
    feats = _feats_from([_txn("E1", None, 100.0, "DEBIT")], [])
    cfg = {"rules": {"comm_burst": {"enabled": True, "weight": 0.1,
                                    "max_calls_per_hour": 20}}}
    row = {r["rule"]: r for r in rulemod.eligibility_report(feats, [], cfg)}["comm_burst"]
    assert row["eligible"] == 0 and row["fired"] == 0
    assert row["note"] and "no call records" in row["note"]


def test_an_eligible_rule_that_simply_found_nothing_has_no_inert_note():
    """The other half of the distinction: eligible entities exist, none crossed the
    threshold. That is a clean result and must not be annotated as inert."""
    events = [_txn("E1", None, 100.0, "CREDIT", minute=0),
              _txn("E1", None, 100.0, "DEBIT", minute=1)]
    feats = _feats_from(events, [])
    feats["E1"]["call_times"] = [T0]
    cfg = {"rules": {"comm_burst": {"enabled": True, "weight": 0.1,
                                    "max_calls_per_hour": 999}}}
    row = {r["rule"]: r for r in rulemod.eligibility_report(feats, [], cfg)}["comm_burst"]
    assert row["eligible"] == 1 and row["fired"] == 0
    assert row["note"] is None
