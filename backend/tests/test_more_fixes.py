"""Tests for the second remediation batch: A4, A5, C2, C4/C5, C3, B5, G2."""

from datetime import datetime, timedelta, timezone

from backend.app.entity_resolution import suggestions
from backend.app.normalization import narration, validation


def test_c4_account_vpa_and_c5_payee():
    out = narration.mine("UPI/200644322758/11161241340@sbi/RIYA ENTERPRISE/REF", {})
    assert out.get("counterparty_account") == "11161241340"      # C4
    assert "RIYA" in (out.get("counterparty_name") or "").upper()  # C5


def test_c4_phone_vpa_still_wins():
    out = narration.mine("UPI/x/9876543210@ybl/JOHN/REF", {})
    assert out.get("counterparty_phone") == "9876543210"
    assert "counterparty_account" not in out


def test_a5_balance_break_detected():
    ist = timezone(timedelta(hours=5, minutes=30))
    def ev(t, direction, amt, bal):
        return {"event_type": "TRANSACTION", "asset": "INR", "primary": ("ACCOUNT_NO", "A1"),
                "direction": direction, "amount": amt,
                "timestamp_start": datetime(2024, 8, 1, t, tzinfo=ist),
                "attributes": {"balance": bal, "ref_no": f"R{t}"}}
    # 1000 -> +500 = 1500 (ok) -> -200 should be 1300 but stated 9999 (break)
    events = [ev(9, "CREDIT", 500, 1500), ev(10, "DEBIT", 200, 9999)]
    rep = validation.check_balances(events)
    assert rep and rep[0]["breaks"] == 1


def test_a4_crypto_value_inr():
    from backend.app.core import config
    assert config.crypto_rate_inr("USDT")            # known token has a rate
    assert config.crypto_rate_inr("NOPECOIN") is None


def test_c2_ipdr_msisdn_from_filename():
    from backend.app.normalization import service as norm
    mapped = {"ip_public": "2409:40d2::1", "date_col": "20241125", "time_col": "132132"}
    prov = {"source_file": "9099102222_ipdr.xlsx"}
    ev = norm._norm_ipdr(mapped, prov, source_tz="IST")
    assert ev and ev["primary"] == ("PHONE", "+919099102222")


def test_c3_fuzzy_suggestions_review_only():
    entities = {"E1": {"label": "Ramesh Kumar Patel"}, "E2": {"label": "Ramesh Kumr Patel"},
                "E3": {"label": "Completely Different"}}
    s = suggestions.suggest(entities, threshold=0.85)
    pair = {frozenset((x["entity_a"], x["entity_b"])) for x in s}
    assert frozenset(("E1", "E2")) in pair
    # suggestions never mutate entities
    assert "merged" not in entities["E1"]


def test_b5_profile_writer(tmp_path, monkeypatch):
    from backend.app.core import config
    from backend.app.ingestion import mapping_writer
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    path = mapping_writer.save_profile("custom_bank", "BANK", "TRANSACTION",
                                       {"account_no": ["Ac_No"], "debit": ["Dr_Amt"]},
                                       ["Ac_No"])
    assert path.endswith(".yaml")
    import yaml
    doc = yaml.safe_load(open(path))
    assert doc["profile"]["source"] == "BANK"
    assert doc["field_map"]["account_no"]["aliases"] == ["Ac_No"]
