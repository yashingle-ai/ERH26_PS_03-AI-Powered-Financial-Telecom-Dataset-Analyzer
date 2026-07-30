"""Fixed-width printed statements (`parsers.fixed_width`).

The largest block of still-unrecognised rows on `fir-65-2024` was `.txt` — 7,331 rows
whose headers came out as `['Unnamed: 0']` because a printed statement has no delimiter,
so pandas returned the whole file as one column and no profile could match it.

These files also have no column header row at all, so the columns can only be identified
from their values. That makes this the case the instance-level matcher exists for.
"""

from __future__ import annotations

import re
import textwrap

from backend.app.ingestion import detector
from backend.app.ingestion import service as ingestion
from backend.app.ingestion.parsers import fixed_width
from backend.app.normalization import service as normalization

# Shape of a real HDFC printed statement: free-text preamble, no header row, space-aligned
# columns, narration wrapping onto continuation lines, and the preamble repeated per page.
PREAMBLE = textwrap.dedent("""\
       C/O SHIV CREATION                          City           : SURAT 395002
       Nomination    : Registered                 Account No.    : 50200059660555     CARM
       Statement From: 19/07/21                   A/C open date  : 19/07/2021

    """)

#: (date, narration, ref, debit, credit) — balances are derived so the ledger must close.
#: Each money column carries at least `value_typer._MIN_SAMPLES` values on purpose: below
#: that floor a column is not typed at all, and typing a column from three cells would be
#: guessing at exactly the point where a wrong guess invents a transaction value.
_ROWS = [
    ("19/07/21", "CU1901494271SHIV CREATION", "503851", None, 30000.00),
    ("26/07/21", "IMPS-120712183651-SIGNZY", "120712183651", None, 1.05),
    ("29/07/21", "DEBIT CARD ISSUANCE FEE", "CDT2120905123231", 236.00, None),
    ("06/08/21", "IMPS-121819086994-SIGNZY", "121819086994", None, 1.09),
    ("14/08/21", "NEFT CHARGE", "NEF2214009466183", 23.60, None),
    ("20/08/21", "ATW-419188XXXXXX9981-SURAT", "ATW2120905123999", 20000.00, None),
    ("25/08/21", "UPI-COLLECT-SIGNZY", "UPI2120905123111", None, 5000.00),
    ("02/09/21", "NEFT-DR-HDFC-VENDOR", "NEF2225009466999", 1500.00, None),
    ("10/09/21", "IMPS-CR-SIGNZY-REFUND", "IMP2225309466123", None, 250.75),
    ("15/09/21", "ATM WDL SURAT SAHARA", "ATW2225809466456", 493.29, None),
]

#: Column start offsets, matching the print layout of a real statement.
_LAYOUT = [3, 14, 48, 66, 80, 96, 112]


def _row(date="", narr="", ref="", valdate="", debit="", credit="", balance="") -> str:
    line = ""
    for start, text in zip(_LAYOUT, (date, narr, ref, valdate, debit, credit, balance)):
        line = line.ljust(start) + str(text)
    return line


def _statement(rows=None, repeat_preamble: bool = False) -> str:
    rows = _ROWS if rows is None else rows
    out = [PREAMBLE.rstrip("\n"), ""]
    balance = 0.0
    for i, (date, narr, ref, debit, credit) in enumerate(rows):
        balance += (credit or 0.0) - (debit or 0.0)
        out.append(_row(date, narr, ref, date,
                        f"{debit:,.2f}" if debit else "",
                        f"{credit:,.2f}" if credit else "",
                        f"{balance:,.2f}"))
        if i == 1:      # narration wraps onto two continuation lines
            out.append(_row(narr="TECHNOLOGIES-HDFC-ACCOUNT"))
            out.append(_row(narr="VERIFICATION"))
        if repeat_preamble and i == 5:
            out.append(PREAMBLE.rstrip("\n"))
    return "\n".join(out) + "\n"


STATEMENT = _statement()


def _write(tmp_path, text: str, name: str = "Statement.txt"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# ---- detection ---------------------------------------------------------------------

def test_a_printed_statement_is_detected_as_fixed_width(tmp_path):
    p = _write(tmp_path, STATEMENT)
    assert fixed_width.looks_fixed_width(str(p))
    assert detector.detect_format(str(p)) == "fixed"


def test_a_comma_delimited_file_is_left_to_pandas(tmp_path):
    csv = "Date,Narration,Debit,Credit\n19/07/21,ATM,100.00,\n26/07/21,NEFT,,50.00\n" * 3
    p = _write(tmp_path, csv, "delimited.txt")
    assert not fixed_width.looks_fixed_width(str(p))
    assert detector.detect_format(str(p)) == "csv"


def test_a_cctv_log_is_not_a_statement(tmp_path):
    """A Hikvision DVR log sits in the same case folder — 11,275 lines of prose. Its
    lines begin `User: admin Date:...`, not with a date in the left margin, so the
    record-start anchor must exclude it rather than invent a table."""
    log = textwrap.dedent("""\
        ***************************************************
        * Copyright Hikvision Digital Technology Co., Ltd. *
        ***************************************************

        1207 logs output

        User: admin Date:02/12/2024 Time: 18:21:54 made video search
        User: admin Date:02/12/2024 Time: 18:22:11 made video playback
        User: admin Date:02/12/2024 Time: 18:25:02 made local login
        User: admin Date:02/12/2024 Time: 18:31:40 made video search
        """)
    p = _write(tmp_path, log, "A02_log.txt")
    assert not fixed_width.looks_fixed_width(str(p))


def test_too_few_records_is_not_a_table(tmp_path):
    """Two lines cannot establish a column boundary — every position they happen to
    share would look like a separator."""
    p = _write(tmp_path, "   19/07/21   ATM        100.00\n   26/07/21   NEFT        50.00\n")
    assert not fixed_width.looks_fixed_width(str(p))


# ---- structure ---------------------------------------------------------------------

def test_columns_are_inferred_and_continuations_coalesced(tmp_path):
    p = _write(tmp_path, STATEMENT)
    preamble, grid = fixed_width.read(str(p))
    assert any("Account No." in ln for ln in preamble)
    # header + one row per record, NOT one per physical line: the narration wraps twice.
    assert len(grid) == len(_ROWS) + 1
    narration = grid[2][1]
    assert "TECHNOLOGIES-HDFC-ACCOUNT" in narration and "VERIFICATION" in narration


def test_repeated_page_preamble_is_not_coalesced_into_a_record(tmp_path):
    """A multi-page statement repeats its whole preamble, and those repeats fall BETWEEN
    record lines. Coalescing them produced a narration of joined address fragments."""
    p = _write(tmp_path, _statement(repeat_preamble=True))
    _pre, grid = fixed_width.read(str(p))
    assert all("Nomination" not in c and "SURAT 395002" not in c
               for row in grid for c in row)
    assert len(grid) == len(_ROWS) + 1
    assert any("UPI-COLLECT-SIGNZY" in c for row in grid for c in row)


# ---- end to end --------------------------------------------------------------------

def test_statement_with_no_header_row_yields_reconciling_events(tmp_path):
    """The payoff case: no column names exist, so every field is identified from values.

    Asserting the ledger reconciles is the real test — it can only hold if debit, credit
    and balance each landed on the right column.
    """
    p = _write(tmp_path, STATEMENT)
    pf = ingestion.parse_file(str(p))
    assert pf.format == "fixed"
    assert pf.source_type == "BANK"
    assert pf.header_identity.get("account_no") == "50200059660555"

    targets = {s["target"] for s in pf.value_map.values()}
    assert {"timestamp_start", "debit", "credit", "attributes.balance"} <= targets

    events, _ = normalization.normalize_parsed_files([pf])
    assert len(events) == len(_ROWS)
    events.sort(key=lambda e: e["timestamp_start"])
    balance = None
    for e in events:
        amount = e["amount"]
        signed = -amount if e["direction"] == "DEBIT" else amount
        if balance is not None:
            assert abs((balance + signed) - e["attributes"]["balance"]) < 0.01, (
                f"ledger break at {e['timestamp_start']}: "
                f"{balance} {signed:+} != {e['attributes']['balance']}")
        balance = e["attributes"]["balance"]


def test_direction_follows_the_balance_not_the_column_order(tmp_path):
    """Proves orientation is evidence-based rather than conventional.

    Here the CREDIT column is printed to the LEFT of the debit column — the opposite of the
    usual layout. With unnamed columns the first implementation broke the tie alphabetically
    (`credit` < `debit`) and inverted every direction in the file. Only the balance delta
    can tell them apart.
    """
    lines = [PREAMBLE.rstrip("\n"), ""]
    balance = 0.0
    for date, narr, ref, debit, credit in _ROWS:
        balance += (credit or 0.0) - (debit or 0.0)
        # credit in the left money column, debit in the right — deliberately reversed
        lines.append(_row(date, narr, ref, date,
                          f"{credit:,.2f}" if credit else "",
                          f"{debit:,.2f}" if debit else "",
                          f"{balance:,.2f}"))
    p = _write(tmp_path, "\n".join(lines) + "\n", "reversed.txt")

    pf = ingestion.parse_file(str(p))
    events, _ = normalization.normalize_parsed_files([pf])
    assert len(events) == len(_ROWS)
    by_narration = {e["attributes"]["narration"]: e for e in events}
    assert by_narration["NEFT CHARGE"]["direction"] == "DEBIT"
    assert by_narration["UPI-COLLECT-SIGNZY"]["direction"] == "CREDIT"


def test_small_decimal_amount_is_money_not_a_clock(tmp_path):
    """`23.60` matched `_TIME` as 23:60, so `_is_amount` rejected it as temporal and a
    real debit column of 42 values typed as nothing."""
    p = _write(tmp_path, STATEMENT)
    pf = ingestion.parse_file(str(p))
    events, _ = normalization.normalize_parsed_files([pf])
    charge = [e for e in events if "NEFT CHARGE" in (e["attributes"]["narration"] or "")]
    assert charge and charge[0]["amount"] == 23.60
    assert charge[0]["direction"] == "DEBIT"


# ── Bank of Baroda "Customer Account Ledger Report" ────────────────────────────────
#
# A second fixed-width layout, and one that yielded ZERO events until three separate
# assumptions were corrected. Measured across both real case folders: 0 -> 743 events.

#: Built with the same field widths as `_bob_row` so the header words sit over their own
#: columns, which is what a real printed ledger does and what midpoint assignment relies on.
_BOB_HEADER = (
    "-" * 106 + "\n"
    f" {'GL.':<10}  {'Value':<10}  {'Particulars':<32}  "
    f"{'Transaction':>13}  {'Transaction':>14}  {'Balance':>15}\n"
    f" {'Date':<10}  {'Date':<10}  {'':<32}  "
    f"{'Debit Amount':>13}  {'Credit Amount':>14}  {'':>15}\n"
    + "-" * 106 + "\n"
)


def _bob(rows: list[str]) -> str:
    """A BoB ledger: report banner, preamble, ruled two-line header, then records."""
    return (
        " 23-07-2025 18:20:58        BANK OF BARODA, SFS MANSAROVAR, RAJASTHAN\n"
        "                          Customer Account Ledger Report\n"
        " Account No       : 39770200001891    INR SHUBHAM FASHION\n"
        " Opening Balance  :          1,24,081.00Cr\n"
        + _BOB_HEADER
        + "\n".join(rows)
        + "\n"
    )


def _bob_row(day: int, narration: str, debit: str = "", credit: str = "") -> str:
    """Two spaces between every field — that is what makes the layout inferable."""
    return (f" {day:02d}-04-2024  {day:02d}-04-2024  {narration:<32}  "
            f"{debit:>13}  {credit:>14}  {'1,24,081.00Cr':>15}")


def test_one_malformed_row_must_not_collapse_two_columns(tmp_path):
    """`_boundaries` required a position to be blank in EVERY record line, so a single bad
    row merged the GL date and value date into `02-04-2024  02-04-2024`. That cell parses as
    neither date and `_norm_bank` dropped every row — 731 of them on the real file."""
    rows = [_bob_row(d, f"RTGS-TRANSFER-{d}",
                     **({"credit": "3,01,000.00"} if d % 2 else {"debit": "2,000.00"}))
            for d in range(2, 20)]
    # one row where the two dates are separated by a single space, not two
    rows.append(" 21-04-2024 21-04-2024  SINGLE SPACE ROW                    "
                "     1,000.00                   1,24,081.00Cr")
    p = _write(tmp_path, _bob(rows), "bob.txt")

    pf = ingestion.parse_file(str(p))
    events, _ = normalization.normalize_parsed_files([pf])
    assert len(events) >= len(rows) - 1, "the malformed row collapsed the date columns"
    assert all(e["timestamp_start"] is not None for e in events)


def test_report_banner_is_not_a_transaction(tmp_path):
    """The banner `23-07-2025 18:20:58  BANK OF BARODA...` starts with a date, so it matched
    `_RECORD_START` and became record 1. That put the first record at the banner, leaving no
    preamble to search and burying the real column header inside the record block."""
    rows = [_bob_row(d, f"NEFT-{d}",
                     **({"credit": "3,01,000.00"} if d % 2 else {"debit": "1,10,000.00"}))
            for d in range(2, 12)]
    p = _write(tmp_path, _bob(rows), "bob_banner.txt")

    lines = fixed_width._lines(str(p))
    starts = fixed_width._record_lines(lines)
    assert starts, "no records detected"
    first = lines[starts[0]]
    assert "BANK OF BARODA" not in first
    assert re.match(r"^\s*\d{2}-04-2024", first)


def test_real_column_names_are_recovered_from_the_header_block(tmp_path):
    """Synthesising `column_0..N` threw away `Particulars`, `Debit Amount` and
    `Credit Amount` — all existing profile aliases. Character-slicing the header gave
    `'lue te'` for `Value Date`, so words are assigned by midpoint instead."""
    rows = [_bob_row(d, f"RTGS-PAYEE-{d}",
                     **({"credit": "2,50,000.00"} if d % 2 else {"debit": "5,000.00"}))
            for d in range(2, 14)]
    p = _write(tmp_path, _bob(rows), "bob_header.txt")

    _preamble, grid = fixed_width.read(str(p))
    headers = grid[0]
    assert not any(h.startswith("column_") for h in headers[:3]), headers
    joined = " | ".join(headers)
    assert "Particulars" in joined
    assert "Date" in joined
    # no truncated fragments of real words
    assert "lue te" not in joined


def test_bob_ledger_produces_events_with_account_from_the_preamble(tmp_path):
    """End to end: the account number lives in the preamble, and `_norm_bank` drops any row
    without one."""
    rows = [_bob_row(d, f"RTGS-SENDER-{d}",
                     **({"credit": "3,77,000.00"} if d % 2 else {"debit": "9,000.00"}))
            for d in range(2, 16)]
    p = _write(tmp_path, _bob(rows), "bob_e2e.txt")

    pf = ingestion.parse_file(str(p))
    assert pf.source_type == "BANK"
    assert pf.header_identity.get("account_no") == "39770200001891"
    events, _ = normalization.normalize_parsed_files([pf])
    assert events
    assert all(e["primary"] == ("ACCOUNT_NO", "39770200001891") for e in events)
