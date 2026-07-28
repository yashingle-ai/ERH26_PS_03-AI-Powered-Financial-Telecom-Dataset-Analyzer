"""RBL / Finacle SOA PDF headers must score as bank_generic (not unrecognised)."""

from backend.app.ingestion import detector


def test_rbl_soa_headers_match_bank_generic():
    headers = [
        "Account No", "Tran Date", "Value Date", "Instrument Num.",
        "Tran Particular", "Tran Crncy Code", "Debit Amount", "Credit Amount",
    ]
    det = detector.detect_profile(headers)
    assert det["source"] == "BANK"
    assert det["profile"]["profile"]["id"] == "bank_generic"
    assert det["confidence"] > 0.3
    assert not det["needs_manual_mapping"]
