"""Finance<->telecom bridge tests: narration VPA phone (auto) + KYC entity_map (supplied)."""

from backend.app.entity_resolution import mapping as er_mapping
from backend.app.entity_resolution import service as er
from backend.app.normalization import narration


def test_narration_extracts_phone_vpa():
    out = narration.mine("UPI/441344919270/9876543210@ybl/PAYTM/12:35", {})
    assert out.get("counterparty_phone") == "9876543210"
    # non-phone VPA (account-like handle) must NOT be treated as a phone
    out2 = narration.mine("UPI/200644322758/11161241340@SBIN/UPI", {})
    assert "counterparty_phone" not in out2


def test_kyc_mapping_bridges_account_and_phone(tmp_path):
    # A bank account and a telecom phone that share no field in the raw data...
    events = [
        {"event_type": "TRANSACTION", "primary": ("ACCOUNT_NO", "999888"),
         "own_identifiers": [("ACCOUNT_NO", "999888")], "counterparty": None,
         "timestamp_start": None},
        {"event_type": "CALL", "primary": ("PHONE", "+919876543210"),
         "own_identifiers": [("PHONE", "+919876543210")], "counterparty": None,
         "timestamp_start": None},
    ]
    # ...are unified by an analyst KYC map.
    (tmp_path / "entity_map.csv").write_text("account_no,phone\n999888,9876543210\n")
    links = er_mapping.load_link_events(str(tmp_path))
    assert len(links) == 1
    entities, n2e = er.resolve(events + links)
    assert n2e[("ACCOUNT_NO", "999888")] == n2e[("PHONE", "+919876543210")]


def test_no_mapping_file_is_noop(tmp_path):
    assert er_mapping.load_link_events(str(tmp_path)) == []
