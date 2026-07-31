"""Gujarati bank-reply tables → LINK events (bank account ↔ registered mobile).

FR-9 needs one entity holding a transaction, a call and an IP session inside a window. Both real
cases hold hundreds of thousands of transactions and calls and STRONG is **0 at every window from
1 to 60 minutes**, because nothing ties an account to a handset: `account+phone` is 3.

The bridge is in the evidence. Banks answering a legal-process request tabulate the account beside
the mobile registered against it, and the police paperwork carries those replies as Word tables
with a stable five-column Gujarati header:

    અ.નં. | બેંક એકાઉન્ટ નંબર | એકાઉન્ટ ધારકનું નામ સરનામુ | રજીસ્ટર મોબાઇલ નંબર | રજીસ્ટર ઇ-મેઇલ આઇડી
    s.no  | bank account no    | account holder name+address | registered mobile no  | registered e-mail

`field_mapper` matches English aliases, so those tables score zero against every profile and land
in the unrecognised pile. The values themselves are ASCII — 47 distinct accounts and 56 distinct
mobiles across both cases, in 61 pairs, none written in Gujarati numerals — so the only blocker is
the header language.

**Why this source and not the affidavits.** These are the bank's own KYC record. The narrative
affidavits in the same folders assert far more — accused ↔ account ↔ IMEI ↔ handset, with the
officer's own layering determination — but an assertion in a legal filing is not a bank record, and
letting one become a merge is what rule 3 forbids. Provenance decides what may create an identity;
see `docs/COMPONENT_STATUS.md` §4.2.

**Three safety checks, all measured before this existed** (§4.1):

  1. Officer contamination. The `has_admin_role_columns` guard finds 299 officer/handler tables
     across both cases holding 1,449 distinct officer mobiles. **0** of the 56 bridge mobiles appear
     among them. This is the check that disqualified `master - Copy.xlsx`, where linking would have
     merged 32 mule accounts into ~98 police entities.
  2. Cardinality. 36 of 61 pairs are strictly one-to-one and the worst fan-out is 3 — the holder
     signature. The rejected officer table had the inverse: 94 of 98 officers with exactly one
     mobile but only 10 of 32 accounts, which is a shared contact column.
  3. Effect. Merging yields TRANSACTION+CALL on 7 pairs per case and TRANSACTION+CALL+IP on 4 pairs
     of `fir-65-2024`. Necessary but not sufficient — the events must also fall inside the window —
     so 4 is an upper bound on new STRONG candidates, never a prediction.

`_MAX_FANOUT` is enforced here rather than trusted from that measurement, because the guard has to
hold for the next case folder too.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path

from ..core.logging_config import get_logger
from ..core.text import ascii_digits
from ..ingestion import value_typer as vt
from ..normalization import normalizers as nz

log = get_logger(__name__)

#: Off by default. This creates identity merges, so it must be switchable from the environment:
#: both arms of the FR-9 window sweep then run the same build and any moved STRONG count is
#: attributable to the links and nothing else. Attributing a change by run timestamp is a trap
#: this project has already paid for once.
_FLAG = "ERAKSHAK_BANK_REPLY_LINKS"


def enabled() -> bool:
    return os.getenv(_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}

#: Header vocabulary. Transliterations are in the comments so a reviewer who does not read
#: Gujarati can audit the match, which matters for a module that creates identities.
_ACCOUNT_HDR = re.compile("|".join([
    "એકાઉન્ટ નંબર",      # account number
    "બેંક એકાઉન્ટ",       # bank account
    "ખાતા નં",           # khaataa no. (account no.)
]))
_PHONE_HDR = re.compile("|".join([
    "રજીસ્ટર મોબાઇલ",    # registered mobile
    "મોબાઇલ નંબર",       # mobile number
    "મોબાઈલ નંબર",       # mobile number, alternate spelling
]))
#: A holder column must be present. Its absence is what distinguishes a bank KYC reply from a
#: seized-property schedule that happens to list an account and a handset side by side.
_HOLDER_HDR = re.compile("|".join([
    "એકાઉન્ટ ધારક",      # account holder
    "ધારકનું નામ",        # holder's name
    "ધારકનુ નામ",         # holder's name, alternate spelling
]))

_MSISDN = re.compile(r"(?<!\d)[6-9]\d{9}(?!\d)")
_ACCT = re.compile(r"(?<!\d)\d{9,18}(?!\d)")

#: Above this, a column is a shared contact rather than a holder's own line, and the batch is
#: refused wholesale rather than filtered — a mixed table means the wrong column was read.
_MAX_FANOUT = 4


def _cell_ids(text: str, pattern: re.Pattern) -> list[str]:
    return pattern.findall(ascii_digits(text))


def _link(account: str, phone: str, source_file: str) -> dict:
    return {
        "event_type": "LINK", "timestamp_start": None, "timestamp_end": None,
        "amount": None, "direction": None,
        "primary": ("ACCOUNT_NO", account), "counterparty": None,
        "own_identifiers": [("ACCOUNT_NO", account), ("PHONE", phone)],
        "attributes": {"source": "bank_reply_gujarati"},
        "provenance": {"source_file": source_file},
    }


def _pairs_from_table(head: list[str], rows: list[list[str]]) -> list[tuple[str, str]]:
    """Account/mobile pairs from one table, or [] if it is not a bank KYC reply."""
    joined = " | ".join(head)
    if not (_ACCOUNT_HDR.search(joined) and _PHONE_HDR.search(joined)
            and _HOLDER_HDR.search(joined)):
        return []
    # An officer/handler column anywhere means the phone column is an administrative contact.
    # Refusing is the safe direction: a missed link costs a lead, an invented one puts an
    # innocent person inside a correlation hit.
    if vt.has_admin_role_columns(head):
        return []
    acc_i = next((i for i, h in enumerate(head) if _ACCOUNT_HDR.search(h)), None)
    ph_i = next((i for i, h in enumerate(head) if _PHONE_HDR.search(h)), None)
    if acc_i is None or ph_i is None:
        return []

    pairs: list[tuple[str, str]] = []
    for row in rows:
        if max(acc_i, ph_i) >= len(row):
            continue
        accounts = _cell_ids(row[acc_i], _ACCT)
        phones = _cell_ids(row[ph_i], _MSISDN)
        # One row is one subject. Several values in a cell is a multi-account holder, which is
        # real; the cross product is what the bank is asserting about that subject.
        for a in accounts:
            acct = nz.account_no(a)
            for p in phones:
                ph = nz.phone(p)
                if acct and ph:
                    pairs.append((acct, ph))
    return pairs


def _docx_tables(path: Path):
    from docx import Document
    for table in Document(str(path)).tables:
        if len(table.rows) < 2:
            continue
        yield ([c.text.strip() for c in table.rows[0].cells],
               [[c.text.strip() for c in r.cells] for r in table.rows[1:]])


def load_bank_reply_links(input_dir: str) -> list[dict]:
    """Walk the case tree for Gujarati bank KYC replies and emit account↔phone LINK events."""
    root = Path(input_dir)
    if not root.exists():
        return []

    found: list[tuple[str, str, str]] = []          # (account, phone, source_file)
    for path in root.rglob("*.docx"):
        if not path.is_file() or path.name.startswith("~$"):
            continue
        try:
            tables = list(_docx_tables(path))
        except Exception as e:
            log.warning("bank reply unreadable %s: %s", path.name, e)
            continue
        for head, rows in tables:
            for acct, ph in _pairs_from_table(head, rows):
                found.append((acct, ph, path.name))

    if not found:
        return []

    # Fan-out is checked over the WHOLE case, not per table: the same shared contact number
    # spread thinly across six copies of one reply would pass every table individually.
    by_acct: dict[str, set] = defaultdict(set)
    by_phone: dict[str, set] = defaultdict(set)
    for acct, ph, _ in found:
        by_acct[acct].add(ph)
        by_phone[ph].add(acct)

    worst_phone = max((len(v) for v in by_phone.values()), default=0)
    worst_acct = max((len(v) for v in by_acct.values()), default=0)
    if worst_phone > _MAX_FANOUT or worst_acct > _MAX_FANOUT:
        # Refuse the batch, loudly. A mixed table means the wrong column was read, and
        # filtering the outliers would keep whatever else that mistake produced.
        log.warning(
            "bank reply links REFUSED for %s: fan-out %d accounts/phone and %d phones/account "
            "exceeds %d — reads as a shared contact column, not a holder column",
            root.name, worst_phone, worst_acct, _MAX_FANOUT)
        return []

    links, seen = [], set()
    for acct, ph, src in found:
        key = (acct, ph)
        if key in seen:
            continue
        seen.add(key)
        links.append(_link(acct, ph, src))

    log.info("loaded %d bank-reply account<->phone links from %s "
             "(%d accounts, %d phones, max fan-out %d/%d)",
             len(links), root.name, len(by_acct), len(by_phone), worst_phone, worst_acct)
    return links
