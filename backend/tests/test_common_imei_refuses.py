"""The `Common_*_Report` family is not all identity evidence, and only one member of it is.

Operators ship these together in one CDR folder. On `fir-65-2024` there are eight, and the
filename match deliberately claims three:

    Common_IMEI_Report          Number=IMEI     columns=MSISDN   -> identity
    IPDR_-_Common_IMEI_Report   Number=IMEI     columns=session   -> identity
    Common_A_B_Report           Number=MSISDN   columns=MSISDN   -> a COMMS edge
    Common_First_Cell_ID_*      Number=CELL ID  columns=MSISDN   -> a LOCATION edge

The five it skips look like free coverage — "5 of 8 files missed" was written down as a defect
during review — and consuming them would be rule 3: fabricating identity. A shared B-party says
nothing about who owns what, its `Number` column carries SMS sender IDs like `VG-ViCARE` that are
not subscribers at all, and merging a cell tower into a phone entity would fuse every handset that
ever used that cell into one subject.

These tests exist so the next person to notice the "missed" files finds the reason instead of the
opportunity. Fixtures are **synthetic**, in the real column layout.
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.app.entity_resolution import common_imei as ci


def _report(tmp_path, name, number_col, wide_cols, tail_col="Handset Details"):
    """A Common-* report: `Number`, `Count`, one column per cross-referenced value, then a tail."""
    cols = ["Number", "Count", *wide_cols, tail_col]
    rows = []
    for n in number_col:
        rows.append([n, len(wide_cols), *["Yes"] * len(wide_cols), "x"])
    path = tmp_path / name
    pd.DataFrame(rows, columns=cols).to_excel(path, index=False)
    return path


# ── the one member that IS identity ─────────────────────────────────────────────────

def test_a_common_imei_report_yields_imei_to_phone_links(tmp_path):
    _report(tmp_path, "CDR__1__Common_IMEI_Report.xlsx",
            ["356789894119614", "865155068217691"], ["9874834369", "9537658408"])
    links = ci.load_common_imei_links(str(tmp_path), [])
    assert len(links) == 4
    for ln in links:
        kinds = {t for t, _ in ln["own_identifiers"]}
        assert kinds == {"IMEI", "PHONE"}


# ── the members that are NOT ─────────────────────────────────────────────────────────

def test_a_common_a_b_report_is_not_read_at_all(tmp_path):
    """Number=MSISDN, columns=MSISDN. Two A-parties sharing a B-party is a communication
    co-occurrence; treating it as identity would merge unrelated subscribers."""
    _report(tmp_path, "CDR__2670__Common_A_B_Report.xlsx",
            ["7874166608", "9316511286"], ["7874166608", "9574482942"], tail_col="Circle")
    assert ci.load_common_imei_links(str(tmp_path), []) == []


def test_an_sms_sender_id_is_never_treated_as_a_subscriber(tmp_path):
    """The real `Common_A_B_Report` Number column holds `VM-611121`, `VG-ViCARE`. Those are SMS
    headers, not people."""
    _report(tmp_path, "CDR__6490__Common_A_B_Report.xlsx",
            ["VG-ViCARE", "VZ-ViCARE", "VM-611121"], ["7201803066"], tail_col="Circle")
    assert ci.load_common_imei_links(str(tmp_path), []) == []


def test_a_common_first_cell_id_report_is_not_read_at_all(tmp_path):
    """Number=CELL ID. Merging a tower into a phone entity fuses every handset that used it."""
    _report(tmp_path, "CDR__2672__Common_First_Cell_ID_A_Report.xlsx",
            ["404-5-0-80394730", "404-5-0-71394713"], ["7284882369"],
            tail_col="Tower Address")
    assert ci.load_common_imei_links(str(tmp_path), []) == []


def test_a_cell_id_that_looks_like_an_imei_by_length_is_still_refused(tmp_path):
    """`404050576321825` is 15 digits and passes the IMEI length test. The filename is what keeps
    it out, which is exactly why the filename match must stay narrow."""
    _report(tmp_path, "imei__6607__Vi__Common_First_Cell_ID_A_Report.xlsx",
            ["404050576321825", "ARETC00"],
            ["35161338815222_124268193_INC000022638761"], tail_col="Tower Address")
    assert ci.load_common_imei_links(str(tmp_path), []) == []


@pytest.mark.parametrize("name", [
    "CDR__2670__Common_A_B_Report.xlsx",
    "CDR__2672__Common_First_Cell_ID_A_Report.xlsx",
    "SomeOperator__Common_Cell_Report.xlsx",
    "Common_Report.xlsx",
])
def test_no_other_member_of_the_family_is_claimed(tmp_path, name):
    """A `common_*_report` glob would swallow all of these. Enumerated so widening the match
    breaks a test rather than a case."""
    _report(tmp_path, name, ["9874834369"], ["9537658408"], tail_col="Circle")
    assert ci.load_common_imei_links(str(tmp_path), []) == []


def test_the_match_is_on_common_imei_specifically(tmp_path):
    """Both spellings seen in real folders, and nothing looser."""
    for good in ("X__Common_IMEI_Report.xlsx", "X__common imei report.xlsx",
                 "ipdr__1__IPDR_-_Common_IMEI_Report.xlsx"):
        d = tmp_path / good.replace(".", "_")
        d.mkdir()
        _report(d, good, ["356789894119614"], ["9874834369"])
        assert ci.load_common_imei_links(str(d), []), f"{good} must be read"
