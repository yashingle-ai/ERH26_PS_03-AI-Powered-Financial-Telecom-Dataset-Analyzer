"""Finance<->telecom bridge tests: narration VPA phone (auto) + KYC entity_map (supplied)."""

from backend.app.entity_resolution import mapping as er_mapping
from backend.app.entity_resolution import service as er
from backend.app.normalization import narration
from backend.app.normalization import service as norm


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


def test_registered_mobile_only_bridges_header_account():
    """NCRP complaint tables list mule accounts in rows; complainant mobile is header-only.

    Bridging that phone onto every row account would falsely merge victim↔mule.
    """
    from datetime import datetime, timezone

    ts = datetime(2024, 6, 9, 10, 0, tzinfo=timezone.utc)
    identity = {"account_no": "111", "registered_mobile": "9876543210"}
    # subject account row -> phone attached
    subj = norm._norm_bank(
        {"account_no": "111", "timestamp_start": ts.isoformat(), "amount": "100"},
        identity, {"narration_extract": {}}, {"source_file": "t"}, "IST")
    assert ("PHONE", "+919876543210") in subj["own_identifiers"]
    # mule layer row -> account only
    mule = norm._norm_bank(
        {"account_no": "222", "timestamp_start": ts.isoformat(), "amount": "100"},
        identity, {"narration_extract": {}}, {"source_file": "t"}, "IST")
    assert mule["primary"] == ("ACCOUNT_NO", "222")
    assert all(t != "PHONE" for t, _ in mule["own_identifiers"])


def test_entity_map_ignores_comments_and_blank_lines(tmp_path):
    """This file is filled in by hand by a case officer, so it will carry notes. A commented
    instruction parsed as a data row would enter entity resolution as an identifier."""
    from backend.app.entity_resolution import mapping as er_mapping

    (tmp_path / "entity_map.csv").write_text(
        "account_no,phone,wallet,upi_id\n"
        "# NEVER INVENT A ROW — every value must come from KYC\n"
        "\n"
        "#   FIR 65-2024\n"
        "# ,9537658408,,\n"
        "50100369668648,9825504222,,\n"
        "   # indented comment\n",
        encoding="utf-8",
    )
    links = er_mapping.load_link_events(str(tmp_path))
    assert len(links) == 1, [x["own_identifiers"] for x in links]
    ids = dict(links[0]["own_identifiers"])
    assert ids["ACCOUNT_NO"] == "50100369668648"
    assert ids["PHONE"].endswith("9825504222")


def test_commented_out_template_rows_create_no_links(tmp_path):
    """The shipped template lists the five wanted MSISDNs commented out. Until an officer
    fills in the account and uncomments them they must produce nothing."""
    from backend.app.entity_resolution import mapping as er_mapping

    (tmp_path / "entity_map.csv").write_text(
        "account_no,phone,wallet,upi_id\n"
        "# ,9537658408,,\n# ,9687045370,,\n# ,9099102222,,\n",
        encoding="utf-8",
    )
    assert er_mapping.load_link_events(str(tmp_path)) == []
