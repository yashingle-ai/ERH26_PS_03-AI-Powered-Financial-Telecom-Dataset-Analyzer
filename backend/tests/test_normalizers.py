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
