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


# ── Archives: evidence sealed inside (nested) ZIPs ─────────────────────────────
# On the real case, 92 archives were never opened — 83 structured files plus 129 PDFs
# sat inside them, and nothing reported the omission.

def _zip_with(tmp_path, name, entries):
    import zipfile
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as zf:
        for member, body in entries.items():
            zf.writestr(member, body)
    return p


def test_archive_members_are_parsed(tmp_path):
    _zip_with(tmp_path, "bank.zip", {"stmt.csv": "Amount,Date\n10,01-08-2024\n"})
    parsed = ing.parse_directory(str(tmp_path), include_pdf=False)
    assert [p.records[0]["Amount"] for p in parsed if p.records] == ["10"]


def test_archive_provenance_names_the_container(tmp_path):
    """A statement pulled out of bank.zip must still cite the exhibit it came from."""
    _zip_with(tmp_path, "bank.zip", {"stmt.csv": "Amount,Date\n10,01-08-2024\n"})
    parsed = [p for p in ing.parse_directory(str(tmp_path), include_pdf=False) if p.records]

    assert parsed[0].container == "bank.zip"
    assert parsed[0].records[0]["_provenance"]["source_file"] == "bank.zip → stmt.csv"


def test_nested_archives_are_expanded(tmp_path):
    import io
    import zipfile
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("deep.csv", "Amount,Date\n99,01-08-2024\n")
    _zip_with(tmp_path, "outer.zip", {"inner.zip": inner.getvalue()})

    parsed = [p for p in ing.parse_directory(str(tmp_path), include_pdf=False) if p.records]
    assert parsed and parsed[0].records[0]["Amount"] == "99"


def test_archive_skips_macos_noise(tmp_path):
    _zip_with(tmp_path, "a.zip", {
        "real.csv": "Amount,Date\n10,01-08-2024\n",
        "__MACOSX/._real.csv": "\x00\x05\x16\x07",
        "._real.csv": "\x00\x05\x16\x07",
    })
    parsed = ing.parse_directory(str(tmp_path), include_pdf=False)
    assert len(parsed) == 1


def test_archive_refuses_path_traversal(tmp_path):
    """A crafted member must not be written outside the extraction directory."""
    from backend.app.ingestion.parsers import archive

    _zip_with(tmp_path, "evil.zip", {"../escaped.csv": "Amount\n1\n"})
    dest = tmp_path / "out"
    extracted = archive.extract_archive(str(tmp_path / "evil.zip"), dest,
                                        max_total_bytes=1 << 20)

    assert extracted == []
    assert not (tmp_path / "escaped.csv").exists()


def test_archive_respects_expansion_budget(tmp_path):
    """A zip bomb must stop at the budget rather than filling the disk."""
    from backend.app.ingestion.parsers import archive

    _zip_with(tmp_path, "big.zip", {"a.csv": "x" * 5000, "b.csv": "y" * 5000})
    extracted = archive.extract_archive(str(tmp_path / "big.zip"), tmp_path / "o",
                                        max_total_bytes=6000)
    assert len(extracted) == 1  # first fits, second exceeds the remaining budget


def test_encrypted_archive_does_not_abort_the_batch(tmp_path):
    """Operators send password-protected archives; zipfile raises a bare RuntimeError.

    One locked member must not lose the rest of the archive — and must never abort the
    whole case, which is what happened before this was handled per-member.
    """
    import zipfile

    from backend.app.ingestion.parsers import archive

    p = tmp_path / "locked.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("open.csv", "Amount\n1\n")
    # Mark one member encrypted without a real password (flag bit 0x1).
    with zipfile.ZipFile(p, "a") as zf:
        zf.writestr("secret.csv", "Amount\n2\n")
    with zipfile.ZipFile(p, "a") as zf:
        zf.infolist()[-1].flag_bits |= 0x1

    extracted = archive.extract_archive(str(p), tmp_path / "o", max_total_bytes=1 << 20)
    assert any(f.name == "open.csv" for f in extracted)


# ── Word documents hold many tables, not one ───────────────────────────────────

def _docx_with_tables(path, tables):
    from docx import Document
    doc = Document()
    for rows in tables:
        t = doc.add_table(rows=len(rows), cols=len(rows[0]))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                t.cell(r, c).text = val
    doc.save(path)


def test_read_all_grids_returns_every_table(tmp_path):
    from backend.app.ingestion.parsers import docx_tables

    p = tmp_path / "ca_report.docx"
    _docx_with_tables(p, [
        [["Account Number", "IFSC"], ["111", "AAA"]],
        [["Account Number", "IFSC"], ["222", "BBB"]],
        [["Account Number", "IFSC"], ["333", "CCC"]],
    ])
    grids = docx_tables.read_all_grids(str(p))
    assert len(grids) == 3


def test_multi_table_docx_yields_one_parsedfile_per_table(tmp_path):
    """Keeping only the largest table discarded 2,540 of 5,430 real rows."""
    p = tmp_path / "ca_report.docx"
    _docx_with_tables(p, [
        [["Account Number", "IFSC"], ["111", "AAA"]],
        [["Account Number", "IFSC"], ["222", "BBB"]],
    ])
    parsed = ing.parse_file_multi(str(p))

    assert len(parsed) == 2
    assert [pf.table_index for pf in parsed] == [1, 2]
    values = sorted(r["Account Number"] for pf in parsed for r in pf.records)
    assert values == ["111", "222"]


# ── Finacle/IndusInd bulk SOA: FORACID + DEDIT_AMOUNT ──────────────────────────
# statement bulk.xls (6,975 rows on fir-65-2024) matched bank_generic then lost
# every row: the account lived in FORACID (not an alias) and debit was misspelled
# DEDIT_AMOUNT. Timestamp parsed fine — reject reason was "no account".

FINACLE_BULK_CSV = (
    "FORACID,ACCT_NAME,TRAN_DATE,TRAN_PARTICULAR,DEDIT_AMOUNT,CREDIT_AMOUNT,TRAN_ID\n"
    "100240778506,BAMBHANIYA A,09-05-24,UPI/CR/okaxis,0,20249,S90294351\n"
    "100240778506,BAMBHANIYA A,10-05-24,UPI/DR/okaxis,500,0,S90294352\n"
)


def test_finacle_foracid_bulk_statement_survives_normalization(tmp_path):
    from backend.app.normalization import service as norm

    p = tmp_path / "statement_bulk.csv"
    p.write_text(FINACLE_BULK_CSV, encoding="utf-8")
    pf = ing.parse_file(str(p))
    assert pf.source_type == "BANK"
    assert len(pf.records) == 2

    events, rejects = norm.normalize_parsed_files([pf])
    assert len(events) == 2, rejects
    assert events[0]["primary"] == ("ACCOUNT_NO", "100240778506")
    assert events[0]["direction"] == "CREDIT" and events[0]["amount"] == 20249.0
    assert events[1]["direction"] == "DEBIT" and events[1]["amount"] == 500.0


# ── Exchange wallet ledger: Time + User ID + signed Amount ─────────────────────
# wallet_details / BNB reports (6,683 rejected rows) matched bank_generic at 0.25
# via Description, then every row lost its timestamp because `Time` was not a
# date alias and `User ID` was not an account alias.

EXCHANGE_LEDGER_CSV = (
    "Transaction ID,User ID,Currency,Type,Amount,Available,Description,Time\n"
    "256506709293,1020260104,USDT,Product withdrawal success,-19,0,"
    "Automatically confirm,2025-04-21 14:04:10\n"
    "243255041159,1014659199,USDC,Future transfer,0.1082099,0.1082099,"
    "Clear Zombie users,2025-02-16 21:50:49\n"
)


def test_exchange_wallet_ledger_survives_normalization(tmp_path):
    from backend.app.normalization import service as norm

    p = tmp_path / "wallet_details.csv"
    p.write_text(EXCHANGE_LEDGER_CSV, encoding="utf-8")
    pf = ing.parse_file(str(p))
    assert pf.source_type == "BANK"
    assert pf.profile_id in {"crypto_exchange_ledger", "bank_generic"}

    events, rejects = norm.normalize_parsed_files([pf])
    assert len(events) == 2, (rejects, pf.profile_id, pf.headers)
    assert events[0]["primary"][0] == "ACCOUNT_NO"
    assert events[0]["direction"] == "DEBIT" and events[0]["amount"] == 19.0
    assert events[0]["asset"] == "CRYPTO:USDT"
    assert events[1]["direction"] == "CREDIT"
    assert events[1]["asset"] == "CRYPTO:USDC"


# ── Tab-separated IPDR range export ────────────────────────────────────────────
# ipdr__1365.txt is the same schema as the working .xlsx, but tab-delimited.
# Default comma sep kept the header as one column → unrecognized source, 9/9 lost.

IPDR_TAB_TXT = (
    "IP\tVALUE\tF DATE\tF TIME\tT DATE\tT TIME\n"
    "IPV6\t2409:40d2:1328:a31c::1\t20241226\t135728\t20241226\t140128\n"
    "IPV6\t2409:40d2:132d:b3f8::2\t20241125\t132132\t20241125\t132532\n"
)


def test_tab_separated_ipdr_txt_is_recognized(tmp_path):
    from backend.app.normalization import service as norm

    p = tmp_path / "ipdr_range.txt"
    p.write_text(IPDR_TAB_TXT, encoding="utf-8")
    pf = ing.parse_file(str(p))
    assert pf.source_type == "IPDR", (pf.source_type, pf.headers, pf.profile_id)
    assert len(pf.records) == 2

    events, rejects = norm.normalize_parsed_files([pf])
    assert len(events) == 2, rejects
    assert events[0]["event_type"] == "IP_SESSION"


def test_registered_mobile_survives_country_code_separator():
    """"Mobile: +91 8180934367" must yield the whole number, not "+91".

    The old digits-only pattern stopped at the first space, so three of four real
    statements extracted the bare country code. A country code identifies nobody, and
    each one lost is a lost account-to-phone bridge — the exact link FR-9 needs.
    """
    from backend.app.ingestion.service import _extract_identity

    for text, expect in [
        ("Registered Mobile: +91 8180934367", "+918180934367"),
        ("Registered Mobile : +91-81809 34367", "+918180934367"),
        ("Mobile Number: 8180934367", "8180934367"),
        ("Customer Mobile: 0 8180934367", "08180934367"),
    ]:
        got = _extract_identity([], [text])
        assert got.get("registered_mobile") == expect, f"{text!r} -> {got}"

    # a country code with no number must be refused, not stored
    assert "registered_mobile" not in _extract_identity([], ["Registered Mobile: +91"])
    assert "registered_mobile" not in _extract_identity([], ["Registered Mobile: -"])

    # split across grid cells: ["Registered Mobile", "+91", "8180934367"]
    grid = [["Registered Mobile", "+91", "8180934367"]]
    assert _extract_identity(grid, []).get("registered_mobile") == "+918180934367"

    # names must be unaffected by the numeric path
    assert _extract_identity([], ["Account Name: Smita Gawali"]).get("account_holder")
