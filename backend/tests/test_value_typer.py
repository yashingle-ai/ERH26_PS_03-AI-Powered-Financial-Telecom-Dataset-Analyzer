"""Instance-level column typing (`ingestion.value_typer`).

The property under test throughout: a table whose column names match NO profile alias
must still be classified and mapped, from its values alone. That is the file-level drop —
an unclassified file yields `source_type=None` and normalization rejects every row in it.
"""

from __future__ import annotations

import csv

import pytest

from backend.app.core import config
from backend.app.ingestion import detector, value_typer
from backend.app.ingestion import service as ingestion
from backend.app.normalization import field_mapper
from backend.app.normalization import service as normalization

# Headers deliberately share no alias with any profile in config/profiles/**.
ALIEN_HEADERS = ["Sr", "Posting Stamp", "Ledger Folio", "Remitter Memo",
                 "Money Out", "Money In", "Running Total"]


def _alien_bank_rows(n: int = 12) -> list[dict]:
    rows, bal = [], 90000
    for i in range(n):
        out_ = f"{(i + 1) * 1000}.00" if i % 2 == 0 else ""
        in_ = "" if i % 2 == 0 else f"{(i + 1) * 500}.00"
        bal += -(i + 1) * 1000 if i % 2 == 0 else (i + 1) * 500
        rows.append({
            "Sr": str(i + 1),
            "Posting Stamp": f"1{i % 9}-06-2024 1{i % 9}:30:00",
            "Ledger Folio": "50100234567890",
            "Remitter Memo": f"UPI/41234567890{i}/PAY/abc{i}@okhdfc",
            "Money Out": out_, "Money In": in_, "Running Total": f"{bal}.00",
        })
    return rows


def _columns(rows: list[dict]) -> dict[str, list]:
    return {h: [r[h] for r in rows] for h in ALIEN_HEADERS}


@pytest.fixture
def bank_profile() -> dict:
    return next(p for p in config.profiles()["banks"]
                if p["profile"]["id"] == "bank_generic")


@pytest.fixture
def alien_inferred(bank_profile) -> dict[str, str]:
    """{header: canonical target} inferred from values for the alien statement."""
    inferred = value_typer.infer_targets(
        ALIEN_HEADERS, _columns(_alien_bank_rows()), bank_profile)
    return {h: s["target"] for h, s in inferred.items()}


# ---- value recognizers -------------------------------------------------------------

def test_recognizes_finacle_and_ncrp_datetimes():
    """Both real shapes that previously counted as "missing timestamp"."""
    assert "datetime" in value_typer._column_types(["11DEC2019:09:07:02"] * 6)
    assert "datetime" in value_typer._column_types(
        ["09-06-2024 HR: 3 MIN: 50 AM/PM: PM"] * 6)


def test_serial_column_is_never_an_account():
    """A row counter typed as an account number is a bug already paid for once."""
    types = value_typer._column_types([str(i) for i in range(1, 20)])
    assert types == {"serial": 1.0}
    assert "account_like" not in types


def test_long_digit_run_is_not_money():
    """An account column read as an amount turns an identifier into a rupee value."""
    accounts = ["50100234567890"] * 4 + ["31110240170862"] * 4
    assert "amount" not in value_typer._column_types(accounts)
    assert "account_like" in value_typer._column_types(accounts)


def test_per_row_unique_digits_are_a_reference_not_an_account():
    utrs = [f"41234567890{i}" for i in range(10)]
    types = value_typer._column_types(utrs)
    assert "reference_like" in types
    assert "account_like" not in types


def test_imei_and_imsi_separate_on_mcc_prefix():
    assert "imsi" in value_typer._column_types(["405870182224029", "404100123456789"] * 3)
    assert "imei" in value_typer._column_types(["355330170920575", "358419296846579"] * 3)


def test_clock_is_not_an_ipv6_address():
    types = value_typer._column_types(["09:07:02", "23:59:59", "00:00:01", "12:30:00"] * 2)
    assert "time" in types
    assert "ipv6" not in types


def test_too_few_values_yields_no_type():
    """Typing a column from two cells is guessing, and guessing fabricates identifiers."""
    assert value_typer._column_types(["11DEC2019:09:07:02", ""]) == {}


# ---- fuzzy header tiebreak ---------------------------------------------------------

def test_abbreviations_expand_before_comparison():
    assert value_typer.header_similarity("Txn Dt", "Transaction Date") > 0.9
    assert value_typer.header_similarity("A/C No.", "Account Number") > 0.9
    assert value_typer.header_similarity("Withdrawal Amount (INR )", "Withdrawal Amt") > 0.9


# ---- assignment --------------------------------------------------------------------

def test_alien_headers_map_from_values_alone(alien_inferred):
    assert alien_inferred["Posting Stamp"] == "timestamp_start"
    assert alien_inferred["Ledger Folio"] == "account_no"
    assert alien_inferred["Remitter Memo"] == "attributes.narration"
    assert "Sr" not in alien_inferred            # serial vetoed


def test_mutually_exclusive_amount_pair_becomes_debit_and_credit(alien_inferred):
    """`Money Out` landing on the signed `amount` target inverts half the directions."""
    assert alien_inferred["Money Out"] == "debit"
    assert alien_inferred["Money In"] == "credit"
    assert alien_inferred["Running Total"] == "attributes.balance"


def test_one_target_is_claimed_by_one_column(alien_inferred):
    targets = list(alien_inferred.values())
    assert len(targets) == len(set(targets))


# ---- detector integration ----------------------------------------------------------

def test_detector_claims_an_alien_bank_table_on_values():
    rows = _alien_bank_rows()
    det = detector.detect_profile(ALIEN_HEADERS, _columns(rows))
    assert det["source"] == "BANK"
    assert det["value_map"], "no value-based mapping produced"
    # Deliberately below auto_detect_threshold: a value-claimed file is always flagged
    # for analyst review rather than silently trusted.
    assert det["needs_manual_mapping"]


def test_headers_alone_still_yield_nothing():
    """Proves the recovery comes from values, not from a loosened header rule."""
    assert detector.detect_profile(ALIEN_HEADERS)["source"] is None


def test_declared_alias_always_beats_an_inferred_mapping():
    profile = {"field_map": {
        "timestamp_start": {"aliases": ["Tran Date"]},
        "account_no": {"aliases": ["Account No"]},
    }}
    raw = {"Tran Date": "01-02-2024 10:00:00", "Weird Stamp": "09-06-2024 15:50:00"}
    value_map = {"Weird Stamp": {"target": "timestamp_start"}}
    mapped = field_mapper.map_record(raw, profile, value_map)
    assert mapped["timestamp_start"] == "01-02-2024 10:00:00"


def test_inferred_mapping_fills_only_an_empty_target():
    profile = {"field_map": {"timestamp_start": {"aliases": ["Tran Date"]}}}
    raw = {"Tran Date": "", "Weird Stamp": "09-06-2024 15:50:00"}
    mapped = field_mapper.map_record(
        raw, profile, {"Weird Stamp": {"target": "timestamp_start"}})
    assert mapped["timestamp_start"] == "09-06-2024 15:50:00"


# ---- end to end --------------------------------------------------------------------

def test_alien_statement_survives_the_whole_pipeline(tmp_path):
    p = tmp_path / "unknown_bank.csv"
    rows = _alien_bank_rows()
    with p.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=ALIEN_HEADERS)
        w.writeheader()
        w.writerows(rows)

    pf = ingestion.parse_file(str(p))
    assert pf.source_type == "BANK"
    events, rejects = normalization.normalize_parsed_files([pf])
    assert len(events) == len(rows), f"lost rows: {rejects}"
    assert {e["direction"] for e in events} == {"DEBIT", "CREDIT"}
    assert all(e["primary"] == ("ACCOUNT_NO", "50100234567890") for e in events)


def test_flag_off_restores_the_previous_behaviour(tmp_path, monkeypatch):
    monkeypatch.setenv("ERAKSHAK_VALUE_TYPING", "0")
    p = tmp_path / "unknown_bank.csv"
    with p.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=ALIEN_HEADERS)
        w.writeheader()
        w.writerows(_alien_bank_rows())
    pf = ingestion.parse_file(str(p))
    assert pf.source_type is None
    assert pf.value_map == {}
