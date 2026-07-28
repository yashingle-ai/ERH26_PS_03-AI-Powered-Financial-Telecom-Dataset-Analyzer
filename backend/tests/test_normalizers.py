from backend.app.normalization import normalizers as nz


def test_phone_e164():
    assert nz.phone("9876543210") == "+919876543210"
    assert nz.phone("+91 98765 43210") == "+919876543210"
    assert nz.phone("098765-43210") == "+919876543210"
    assert nz.phone("") is None


def test_amount_parsing():
    assert nz.amount("1,23,456.78") == 123456.78
    assert nz.amount("INR 500") == 500.0
    assert nz.amount("") is None


def test_datetime_iso_vs_ddmmyyyy():
    # ISO must NOT be day-first swapped
    iso = nz.parse_dt("2026-06-01 20:44:49")
    assert (iso.month, iso.day) == (6, 1)
    # Indian bank dd/mm/yyyy must be day-first
    ddmm = nz.parse_dt("01/06/2026 20:47:49")
    assert (ddmm.month, ddmm.day) == (6, 1)
    assert iso.tzinfo is not None  # tz applied


def test_core_banking_datetime_with_colon_separator():
    """`11DEC2019:09:07:02` — Finacle/ICORE and SAS exports join date and time
    with a colon. dateutil parses the date half alone but rejects the whole
    string, so every row of such a statement was dropped for "missing
    timestamp": 95% of bank rows on a real case.
    """
    dt = nz.parse_dt("11DEC2019:09:07:02")
    assert dt is not None
    assert (dt.year, dt.month, dt.day) == (2019, 12, 11)
    assert (dt.hour, dt.minute, dt.second) == (9, 7, 2)

    # fractional seconds, 2-digit hour, and quoted values all occur in the wild
    assert nz.parse_dt("01JAN2020:00:00:00.500") is not None
    assert nz.parse_dt("'11DEC2019:09:07:02'") is not None
    # date-only and genuinely bad input must behave as before
    assert nz.parse_dt("11DEC2019") is not None
    assert nz.parse_dt("garbage") is None
    assert nz.parse_dt("") is None


def test_ncrp_complaint_multiline_datetime():
    """NCRP complaint PDFs split date/time across lines inside one cell."""
    dt = nz.parse_dt("09-06-2024\nHR: 3\nMIN: 50\nAM/PM: PM")
    assert dt is not None
    assert (dt.year, dt.month, dt.day) == (2024, 6, 9)
    assert (dt.hour, dt.minute) == (15, 50)

    # date + AM/PM only (no HR/MIN) still yields the calendar day
    d2 = nz.parse_dt("15-05-2024\nAM/PM: AM")
    assert d2 is not None
    assert (d2.year, d2.month, d2.day) == (2024, 5, 15)


def test_ncrp_account_cell_cleaning():
    assert nz.account_no("-:39951540286") == "39951540286"
    assert nz.account_no("201029737717\nLayer : 1") == "201029737717"
    assert nz.account_no("  9180300823909  ") == "9180300823909"
    assert nz.account_no("") is None


def test_alias_precedence_prefers_the_profile_order_not_column_order():
    """Several columns claim `timestamp_start`; the profile's order must decide.

    An ICORE statement carries Tran_Date, pstd_dt and value_dt. Resolving by raw
    column order let the rightmost win, so an empty `value_dt` silently replaced
    a clean `Tran_Date`.
    """
    from backend.app.normalization import field_mapper

    profile = {"field_map": {"timestamp_start": {
        "aliases": ["Tran_Date", "pstd_dt", "value_dt"]}}}

    # all three present -> the profile's first choice wins
    assert field_mapper.map_record(
        {"Tran_Date": "11-12-2019", "pstd_dt": "11DEC2019:09:07:02", "value_dt": ""},
        profile) == {"timestamp_start": "11-12-2019"}

    # preferred alias empty -> fall through to the next non-empty one
    assert field_mapper.map_record(
        {"Tran_Date": "", "pstd_dt": "11DEC2019:09:07:02"},
        profile) == {"timestamp_start": "11DEC2019:09:07:02"}

    # only a low-priority alias present -> still mapped
    assert field_mapper.map_record({"value_dt": "2020-01-01"}, profile) == {
        "timestamp_start": "2020-01-01"}

    # column order must not matter
    assert field_mapper.map_record(
        {"value_dt": "2020-01-01", "Tran_Date": "11-12-2019"},
        profile) == {"timestamp_start": "11-12-2019"}


def test_field_mapper_collapses_whitespace_in_pdf_headers():
    """PDF extracts embed newlines in NCRP column titles; aliases must still match."""
    from backend.app.normalization import field_mapper

    profile = {"field_map": {
        "account_no": {"aliases": ["Account No./ (Wallet /PG/PA) ID"]},
        "timestamp_start": {"aliases": ["Transaction Date"]},
        "amount": {"aliases": ["Transaction Amount"]},
    }}
    mapped = field_mapper.map_record({
        "Account No./ (Wallet\n/PG/PA) ID": "-:39951540286",
        "Transaction\nDate": "09-06-2024\nHR: 3\nMIN: 50\nAM/PM: PM",
        "Transaction\nAmount": "90000",
    }, profile)
    assert mapped["account_no"] == "-:39951540286"
    assert "09-06-2024" in mapped["timestamp_start"]
    assert mapped["amount"] == "90000"


def test_field_mapper_shared_alias_fills_multiple_targets():
    """Target/A must populate both entity_phone and target_phone (IMEI attach needs both)."""
    from backend.app.normalization import field_mapper

    profile = {"field_map": {
        "entity_phone": {"aliases": ["Target /A PARTY NUMBER", "A PARTY NUMBER"]},
        "target_phone": {"aliases": ["Target /A PARTY NUMBER"]},
    }}
    mapped = field_mapper.map_record(
        {"Target /A PARTY NUMBER": "9876543210", "B PARTY NUMBER": "9123456789"},
        profile)
    assert mapped["entity_phone"] == "9876543210"
    assert mapped["target_phone"] == "9876543210"


def test_time_only_value_is_refused_not_dated_today():
    """A value with no date must be rejected, never stamped with today's date.

    "Time" is a timestamp_start alias (exchange ledgers carry only that column). If a
    file supplies a bare time, dateutil fills in *today* — a 2019 row would enter the
    timeline dated now. Worse, every such row gets the same fabricated date and lands
    within minutes of the others, which can manufacture correlation hits. A counted
    reject is correct; an invented timestamp is not.
    """
    for bare_time in ("13:45:00", "09:07", "1:05 PM", "00:00:00"):
        assert nz.parse_dt(bare_time) is None, bare_time

    # date-bearing values must still parse, including the awkward real-world ones
    assert nz.parse_dt("11DEC2019:09:07:02") is not None
    assert nz.parse_dt("11-12-2019") is not None
    assert nz.parse_dt("2019-12-11 09:07:02") is not None
    assert nz.parse_dt("11DEC2019") is not None          # date-only is a real date
    assert nz.parse_dt("01/06/2026 20:47:49") is not None

    # and the date must be the one in the value, not a probe default
    dt = nz.parse_dt("11-12-2019")
    assert (dt.year, dt.month, dt.day) == (2019, 12, 11)
