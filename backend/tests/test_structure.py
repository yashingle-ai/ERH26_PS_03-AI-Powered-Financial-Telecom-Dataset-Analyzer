"""Table-region recovery for broken grids (`ingestion.structure`).

`pdfplumber` flattens every table on every page into one list of rows. On real
cybercrime-portal exports that produced a 495-row grid yielding 14 events, because the
transaction dates sat on continuation rows discarded as padding and the column titles were
split down six rows. Recovery lifts the same folder to 389 events.

The gate matters as much as the recovery: this must not touch a grid that already parses.
"""

from __future__ import annotations

from backend.app.ingestion import service as ingestion
from backend.app.ingestion import structure
from backend.app.normalization import service as normalization

# A clean statement grid — uniform cell count, one header row, sparse money columns.
CLEAN = [
    ["Tran Date", "Tran Particular", "Debit Amount", "Credit Amount", "Balance"],
    ["01-02-2024", "UPI/1234/PAY", "", "5000.00", "15000.00"],
    ["02-02-2024", "ATM WDL SURAT", "2000.00", "", "13000.00"],
    ["03-02-2024", "NEFT-HDFC-VENDOR", "1000.00", "", "12000.00"],
    ["04-02-2024", "IMPS/9999/REFUND", "", "500.00", "12500.00"],
]

# Shape of a real NCRP portal export: a narrow complete table, then a wide table whose
# header is split across rows and whose records span several physical rows.
BROKEN = [
    ["S\nNo.", "Account No./ (Wallet", "Transaction ID", "Transaction\nAmount",
     "Transaction\nDate"],
    ["1", "-:016901567850", "413611075951", "500000", "15-05-2024\nAM/PM: AM"],
    ["2", "-:016901567850", "DG31176408", "150000", "03-07-2024\nAM/PM: AM"],
    ["3", "-:016901567850", "417712416497", "200000", "25-06-2024\nAM/PM: AM"],
    ["4", "-:016901567850", "415516935733", "230000", "03-06-2024\nAM/PM: AM"],
    # second table: wider, multi-row header, multi-row records
    ["S\nNo.", "Account\nNo./", "Action\nTaken by", "Bank", "Account Details",
     "Transaction Details", "Reference\nNo"],
    ["", "", "(Wallet/PG/PA)", "Merchant", "", "", ""],
    ["", "Transaction\nId / UTR", "", "", "", "", "Date of Action"],
    ["1", "8747048057", "Money Transfer to", "State Bank of India",
     "A/C No.-:42920748141 IFSC Code: SBIN0031048",
     "Transaction Amount-:135000 Txn Date: 14/05/2024", "NEFT:PUNBS241358"],
    ["", "4155178598", "", "", "", "", ""],
    ["", "Layer : 2", "", "", "", "", ""],
    ["2", "8747048057", "Money Transfer to", "South Indian Bank",
     "A/C No.-:05700730011 IFSC Code: SIBL0000057",
     "Transaction Amount-:300000 Txn Date: 13/05/2024", "NRTGS/PUNBR520"],
    ["", "4155178598", "", "", "", "", ""],
    ["", "Layer : 2", "", "", "", "", ""],
]


# ---- the gate ----------------------------------------------------------------------

def test_a_clean_grid_is_left_alone():
    """The regression that mattered. `needs_recovery` first measured *effective* width, so
    a statement with sparse debit/credit columns trimmed to a different width on nearly
    every row and an ordinary spreadsheet looked like glued tables — recovery then degraded
    files that already parsed, and two pipeline tests failed."""
    assert not structure.needs_recovery(CLEAN)


def test_mixed_raw_widths_need_recovery():
    assert structure.needs_recovery(BROKEN)


def test_a_degenerate_header_needs_recovery():
    """`_find_header_row` chose `['Complainant/ Victim Details View & Print']` — a one-cell
    page title — as the header for an 830-row table."""
    grid = [["Complainant/ Victim Details View & Print"]] + \
           [[f"{i}"] for i in range(1, 8)]
    assert structure.needs_recovery(grid)


def test_a_grid_too_small_to_judge_is_left_alone():
    assert not structure.needs_recovery([["a", "b"]])


# ---- recovery ----------------------------------------------------------------------

def test_both_tables_are_separated():
    regions = structure.regions(BROKEN)
    assert len(regions) == 2
    assert len(regions[0][1]) == 4          # the narrow complete table
    assert len(regions[1][1]) == 2          # two records, not six physical rows


def test_multi_row_header_is_merged_into_one_name_per_column():
    _headers_a, _rows_a = structure.regions(BROKEN)[0]
    headers, _rows = structure.regions(BROKEN)[1]
    joined = " ".join(headers)
    assert "Wallet/PG/PA" in joined        # contributed by the second header row
    assert "Date of Action" in joined      # contributed by the third


def test_continuation_rows_merge_into_the_record_above():
    _headers, rows = structure.regions(BROKEN)[1]
    assert len(rows) == 2
    assert "4155178598" in rows[0][1]     # account tail from the next physical row


def test_embedded_labelled_fields_become_columns():
    """The portal writes the transaction date and beneficiary account INSIDE a cell, so
    both are invisible to any profile. The labels recovered here — `Txn Date`, `A/C No` —
    are already aliases in the bank profiles."""
    headers, rows = structure.regions(BROKEN)[1]
    assert "Txn Date" in headers
    assert "A/C No" in headers
    date_col = headers.index("Txn Date")
    assert rows[0][date_col] == "14/05/2024"
    assert rows[1][date_col] == "13/05/2024"
    acct_col = headers.index("A/C No")
    assert rows[0][acct_col] == "42920748141"


def test_layer_is_not_promoted_to_a_column():
    """`Layer : 2` is a complaint-chain depth marker, not an evidentiary field."""
    headers, _rows = structure.regions(BROKEN)[1]
    assert "Layer" not in headers


def test_recovery_of_an_empty_grid_is_empty():
    assert structure.regions([]) == []
    assert not structure.needs_recovery([])


# ---- end to end --------------------------------------------------------------------

def test_broken_grid_yields_events_through_the_normal_path(tmp_path):
    """Recovered regions go through detection, mapping and normalization unchanged."""
    parsed = [
        ingestion._parsed_from_grid("portal.pdf", "pdf", [headers] + rows, [],
                                   table_index=i + 1)
        for i, (headers, rows) in enumerate(structure.regions(BROKEN))
    ]
    assert [pf.source_type for pf in parsed] == ["BANK", "BANK"]
    events, _rejects = normalization.normalize_parsed_files(parsed)
    assert len(events) >= 6, f"expected both tables to map, got {len(events)}"
    dates = {e["timestamp_start"].strftime("%d-%m-%Y") for e in events}
    assert "15-05-2024" in dates           # from the narrow table
    assert "14-05-2024" in dates           # only reachable via field promotion
