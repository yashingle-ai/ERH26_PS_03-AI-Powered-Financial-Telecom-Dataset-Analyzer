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


# ---- defects found by running against the real case folders -------------------------

def test_quote_wrapped_excel_accounts_are_recognized():
    """Real NCRP register cells arrive text-forced: "'50200099412403'" with the
    apostrophe intact. Typing the raw value matched nothing."""
    accounts = ["'50200099412403'", "'20100019091781'", "'10052001003779'",
                "'9946300953'", "'9848410613'", "'20100019091781'",
                "'348001503055'", "'2402251956151747'"]
    assert "account_like" in value_typer._column_types(accounts)


def test_variable_length_unique_accounts_stay_accounts():
    """A complaint register lists a different mule account per row, so it is ~100%
    unique. Demoting it to a reference lost the only column in the case carrying an
    account and a mobile on the same row."""
    accounts = ["50200099412403", "9946300953", "348001503055",
                "2402251956151747", "20100019091781", "10052001003779",
                "9848410613", "31110240170862"]
    types = value_typer._column_types(accounts)
    assert "account_like" in types
    assert "reference_like" not in types


def test_serial_column_with_per_page_resets_is_still_a_serial():
    """A multi-page PDF register restarts `S No.` on each page, so the run is not
    sorted — and the column then typed as money and claimed the balance target."""
    values = [str(i) for i in range(1, 26)] * 2
    assert value_typer._column_types(values) == {"serial": 1.0}


def test_small_integer_code_column_is_not_money():
    """A `Layer` column of 1, 2, 6 must not reach amount/debit/balance."""
    assert "amount" not in value_typer._column_types(
        ["2", "1", "1", "1", "6", "1", "2", "2", "1", "2"])


def test_fifteen_digit_indian_accounts_are_accounts():
    """28 of one real register's 173 accounts are 15 digits (Union/SBI lengths).
    Excluding all 15-digit values as IMEIs held purity at 0.68, under the gate."""
    accounts = ["040026900000174", "500101013942036", "924010036411120",
                "50200099412403", "20100019091781", "348001503055",
                "10052001003779", "31110240170862"]
    assert "account_like" in value_typer._column_types(accounts)


def test_imsi_and_phone_columns_never_become_accounts():
    """The other side of the previous test: loosening the 15-digit rule must not let a
    telecom identifier column claim an account target."""
    assert "account_like" not in value_typer._column_types(
        ["405870182224029", "404100123456789"] * 4)
    assert "account_like" not in value_typer._column_types(
        ["8180934367", "7500107305", "9876543210", "6123456789"] * 2)


def test_serial_survives_repeated_page_headings():
    """pdfplumber bleeds a repeated `S No.` heading and stray cells into column 0; four
    junk values out of 119 kept a row counter typed as money."""
    values = [str(i) for i in range(1, 30)] + ["S\nNo."] + [str(i) for i in range(1, 30)]
    assert value_typer._column_types(values) == {"serial": 1.0}


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


def test_a_rupee_statement_is_not_claimed_by_the_utc_crypto_profile():
    """`crypto_exchange_ledger` is source_tz: UTC and declares 7 fields where
    bank_generic declares 12. Ranked on coverage it wins, and every timestamp in a real
    rupee statement then shifts by 5.5 hours."""
    det = detector.detect_profile(ALIEN_HEADERS, _columns(_alien_bank_rows()))
    assert det["profile"]["profile"]["id"] == "bank_generic"
    assert (det["profile"]["profile"].get("source_tz") or "IST").upper() == "IST"


def test_value_claim_never_bypasses_required_all(bank_profile):
    """required_all means "this shape is mandatory" — no fallback may skip it."""
    profile = {
        "profile": {"id": "strict", "source": "BANK",
                    "match": {"required_all": ["Mandatory Column"]}},
        "field_map": bank_profile["field_map"],
    }
    score, inferred = value_typer.value_profile_score(
        ALIEN_HEADERS, _columns(_alien_bank_rows()), profile)
    assert score == 0.0
    assert inferred == {}


def test_no_non_ist_profile_can_ever_be_claimed_on_values():
    """Pinned as an invariant over every configured profile, not just the crypto one.

    In a window-based correlation product a 5.5-hour shift does not merely lose hits, it
    manufactures them: two events that were hours apart land inside the same window.
    """
    columns = _columns(_alien_bank_rows())
    checked = 0
    for plist in config.profiles().values():
        for profile in plist:
            tz = (profile.get("profile", {}).get("source_tz") or "IST").upper()
            if tz == "IST":
                continue
            checked += 1
            score, inferred = value_typer.value_profile_score(
                ALIEN_HEADERS, columns, profile)
            assert score == 0.0, f"{profile['profile']['id']} ({tz}) claimed on values"
            assert inferred == {}
    assert checked, "no non-IST profile configured — invariant untested"


# ---- inference must never be able to cost a file ------------------------------------

@pytest.mark.parametrize("value", ["inf", "-inf", "Infinity", "INF", "nan", "1e999"])
def test_non_finite_cells_do_not_raise(value):
    """A real LEA CDR export carries a cell that floats to infinity.
    `int(float("inf"))` raises OverflowError, not ValueError — it escaped to
    `_parse_one`, which recorded the whole file as a zero-row reject. Eleven CDR files
    and 118,510 rows vanished while the file count stayed identical."""
    assert value_typer._as_int(value) is None
    value_typer._column_types(["1", "2", "3", value, "5", "6", "7"])   # must not raise


def test_detect_profile_survives_a_broken_inference(monkeypatch):
    """The backstop. A feature whose purpose is to stop losing files must not be able to
    lose one, whatever goes wrong inside it."""
    def explode(*_a, **_k):
        raise RuntimeError("synthetic inference failure")
    monkeypatch.setattr(value_typer, "infer_targets", explode)
    monkeypatch.setattr(value_typer, "value_profile_score", explode)

    headers = ["Account No", "Tran Date", "Tran Particular", "Debit Amount"]
    columns = {h: ["x"] * 8 for h in headers}
    det = detector.detect_profile(headers, columns)
    assert det["source"] == "BANK"            # header match preserved
    assert det["value_map"] == {}             # inference degraded to nothing


# ---- administrative phones must never become subject identifiers -------------------

#: Shape of the real complaint register: mule accounts beside the investigating
#: officer's contact details.
REGISTER_HEADERS = ["S No.", "Acknowledgement No", "Account No.", "Layer", "State",
                    "District", "police Station",
                    "Name of Complain reported officer", "Designation", "Mobile Number"]


def _register_columns() -> dict[str, list]:
    accounts = ["50200099412403", "20100019091781", "10052001003779", "348001503055",
                "2402251956151747", "040026900000174", "500101013942036",
                "924010036411120"]
    mobiles = ["8977945606", "9121104794", "9490617852", "9490617772",
               "9493545781", "9440700866", "7382296138", "7382296138"]
    n = len(accounts)
    return {
        "S No.": [str(i + 1) for i in range(n)],
        "Acknowledgement No": [f"2020225000591{i}" for i in range(n)],
        "Account No.": accounts,
        "Layer": ["HDFC0001704"] * n,
        "State": ["Gujarat"] * n,
        "District": ["Surat"] * n,
        "police Station": ["CHEEPURUPALLI"] * n,
        "Name of Complain reported officer": ["N Nagaraju", "R Anuradha"] * (n // 2),
        "Designation": ["Police Constable"] * n,
        "Mobile Number": mobiles,
    }


def test_officer_mobile_never_fills_a_subject_phone_target(bank_profile):
    """94 of 98 officers in the real register have exactly one mobile, while only 10 of
    32 accounts do — the phone is a function of the officer, not the account. Linking
    them would merge mule accounts into police entities, and bridge unrelated mule
    accounts through a shared officer number."""
    assert value_typer.has_admin_role_columns(REGISTER_HEADERS)
    inferred = value_typer.infer_targets(
        REGISTER_HEADERS, _register_columns(), bank_profile)
    targets = {s["target"] for s in inferred.values()}
    assert not (targets & value_typer._SUBJECT_PHONE_TARGETS)


def test_an_ordinary_telecom_table_still_maps_its_phones():
    """The veto must not cost a real CDR its A-party column."""
    headers = ["Calling Party Number", "Called Party Number", "Call Date", "Duration"]
    columns = {
        "Calling Party Number": ["8180934367"] * 8,
        "Called Party Number": ["7500107305", "9876543210"] * 4,
        "Call Date": [f"1{i}-06-2024 10:30:00" for i in range(8)],
        "Duration": ["45", "120", "33", "600", "12", "88", "5", "301"],
    }
    assert not value_typer.has_admin_role_columns(headers)
    profile = next(p for p in config.profiles()["cdr"]
                   if p["profile"]["id"] == "cdr_generic")
    inferred = value_typer.infer_targets(headers, columns, profile)
    targets = {s["target"] for s in inferred.values()}
    assert "entity_phone" in targets or "counterparty_phone" in targets


def test_more_targets_outranks_a_smaller_profile():
    small = value_typer.value_claim_rank({"a": {"target": "timestamp_start", "confidence": 0.9},
                                          "b": {"target": "account_no", "confidence": 0.9}})
    large = value_typer.value_claim_rank({"a": {"target": "timestamp_start", "confidence": 0.8},
                                          "b": {"target": "account_no", "confidence": 0.8},
                                          "c": {"target": "debit", "confidence": 0.8}})
    assert large > small


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
