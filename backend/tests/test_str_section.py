"""FR-17: the STR draft section, read against real output rather than assumed correct.

The section shipped inside the forensic report but had never been reviewed for content. Four
problems were visible the moment it was printed: no traceable identifier, no transaction
particulars, silently truncated grounds, and a recommendation to freeze an account on an
automatically-scored medium entity.
"""

from __future__ import annotations

from backend.app.reporting.service import _STR_MAX_BASIS, _STR_MAX_GROUNDS, _str_lines


def _row(eid, label, score, band, n_flags, txn_count=10):
    return {
        "entity_id": eid,
        "label": label,
        "risk_score": score,
        "band": band,
        "rule_flags": [{"rule": f"rule_{i}", "detail": f"detail {i}", "weight": 0.1}
                       for i in range(n_flags)],
        "features": {"txn_count": txn_count, "total_in": 1000.0, "total_out": 900.0},
    }


def _data(rows, entities=None):
    return {"risk": {r["entity_id"]: r for r in rows}, "entities": entities or {}}


# ── grounds must never be dropped without saying so ──────────────────────────────

def test_truncated_grounds_are_declared_not_dropped():
    """Real output showed `(+1 further typology)` and `(+3 further grounds on file)`, so
    grounds genuinely were being lost. Silently shortening the grounds of suspicion in the
    document a regulator reads is the exact failure rule 2 exists to prevent."""
    extra = 4
    rows = [_row("E1", "Subject A", 90.0, "high", _STR_MAX_GROUNDS + extra)]
    line = _str_lines(_data(rows))[0]

    assert f"+{extra} further typolog" in line
    dropped_basis = (_STR_MAX_GROUNDS + extra) - _STR_MAX_BASIS
    assert f"+{dropped_basis} further ground" in line


def test_grounds_within_the_cap_carry_no_truncation_note():
    line = _str_lines(_data([_row("E1", "A", 90.0, "high", 2)]))[0]
    assert "further typolog" not in line
    assert "further ground" not in line


# ── the subject must be identifiable ─────────────────────────────────────────────

def test_subject_is_named_by_typed_identifier():
    """On real data `label` is a bare account number, so "Suspected subject: 50100369668648"
    leaves the reader guessing what the number is. An STR has to name the account."""
    entities = {"E1": {"identifiers": {("ACCOUNT_NO", "50100369668648"),
                                       ("PHONE", "+919825504222")}}}
    line = _str_lines(_data([_row("E1", "Subject A", 90.0, "high", 2)], entities))[0]
    assert "ACCOUNT_NO:50100369668648" in line
    assert "PHONE:+919825504222" in line


def test_many_identifiers_are_summarised_with_a_count():
    entities = {"E1": {"identifiers": {("ACCOUNT_NO", f"{i:012d}") for i in range(9)}}}
    line = _str_lines(_data([_row("E1", "A", 90.0, "high", 2)], entities))[0]
    assert "+5 more" in line


def test_subject_falls_back_to_the_label_when_no_identifier_is_typed():
    line = _str_lines(_data([_row("E1", "Subject A", 90.0, "high", 2)]))[0]
    assert "Subject A" in line and "[" not in line.split("| Risk")[0]


# ── particulars ──────────────────────────────────────────────────────────────────

def test_particulars_state_transaction_volume():
    line = _str_lines(_data([_row("E1", "A", 90.0, "high", 2, txn_count=129)]))[0]
    assert "129 transaction(s)" in line


def test_a_subject_with_no_attributed_transactions_says_so():
    """A counterparty-only entity has an empty transaction vector. Printing zeros would
    read as "no money moved" when it means "none was attributed to this subject"."""
    line = _str_lines(_data([_row("E1", "A", 90.0, "high", 2, txn_count=0)]))[0]
    assert "no transactions attributed" in line


# ── the recommendation must be proportionate ─────────────────────────────────────

def test_medium_band_is_not_recommended_for_filing_or_freezing():
    """The previous wording recommended "file STR with FIU-IND; freeze/monitor per SOP" for
    every high AND medium entity — firing down to a score of 48.6. Freezing a real account
    holder's funds is not an action a rules engine should propose unprompted."""
    line = _str_lines(_data([_row("E1", "A", 48.6, "medium", 3)]))[0]
    assert "freeze" not in line.lower()
    assert "analyst review" in line.lower()


def test_high_band_is_put_forward_subject_to_confirmation():
    line = _str_lines(_data([_row("E1", "A", 92.5, "high", 3)]))[0]
    assert "analyst confirmation" in line.lower()
    assert "freeze" not in line.lower()


# ── empty state ──────────────────────────────────────────────────────────────────

def test_empty_state_distinguishes_nothing_matched_from_nothing_assessed():
    lines = _str_lines(_data([_row("E1", "A", 10.0, "low", 2)]))
    assert len(lines) == 1
    assert "not that nothing was" in lines[0]


def test_an_entity_with_no_fired_typology_is_excluded():
    rows = [_row("E1", "A", 95.0, "high", 0), _row("E2", "B", 80.0, "high", 2)]
    lines = _str_lines(_data(rows))
    assert len(lines) == 1
    assert "B" in lines[0]
