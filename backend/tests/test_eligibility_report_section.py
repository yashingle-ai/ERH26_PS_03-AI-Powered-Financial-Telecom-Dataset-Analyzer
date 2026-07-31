"""Section 6 of the forensic report must carry the whole inert note, in both formats.

The note is the sentence that stops `fired = 0` reading as "nothing suspicious here". It was
being cut at 96 characters, which is shorter than every note the detector produces — so the
reader received the premise and not the conclusion, in the document most likely to be relied
on. Same defect class as the STR grounds truncated at 5 and 3, in the same file.
"""

from __future__ import annotations

from backend.app.detection import rules as rulemod
from backend.app.reporting import service as reporting


def _elig_data(rows):
    return {"risk": {}, "entities": {}, "rule_eligibility": rows,
            "summary": {}, "input_dir": "x", "window": 10}


def test_the_longest_inert_note_survives_intact():
    longest = max(rulemod._INERT_NOTES.values(), key=len)
    assert len(longest) > 96, "if the notes got shorter, this test stopped guarding anything"

    rows = reporting._eligibility_rows(_elig_data(
        [{"rule": "rapid_in_out", "enabled": True, "eligible": 0, "fired": 0,
          "note": longest}]))
    assert rows[1][4] == longest


def test_every_configured_inert_note_survives_intact():
    rows = reporting._eligibility_rows(_elig_data(
        [{"rule": name, "enabled": True, "eligible": 0, "fired": 0, "note": note}
         for name, note in rulemod._INERT_NOTES.items()]))
    got = {r[0]: r[4] for r in rows[1:]}
    for name, note in rulemod._INERT_NOTES.items():
        assert got[name] == note, f"{name}'s note was altered on the way to the report"


def test_a_missing_note_renders_as_empty_not_as_none():
    rows = reporting._eligibility_rows(_elig_data(
        [{"rule": "comm_burst", "enabled": True, "eligible": 12, "fired": 3, "note": None}]))
    assert rows[1][4] == ""


def test_the_note_reaches_the_rendered_pdf_and_docx(tmp_path):
    """Rendered, not just assembled: the PDF path wraps this column, and a wrap that throws
    would take the whole report with it."""
    note = max(rulemod._INERT_NOTES.values(), key=len)
    data = _elig_data([{"rule": "mule_account", "enabled": True, "eligible": 0, "fired": 0,
                        "note": note}])
    data["summary"] = {"files": 1, "events": 1, "transactions": 1, "calls": 0, "ip_sessions": 0,
                       "entities": 1, "correlation_hits": 0, "transfers": 0,
                       "high_risk_entities": 0, "rejected_rows": 0}
    data.update({"correlation_hits": [], "transfers": [], "data_quality": []})

    pdf = reporting._generate_pdf(data, str(tmp_path))
    assert open(pdf, "rb").read(4) == b"%PDF"
    docx = reporting._generate_docx(data, str(tmp_path))
    assert open(docx, "rb").read(2) == b"PK"

    from docx import Document
    cells = [c.text for t in Document(docx).tables for row in t.rows for c in row.cells]
    assert note in cells, "the DOCX table dropped or clipped the note"
