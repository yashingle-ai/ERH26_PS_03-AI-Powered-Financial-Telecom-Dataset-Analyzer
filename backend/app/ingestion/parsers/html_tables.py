"""HTML reader -> (text_lines, table_grid). Legal-process web exports (FR-3, FR-10).

Why HTML is worth a parser at all. `_walk` only opens extensions in
`detector.FORMAT_BY_EXT`, so every `.html` in a case folder was skipped without even a
reject entry — 8 files in `FIR 65-2024` and 15 in `FIR-0006-2025 U`. Opening one showed
what was being thrown away: Google's response to legal process, carrying

  * the subscriber's OWN phone numbers, e-mail and account id — an identity bridge whose
    ownership the document itself asserts, unlike the officer contact numbers in a
    complaint register; and
  * an IP ACTIVITY table of timestamped logins with public IPv4/IPv6 addresses.

The second is the interesting one. FR-9 is blocked because the case's IPDR identifiers
appear nowhere outside the IPDR files themselves, and these login records are an
independent source of timestamped IP activity already tied to a phone number.

Two structural notes that the profile depends on:

  * Google stamps every timestamp `Z`. The profile declares `source_tz: UTC`; read as IST
    each login would land 5.5 hours early and correlate against the wrong window.
  * The subscriber's phone lives in the document's header block, not in the activity
    table, and only BANK normalizers receive `header_identity`. Rather than widen that
    plumbing, the subject's identifiers are denormalized onto every activity row here —
    the same thing `header_identity` does for a bank statement, done in the reader where
    the format is already understood.
"""

from __future__ import annotations

import re
from pathlib import Path

from lxml import html as lxml_html

#: Heading that identifies a Google legal-process subscriber response.
_GOOGLE_MARKER = "GOOGLE SUBSCRIBER INFORMATION"

#: Columns appended to the activity grid, carrying the document's subject onto each row.
COL_MSISDN = "Subscriber MSISDN"
COL_EMAIL = "Subscriber e-Mail"
COL_NAME = "Subscriber Name"
COL_ACCOUNT = "Subscriber Account ID"

#: `<li>` labels holding the subject's own phone, best first. `User Phone Numbers` is the
#: subscriber's declared number; `Recovery SMS` is the number Google texts to reach them.
#: Both are the account holder's. 2-Step Verification numbers are deliberately excluded —
#: they are often a second person's handset used as a trusted device.
_PHONE_LABELS = ("user phone numbers", "recovery sms")
_EMAIL_LABELS = ("e-mail", "contact e-mail")
_NAME_LABELS = ("name",)
_ACCOUNT_LABELS = ("google account id",)

#: "+917041141503 [IN]" -> "+917041141503"
_COUNTRY_SUFFIX = re.compile(r"\s*\[[A-Z]{2}\]\s*")


def _text_lines(doc) -> list[str]:
    """Headings and list items as `Key: Value` lines, for free-text identity extraction."""
    lines: list[str] = []
    for el in doc.iter("h1", "h2", "h3", "h4", "li", "p", "div"):
        if el.tag == "div" and el.getchildren():
            continue                      # container — its children are visited already
        text = re.sub(r"\s+", " ", (el.text_content() or "")).strip()
        if text:
            lines.append(text)
    return lines


def _grids(doc) -> list[list[list[str]]]:
    out = []
    for table in doc.iter("table"):
        grid = []
        for row in table.iter("tr"):
            cells = [re.sub(r"\s+", " ", (c.text_content() or "")).strip()
                     for c in row.iter("th", "td")]
            if cells:
                grid.append(cells)
        if len(grid) >= 2:                # a header with no data row is not a table
            out.append(grid)
    return out


def _labelled(lines: list[str], labels: tuple[str, ...]) -> str | None:
    """First non-empty `Label: value` match, trying labels in order of preference."""
    for label in labels:
        for line in lines:
            key, sep, value = line.partition(":")
            if not sep or key.strip().lower() != label:
                continue
            value = value.strip()
            if value:
                return value
    return None


def _first_phone(value: str | None) -> str | None:
    if not value:
        return None
    for part in value.split(","):
        cleaned = _COUNTRY_SUFFIX.sub("", part).strip()
        if sum(c.isdigit() for c in cleaned) >= 10:
            return cleaned
    return None


def subscriber_identity(text_lines: list[str]) -> dict[str, str]:
    """Subject identifiers asserted by a Google subscriber-information response."""
    out: dict[str, str] = {}
    phone = _first_phone(_labelled(text_lines, _PHONE_LABELS))
    if phone:
        out[COL_MSISDN] = phone
    for key, labels in ((COL_EMAIL, _EMAIL_LABELS), (COL_NAME, _NAME_LABELS),
                        (COL_ACCOUNT, _ACCOUNT_LABELS)):
        value = _labelled(text_lines, labels)
        if value:
            out[key] = value
    return out


def _denormalize(grid: list[list[str]], identity: dict[str, str]) -> list[list[str]]:
    """Append the subject's identifiers as extra columns on every data row."""
    if not grid or not identity:
        return grid
    extra_headers = list(identity)
    extra_values = [identity[h] for h in extra_headers]
    return [grid[0] + extra_headers] + [row + extra_values for row in grid[1:]]


def read(path: str) -> tuple[list[str], list[list]]:
    """Return (text_lines, best_grid) — same contract as `parsers.pdf.read`."""
    raw = Path(path).read_bytes()
    if not raw.strip():
        return [], []
    doc = lxml_html.fromstring(raw)
    lines = _text_lines(doc)
    grids = _grids(doc)
    grid = max(grids, key=len) if grids else []

    if any(_GOOGLE_MARKER in ln.upper() for ln in lines):
        grid = _denormalize(grid, subscriber_identity(lines))
    return lines, grid


def read_all_grids(path: str) -> list[tuple[str, list[list]]]:
    """Every table in the document, labelled — for multi-table HTML exports."""
    raw = Path(path).read_bytes()
    if not raw.strip():
        return []
    doc = lxml_html.fromstring(raw)
    lines = _text_lines(doc)
    identity = (subscriber_identity(lines)
                if any(_GOOGLE_MARKER in ln.upper() for ln in lines) else {})
    return [(f"table_{i + 1}", _denormalize(g, identity))
            for i, g in enumerate(_grids(doc))]
