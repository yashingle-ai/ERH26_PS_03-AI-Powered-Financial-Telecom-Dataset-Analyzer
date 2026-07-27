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
