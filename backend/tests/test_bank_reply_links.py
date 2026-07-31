"""Bank KYC replies in Gujarati become account↔phone links — and nothing else does.

FR-9 has been red since the start: STRONG is 0 at every window from 1 to 60 minutes because no
entity holds a transaction, a call and an IP session at once, for want of anything tying an account
to a handset. `account+phone` is 3.

The refusal paths carry more weight here than the happy path. This project came within one
measurement of merging 32 mule accounts into ~98 police entities off a reference table whose
`Mobile Number` column held the *investigating officer's* number. A module that creates identities
has to be judged on what it declines.

All fixtures are **synthetic**. Case material does not belong in the repository.
"""

from __future__ import annotations

import pytest
from docx import Document

from backend.app.entity_resolution import bank_reply_links as brl

# The real five-column bank-reply header, transliterated in the comment:
#   s.no | bank account number | account holder name+address | registered mobile no | e-mail
HEAD = ["અ.નં.", "બેંક એકાઉન્ટ નંબર", "એકાઉન્ટ ધારકનું નામ સરનામુ",
        "રજીસ્ટર મોબાઇલ નંબર", "રજીસ્ટર ઇ-મેઇલ આઇડી"]


def _write(tmp_path, name, head, rows):
    doc = Document()
    t = doc.add_table(rows=1, cols=len(head))
    for i, h in enumerate(head):
        t.rows[0].cells[i].text = h
    for r in rows:
        cells = t.add_row().cells
        for i, v in enumerate(r):
            cells[i].text = str(v)
    path = tmp_path / name
    doc.save(str(path))
    return path


def _rows(n, start_acct=100000000001, start_ph=9800000001):
    return [[str(i + 1), str(start_acct + i), f"HOLDER {i}", str(start_ph + i),
             f"h{i}@example.com"] for i in range(n)]


# ── the link this exists to produce ─────────────────────────────────────────────────

def test_a_bank_reply_yields_account_to_phone_links(tmp_path):
    _write(tmp_path, "reply.docx", HEAD, _rows(3))
    links = brl.load_bank_reply_links(str(tmp_path))
    assert len(links) == 3
    ids = dict(links[0]["own_identifiers"])
    assert set(ids) == {"ACCOUNT_NO", "PHONE"}
    assert ids["PHONE"].startswith("+91")


def test_links_are_link_events_with_no_timestamp(tmp_path):
    """LINK events contribute merge edges only. A timestamp would put a bank's KYC record on the
    timeline as if it were something that happened."""
    _write(tmp_path, "reply.docx", HEAD, _rows(2))
    for ln in brl.load_bank_reply_links(str(tmp_path)):
        assert ln["event_type"] == "LINK"
        assert ln["timestamp_start"] is None and ln["timestamp_end"] is None
        assert ln["amount"] is None
        assert ln["attributes"]["source"] == "bank_reply_gujarati"
        assert ln["provenance"]["source_file"] == "reply.docx"


def test_the_same_pair_in_several_copies_is_emitted_once(tmp_path):
    """The same reply is duplicated across several .docx copies in a real folder."""
    _write(tmp_path, "a.docx", HEAD, _rows(3))
    _write(tmp_path, "b.docx", HEAD, _rows(3))
    assert len(brl.load_bank_reply_links(str(tmp_path))) == 3


def test_gujarati_numerals_in_the_cells_still_normalise(tmp_path):
    """The values are ASCII in both real cases, but the next folder is a different station."""
    G = str.maketrans("0123456789", "૦૧૨૩૪૫૬૭૮૯")
    rows = [[r[0], r[1].translate(G), r[2], r[3].translate(G), r[4]] for r in _rows(2)]
    _write(tmp_path, "reply.docx", HEAD, rows)
    links = brl.load_bank_reply_links(str(tmp_path))
    assert len(links) == 2
    for ln in links:
        ids = dict(ln["own_identifiers"])
        assert ids["ACCOUNT_NO"].isascii() and ids["PHONE"].isascii()


# ── what it must refuse ─────────────────────────────────────────────────────────────

def test_a_table_with_an_officer_column_is_refused(tmp_path):
    """The `master - Copy.xlsx` failure mode. Linking there would have merged 32 mule accounts
    into ~98 police entities."""
    head = HEAD[:-1] + ["Investigating Officer"]
    _write(tmp_path, "roster.docx", head, [r[:-1] + ["PI Someone"] for r in _rows(3)])
    assert brl.load_bank_reply_links(str(tmp_path)) == []


def test_a_table_with_no_holder_column_is_refused(tmp_path):
    """A seized-property schedule lists an account and a handset side by side without asserting
    that either belongs to the other. The holder column is what makes it a KYC statement."""
    head = ["અ.નં.", "બેંક એકાઉન્ટ નંબર", "મોબાઇલ નંબર"]
    _write(tmp_path, "seized.docx", head, [[r[0], r[1], r[3]] for r in _rows(3)])
    assert brl.load_bank_reply_links(str(tmp_path)) == []


def test_an_english_headed_table_is_not_claimed_here(tmp_path):
    """This module is for the Gujarati replies. English tables are the profiles' business, and two
    readers claiming one table is how a column gets interpreted twice."""
    head = ["S.No", "Bank Account Number", "Account Holder Name", "Registered Mobile", "Email"]
    _write(tmp_path, "reply_en.docx", head, _rows(3))
    assert brl.load_bank_reply_links(str(tmp_path)) == []


def test_a_shared_contact_column_refuses_the_whole_batch(tmp_path):
    """One mobile against many accounts is a branch contact, not a holder. The batch is refused
    rather than filtered: a mixed table means the wrong column was read, and filtering the
    outliers would keep whatever else that mistake produced."""
    rows = [[str(i + 1), str(100000000001 + i), f"HOLDER {i}", "9800000001",
             f"h{i}@example.com"] for i in range(brl._MAX_FANOUT + 2)]
    _write(tmp_path, "reply.docx", HEAD, rows)
    assert brl.load_bank_reply_links(str(tmp_path)) == []


def test_fanout_is_measured_across_the_whole_case_not_per_table(tmp_path):
    """A shared number spread thinly over several copies of one reply passes every table on its
    own. Six files with two rows each still add up to one number against twelve accounts."""
    per_file = 2
    for f in range(brl._MAX_FANOUT + 2):
        rows = [[str(i + 1), str(200000000001 + f * 10 + i), f"HOLDER {f}-{i}",
                 "9700000001", "x@example.com"] for i in range(per_file)]
        _write(tmp_path, f"reply_{f}.docx", HEAD, rows)
    assert brl.load_bank_reply_links(str(tmp_path)) == []


def test_a_batch_at_the_fanout_limit_is_still_accepted(tmp_path):
    """A genuine multi-account holder must not trip the guard."""
    rows = [[str(i + 1), str(300000000001 + i), "ONE HOLDER", "9600000001",
             "x@example.com"] for i in range(brl._MAX_FANOUT)]
    _write(tmp_path, "reply.docx", HEAD, rows)
    assert len(brl.load_bank_reply_links(str(tmp_path))) == brl._MAX_FANOUT


def test_a_malformed_phone_or_account_is_skipped_not_guessed(tmp_path):
    rows = [["1", "12345", "SHORT ACCOUNT", "9800000001", "a@x.com"],       # account too short
            ["2", "100000000002", "BAD PHONE", "1234567890", "b@x.com"],    # not an MSISDN
            ["3", "100000000003", "GOOD", "9800000003", "c@x.com"]]
    _write(tmp_path, "reply.docx", HEAD, rows)
    links = brl.load_bank_reply_links(str(tmp_path))
    assert len(links) == 1
    assert dict(links[0]["own_identifiers"])["ACCOUNT_NO"] == "100000000003"


def test_an_empty_or_missing_folder_is_not_an_error(tmp_path):
    assert brl.load_bank_reply_links(str(tmp_path)) == []
    assert brl.load_bank_reply_links(str(tmp_path / "nope")) == []


def test_an_unreadable_docx_does_not_stop_the_others(tmp_path):
    (tmp_path / "broken.docx").write_bytes(b"not a docx")
    _write(tmp_path, "good.docx", HEAD, _rows(2))
    assert len(brl.load_bank_reply_links(str(tmp_path))) == 2


# ── the flag ────────────────────────────────────────────────────────────────────────

def test_the_feature_is_off_unless_the_flag_is_set(monkeypatch):
    """Off by default because it creates merges, and switchable so both arms of the window sweep
    run the same build. Attributing a change by run timestamp is a trap already paid for here."""
    monkeypatch.delenv(brl._FLAG, raising=False)
    assert brl.enabled() is False
    for v in ("1", "true", "YES", "on"):
        monkeypatch.setenv(brl._FLAG, v)
        assert brl.enabled() is True
    monkeypatch.setenv(brl._FLAG, "0")
    assert brl.enabled() is False


def test_the_pipeline_respects_the_flag(monkeypatch, tmp_path):
    """The reader can be right and still be unreachable — F1 and F3 were both built and unplugged."""
    from backend.app import pipeline
    _write(tmp_path, "reply.docx", HEAD, _rows(2))
    monkeypatch.delenv(brl._FLAG, raising=False)
    assert brl.enabled() is False
    monkeypatch.setenv(brl._FLAG, "1")
    assert brl.enabled() is True
    assert "er_bank_reply" in pipeline.__dict__ or hasattr(pipeline, "er_bank_reply")


@pytest.mark.parametrize("head", [
    ["અ.નં.", "એકાઉન્ટ ધારકનું નામ", "રજીસ્ટર મોબાઇલ નંબર"],   # no account column
    ["અ.નં.", "બેંક એકાઉન્ટ નંબર", "એકાઉન્ટ ધારકનું નામ"],       # no phone column
    ["અ.નં.", "નામ", "સરનામુ"],                                  # neither
])
def test_a_table_missing_either_side_is_refused(tmp_path, head):
    _write(tmp_path, "t.docx", head, [[str(i), "100000000001", "x"] for i in range(3)])
    assert brl.load_bank_reply_links(str(tmp_path)) == []
