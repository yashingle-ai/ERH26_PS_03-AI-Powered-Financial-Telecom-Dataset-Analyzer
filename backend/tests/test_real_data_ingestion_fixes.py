"""Regression tests for ingestion bugs found by running the pipeline over real case data.

Each test encodes a failure that was silently discarding evidence — the pipeline reported
success while dropping rows or whole files. Fixtures reproduce the exact shapes seen in
the real FIR exports (no real data is committed).
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from backend.app.ingestion import detector
from backend.app.ingestion import service as ing
from backend.app.ingestion.parsers import tabular

IST = timezone(timedelta(hours=5, minutes=30))


# ── Trailing-comma CSV: data rows carry one more field than the header ──────────
# pandas resolves that by promoting column 0 to the index, shifting every column left.
# In the real Vodafone-Idea CDR this put "Incoming" in the A-party phone column and a
# duration in the call-date column, so normalization rejected 42,873 of 42,873 rows.

TRAILING_COMMA_CSV = (
    "Target /A PARTY NUMBER,CALL_TYPE,B PARTY NUMBER,Call date,Call Initiation Time\n"
    "919702000558,Incoming,918141122818,01-08-2024,00:04:06,\n"
    "919702000558,Outgoing,919870386595,01-08-2024,00:04:18,\n"
)


def test_trailing_comma_csv_does_not_shift_columns(tmp_path):
    p = tmp_path / "cdr.csv"
    p.write_text(TRAILING_COMMA_CSV, encoding="utf-8")

    df = tabular.read(str(p))

    # The A-party column must hold the phone number, not the call type.
    assert df["Target /A PARTY NUMBER"].iloc[0] == "919702000558"
    assert df["CALL_TYPE"].iloc[0] == "Incoming"
    assert df["Call date"].iloc[0] == "01-08-2024"


def test_trailing_comma_csv_rows_survive_ingestion(tmp_path):
    p = tmp_path / "cdr.csv"
    p.write_text(TRAILING_COMMA_CSV, encoding="utf-8")

    pf = ing.parse_file(str(p))

    assert len(pf.records) == 2
    assert pf.records[0]["Target /A PARTY NUMBER"] == "919702000558"


# ── Duplicate / blank header names silently overwrote earlier columns ───────────

def test_duplicate_headers_are_disambiguated():
    out = ing._dedupe_headers(["Amount", "Date", "Amount", "", "Amount"])
    assert out == ["Amount", "Date", "Amount__2", "column_3", "Amount__3"]
    assert len(set(out)) == len(out)


def test_duplicate_headers_keep_every_column(tmp_path):
    p = tmp_path / "dup.csv"
    p.write_text("Amount,Amount\n10,20\n", encoding="utf-8")

    pf = ing.parse_file(str(p))

    # Both columns must survive; previously the second overwrote the first.
    assert len(pf.records) == 1
    assert sorted(v for k, v in pf.records[0].items() if k != "_provenance") == ["10", "20"]


# ── Extensions lie: sniff the container instead of trusting the suffix ──────────

def test_sniff_detects_zip_regardless_of_extension(tmp_path):
    p = tmp_path / "actually_xlsx.xls"          # xlsx content named .xls
    p.write_bytes(b"PK\x03\x04" + b"\x00" * 32)
    assert detector.sniff_container(str(p)) == "zip"
    assert detector.detect_format(str(p)) == "xlsx"


def test_sniff_detects_legacy_ole2_xls(tmp_path):
    p = tmp_path / "legacy.xls"
    p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32)
    assert detector.sniff_container(str(p)) == "ole2"
    assert detector.detect_format(str(p)) == "xlsx"


def test_text_report_named_xls_falls_back_to_delimited(tmp_path):
    # A real Bank of Baroda export is a fixed-width text report named .xls. It must not
    # reach the Excel reader (opaque "format cannot be determined" error).
    p = tmp_path / "report.xls"
    p.write_text("\r\n\r\n 23-07-2025  BANK OF BARODA   Page 1\r\n", encoding="utf-8")
    assert detector.sniff_container(str(p)) == "text"
    assert detector.detect_format(str(p)) == "csv"


def test_docx_still_resolves_to_docx(tmp_path):
    p = tmp_path / "tables.docx"
    p.write_bytes(b"PK\x03\x04" + b"\x00" * 32)
    assert detector.detect_format(str(p)) == "docx"


def test_appledouble_is_rejected_by_format_detection(tmp_path):
    p = tmp_path / "._report.xlsx"
    p.write_bytes(b"\x00\x05\x16\x07" + b"\x00" * 32)
    assert detector.sniff_container(str(p)) == "appledouble"
    with pytest.raises(ValueError, match="AppleDouble"):
        detector.detect_format(str(p))


# ── macOS sidecars must never be walked as evidence ────────────────────────────

def test_parse_directory_skips_appledouble_and_macosx(tmp_path):
    (tmp_path / "real.csv").write_text("Amount,Date\n10,01-08-2024\n", encoding="utf-8")
    (tmp_path / "._real.csv").write_bytes(b"\x00\x05\x16\x07" + b"\x00" * 32)
    macosx = tmp_path / "__MACOSX"
    macosx.mkdir()
    (macosx / "real.csv").write_bytes(b"\x00\x05\x16\x07" + b"\x00" * 32)

    parsed = ing.parse_directory(str(tmp_path), include_pdf=False)

    names = [p.path.replace("\\", "/").rsplit("/", 1)[-1] for p in parsed]
    assert names == ["real.csv"]


# ── /v1/events sort must not mix naive and aware datetimes ─────────────────────

def test_event_sort_fallback_is_timezone_aware():
    """Event timestamps are tz-aware; a naive datetime.min fallback raises TypeError
    and turns GET /v1/events into a 500."""
    events = [
        {"timestamp_start": datetime(2026, 6, 1, 22, 44, tzinfo=IST)},
        {"timestamp_start": None},
    ]
    ordered = sorted(
        events,
        key=lambda e: e.get("timestamp_start") or datetime.min.replace(tzinfo=UTC),
    )
    assert ordered[0]["timestamp_start"] is None


# ── Profile-matching gate ──────────────────────────────────────────────────────

def test_required_any_gate_is_actually_enforced():
    """`match` lives under the `profile:` block. Reading it from the top level returned
    {} for every profile, so the gate never fired and real IPDR exports were scored as
    CDR on shared IMEI/IMSI columns alone."""
    profile = {
        "profile": {"id": "x", "source": "CDR",
                    "match": {"required_any": ["A PARTY NUMBER"]}},
        "field_map": {"imei": {"aliases": ["IMEI"]}, "imsi": {"aliases": ["IMSI"]}},
    }
    # Shares IMEI/IMSI but has no A-party -> must be rejected outright, not scored.
    assert detector.score_profile(["IMEI", "IMSI", "Public IP Address"], profile) == 0.0
    assert detector.score_profile(["A PARTY NUMBER", "IMEI"], profile) > 0.0


def test_required_all_gate_is_enforced():
    profile = {
        "profile": {"id": "x", "match": {"required_all": ["IMEI", "IMSI"]}},
        "field_map": {"imei": {"aliases": ["IMEI"]}, "imsi": {"aliases": ["IMSI"]}},
    }
    assert detector.score_profile(["IMEI"], profile) == 0.0
    assert detector.score_profile(["IMEI", "IMSI"], profile) > 0.0


def test_every_profile_gate_is_reachable_from_its_own_aliases():
    """A required_any entry that appears in no field_map alias is almost always drift:
    the gate then rejects files the profile is otherwise able to map. This caught
    cdr_vodafone_idea, whose gate omitted the Mobile_No dialect it maps."""
    from backend.app.core import config

    problems = []
    for plist in config.profiles().values():
        for prof in plist:
            gate = prof.get("profile", {}).get("match", {}).get("required_any", [])
            if not gate:
                continue
            aliases = {a.strip().lower()
                       for spec in prof.get("field_map", {}).values()
                       for a in spec.get("aliases", [])}
            unknown = [g for g in gate if g.strip().lower() not in aliases]
            if unknown:
                problems.append((prof["profile"]["id"], unknown))
    assert not problems, f"required_any entries not present in any alias list: {problems}"
