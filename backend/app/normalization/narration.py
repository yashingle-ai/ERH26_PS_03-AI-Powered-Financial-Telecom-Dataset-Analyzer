"""Narration mining (Doc 06 §10) — extract identifiers embedded in bank free-text.

Bank narrations pack the mode, beneficiary/payer, UPI VPA, and UTR/RRN into one string
(e.g. "UPI/john@hdfc/John Doe/100000012345"). We pull these out using the regexes
declared per-profile so linkage (FR-10) can use them.
"""

from __future__ import annotations

import re


def mine(narration: str, profile: dict) -> dict:
    out: dict = {}
    if not narration:
        return out
    patterns = profile.get("narration_extract", {})
    for key, pat in patterns.items():
        m = re.search(pat, narration)
        if m:
            out[key] = m.group(1)

    # Beneficiary/counterparty name heuristic: the token between mode and ref in our
    # "<MODE>/<upi-or-name>/<name>/<ref>" convention.
    parts = [p for p in narration.split("/") if p]
    if len(parts) >= 3:
        out.setdefault("counterparty_name", parts[-2].strip())
    return out
