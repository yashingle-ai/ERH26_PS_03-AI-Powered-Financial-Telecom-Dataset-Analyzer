"""An unclaimed table has a reason, and the four reasons want opposite responses.

FR-4 read "658 of 951 unrecognised" for weeks. By rows the same build claims 95.6% on
`fir-65-2024` — the unclaimed tables average 24 rows. And the number mixes a CCTV log that no
profile should ever claim, an officer-bearing complaint register refused on purpose, real bank data
with no timestamp that cannot become events however well mapped, and the actual parser gap.

Reported as one figure it invites building a profile for data that must not be claimed. That is
not hypothetical: the officer-bearing shape is `master - Copy.xlsx`, where linking would have
merged 32 mule accounts into ~98 police entities.

Fixtures are **synthetic**, in the real column layouts taken from the census.
"""

from __future__ import annotations

from backend.app.ingestion import unrecognised as un


class _PF:
    """Minimal stand-in for ParsedFile — this classifier only reads three attributes."""

    def __init__(self, headers, records, source_type=None):
        self.headers = headers
        self.records = records
        self.source_type = source_type


def _rows(headers, values_per_col, n=12):
    return [{h: values_per_col[h][i % len(values_per_col[h])] for h in headers}
            for i in range(n)]


# ── officer-bearing is disqualifying, and tested first ──────────────────────────────

def test_an_officer_bearing_register_is_refused_not_called_a_parser_gap():
    """The real `All Account complain.csv`: full of account numbers AND an officer column. If this
    classified as a parser gap, the fix would look like "add a profile" — which is the
    `master - Copy.xlsx` error."""
    headers = ["S No.", "Acknowledgement No", "Account No.", "IFSC Code", "State",
               "police Station", "Name of Complain reported officer", "Designation",
               "Mobile Number"]
    vals = {"S No.": ["1", "2", "3"], "Acknowledgement No": ["21310240043223"],
            "Account No.": ["100000000001", "100000000002", "100000000003"],
            "IFSC Code": ["HDFC0001234"], "State": ["Gujarat"],
            "police Station": ["Cyber"], "Name of Complain reported officer": ["PI Someone"],
            "Designation": ["PI"], "Mobile Number": ["9812345678", "9823456789"]}
    assert un.classify(_PF(headers, _rows(headers, vals))) == un.REFUSED_OFFICER


def test_officer_columns_win_even_over_a_timestamp():
    """Order matters. A register with dates AND an officer column must not read as UNREAD."""
    headers = ["Account No.", "Txn Date", "Investigating Officer"]
    vals = {"Account No.": ["100000000001", "100000000002"],
            "Txn Date": ["01/02/2024", "03/02/2024"],
            "Investigating Officer": ["PI Someone"]}
    assert un.classify(_PF(headers, _rows(headers, vals))) == un.REFUSED_OFFICER


# ── out of scope: nothing in it is Bank/CDR/IPDR shaped ─────────────────────────────

def test_a_table_with_no_canonical_field_is_out_of_scope():
    """The CCTV log: one table, 11,275 rows, 70% of everything unclaimed on `fir-65-2024`. All
    `Unnamed` headers and no column that types as an identifier, amount or time."""
    headers = ["Unnamed: 0", "Unnamed: 1", "Unnamed: 2"]
    vals = {"Unnamed: 0": ["cam-A02", "cam-A03"], "Unnamed: 1": ["ok", "ok"],
            "Unnamed: 2": ["motion", "idle"]}
    assert un.classify(_PF(headers, _rows(headers, vals))) == un.OUT_OF_SCOPE


def test_classification_is_value_based_not_filename_based():
    """A filename keyword would make this a lookup table for the two cases we happen to hold. The
    same content decides the same way whatever the file is called."""
    headers = ["Unnamed: 0", "Unnamed: 1"]
    vals = {"Unnamed: 0": ["banner text here", "more prose"],
            "Unnamed: 1": ["Google Confidential", "Google Confidential"]}
    pf = _PF(headers, _rows(headers, vals))
    assert un.classify(pf) == un.OUT_OF_SCOPE


def test_an_empty_table_is_out_of_scope_rather_than_a_gap():
    assert un.classify(_PF(["a", "b"], [])) == un.OUT_OF_SCOPE


# ── real data, no time anchor ───────────────────────────────────────────────────────

def test_a_hold_amount_table_has_no_time_anchor():
    """`BANK, ACCOUNT NO., HOLD AMOUNT` — genuine bank data. Mapping it perfectly still yields
    zero events, because there is no timestamp to place them on the timeline."""
    headers = ["BANK", "ACCOUNT NO.", "HOLD AMOUNT"]
    vals = {"BANK": ["HDFC", "SBI"],
            "ACCOUNT NO.": ["100000000001", "100000000002", "100000000003"],
            "HOLD AMOUNT": ["150000.50", "275000.00", "99000.25"]}
    assert un.classify(_PF(headers, _rows(headers, vals))) == un.NO_TIME_ANCHOR


# ── the genuine gap ─────────────────────────────────────────────────────────────────

def test_a_table_with_identifiers_and_a_timestamp_is_a_real_parser_gap():
    """This is the only reason that should drive new profile work."""
    headers = ["Acct", "When", "Amt"]
    vals = {"Acct": ["100000000001", "100000000002", "100000000003"],
            "When": ["01/02/2024 10:00", "01/02/2024 11:30", "02/02/2024 09:15"],
            "Amt": ["15000.00", "27500.00", "9900.25"]}
    assert un.classify(_PF(headers, _rows(headers, vals))) == un.UNREAD


# ── the summary keeps the old totals intact ─────────────────────────────────────────

def test_summarise_covers_every_unclaimed_table_and_ignores_claimed_ones():
    """Rule 5: `tables_by_source` and `rows_in_unrecognised_tables` keep their exact meaning, so
    every figure previously quoted still compares. This is a companion, not a redefinition."""
    claimed = _PF(["Acct", "When"], _rows(["Acct", "When"],
                  {"Acct": ["100000000001"], "When": ["01/02/2024"]}), source_type="BANK")
    cctv = _PF(["Unnamed: 0"], _rows(["Unnamed: 0"], {"Unnamed: 0": ["cam-A02"]}, n=40))
    hold = _PF(["BANK", "ACCOUNT NO.", "HOLD AMOUNT"],
               _rows(["BANK", "ACCOUNT NO.", "HOLD AMOUNT"],
                     {"BANK": ["HDFC"], "ACCOUNT NO.": ["100000000001", "100000000002"],
                      "HOLD AMOUNT": ["150000.50", "99000.25"]}, n=6))

    got = un.summarise([claimed, cctv, hold])
    assert un.OUT_OF_SCOPE in got and un.NO_TIME_ANCHOR in got
    assert got[un.OUT_OF_SCOPE] == {"tables": 1, "rows": 40}
    assert got[un.NO_TIME_ANCHOR] == {"tables": 1, "rows": 6}
    assert sum(v["tables"] for v in got.values()) == 2, "the claimed table must not appear"


def test_summarise_is_ordered_by_rows_so_the_biggest_reason_reads_first():
    small = _PF(["Unnamed: 0"], _rows(["Unnamed: 0"], {"Unnamed: 0": ["x"]}, n=2))
    big = _PF(["BANK", "ACCOUNT NO.", "HOLD AMOUNT"],
              _rows(["BANK", "ACCOUNT NO.", "HOLD AMOUNT"],
                    {"BANK": ["HDFC"], "ACCOUNT NO.": ["100000000001", "100000000002"],
                     "HOLD AMOUNT": ["150000.50", "99000.25"]}, n=99))
    assert list(un.summarise([small, big]))[0] == un.NO_TIME_ANCHOR


def test_an_empty_input_summarises_to_nothing():
    assert un.summarise([]) == {}


# ── the row-level reject reason must name WHICH precondition failed ──────────────────

def test_a_row_with_no_timestamp_and_one_with_no_identifier_are_reported_apart():
    """All three normalisers gate on a timestamp and then an identifier. Reported as one reason
    that was 60,325 rows on `fir-65-2024` — 16.5% of everything parsed — with no way to tell the
    unrecoverable half (reference data with no time) from the actionable half (a mapping gap)."""
    from backend.app.ingestion.service import ParsedFile
    from backend.app.normalization import service as norm

    pf = ParsedFile(
        path="cdr.csv", format="csv", source_type="CDR", profile_id="cdr_generic",
        confidence=1.0, needs_manual_mapping=False,
        headers=["Call Date", "A-Party"],
        records=[
            {"Call Date": "01/02/2024 10:00", "A-Party": "9876543210"},   # good
            {"Call Date": "", "A-Party": "9876543210"},                   # no time
            {"Call Date": "01/02/2024 11:00", "A-Party": ""},             # no identifier
        ],
    )
    events, rejects = norm.normalize_parsed_files([pf])
    reasons = {r["reason"]: r["rejected"] for r in rejects}
    no_time = [v for k, v in reasons.items() if "no timestamp" in k]
    no_id = [v for k, v in reasons.items() if "no mapped primary identifier" in k]
    assert no_time == [1], f"expected one no-timestamp row, got {reasons}"
    assert no_id == [1], f"expected one no-identifier row, got {reasons}"
    assert len(events) == 1


def test_the_two_reasons_still_sum_to_every_rejected_row():
    """Rule 2 arithmetic: splitting a reason must not lose or double-count a row."""
    from backend.app.ingestion.service import ParsedFile
    from backend.app.normalization import service as norm

    records = ([{"Call Date": "", "A-Party": "9876543210"}] * 4
               + [{"Call Date": "01/02/2024 11:00", "A-Party": ""}] * 3
               # distinct times: identical rows are removed by dedupe, which is a third reason
               # and would muddle the arithmetic under test
               + [{"Call Date": "01/02/2024 12:00", "A-Party": "9812345678"},
                  {"Call Date": "01/02/2024 13:00", "A-Party": "9812345678"}])
    pf = ParsedFile(path="c.csv", format="csv", source_type="CDR", profile_id="cdr_generic",
                    confidence=1.0, needs_manual_mapping=False,
                    headers=["Call Date", "A-Party"], records=records)
    events, rejects = norm.normalize_parsed_files([pf])
    assert len(events) == 2
    split = sum(r["rejected"] for r in rejects
                if "no timestamp" in r["reason"] or "no mapped primary identifier" in r["reason"])
    assert split == 7, f"the two reasons must account for every gated row, got {rejects}"
