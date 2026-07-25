"""Narration mining (Doc 06 §10) — extract identifiers embedded in bank free-text.

Bank narrations pack the mode, beneficiary/payer, UPI VPA, and UTR/RRN into one string
(e.g. "UPI/john@hdfc/John Doe/100000012345"). We pull these out using the regexes
declared per-profile so linkage (FR-10) can use them.
"""

from __future__ import annotations

import re

# A UPI VPA whose handle is a 10-digit Indian mobile (6-9 start), e.g. 9876543210@ybl.
# This is the finance<->telecom bridge: the counterparty's phone in the payment rail.
_VPA_PHONE = re.compile(r'(?<!\d)([6-9]\d{9})@[a-zA-Z]{2,}')
# A UPI VPA whose handle is an account-like number (>=9 digits), e.g. 11161241340@sbi (C4).
_VPA_ACCOUNT = re.compile(r'(?<!\d)(\d{9,18})@[a-zA-Z]{2,}')
# A plausible payee name token: >=4 letters, allows spaces/dots (C5).
_NAME = re.compile(r'\b([A-Za-z][A-Za-z .]{3,40}[A-Za-z])\b')
_STOPWORDS = {"upi", "neft", "imps", "rtgs", "atm", "pos", "cash", "ref", "the", "and"}


def mine(narration: str, profile: dict) -> dict:
    out: dict = {}
    if not narration:
        return out
    patterns = profile.get("narration_extract", {})
    for key, pat in patterns.items():
        m = re.search(pat, narration)
        if m:
            out[key] = m.group(1)

    # Bridge: extract a counterparty phone from a phone-based UPI VPA (real bank data).
    m = _VPA_PHONE.search(narration)
    if m:
        out["counterparty_phone"] = m.group(1)
    else:
        # C4: an account-number VPA handle -> link to the payee's account entity.
        ma = _VPA_ACCOUNT.search(narration)
        if ma:
            out["counterparty_account"] = ma.group(1)

    # C5: structured payee name — longest alphabetic token that isn't a mode keyword.
    candidates = [c.strip() for c in _NAME.findall(narration)
                  if c.strip().lower() not in _STOPWORDS and len(c.strip()) >= 4]
    if candidates:
        out["counterparty_name"] = max(candidates, key=len).strip()
    else:
        parts = [p for p in narration.split("/") if p]
        if len(parts) >= 3:
            out["counterparty_name"] = parts[-2].strip()
    return out
