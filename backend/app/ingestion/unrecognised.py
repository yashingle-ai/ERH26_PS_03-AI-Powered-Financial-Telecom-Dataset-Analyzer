"""Why a table went unclaimed — because "671 unrecognised" is a headcount, not a diagnosis.

FR-4 has read "658 of 951 unrecognised" for weeks. Measured by rows on `fir-65-2024` the same
build claims **348,567 of 364,747 — 95.6%** — because the unclaimed tables average 24 rows while
the claimed ones hold thousands. The headline counts tables and so overstates the gap by roughly
twenty times.

Worse, it mixes outcomes that call for opposite responses:

  * A **CCTV log** — one table, 11,275 rows, 70% of everything unclaimed on that case — is not
    Bank, CDR or IPDR. No profile should ever claim it.
  * An **NCRP complaint register** carrying `Name of Complain reported officer, Designation,
    Mobile Number` is refused *on purpose*: this is the `master - Copy.xlsx` shape, where linking
    would have merged 32 mule accounts into ~98 police entities.
  * A **hold-amount or nominee table** is real bank data with no timestamp, so it cannot become
    events however well it is mapped.
  * Only what is left is a parser gap worth working on.

Reporting those four as one number invites building profiles for data that must not be claimed.
This adds the breakdown; `tables_by_source` and `rows_in_unrecognised_tables` keep their exact
meaning so every figure previously quoted still compares — a headline metric gets a companion,
not a redefinition.

Classification is **value-based**, not filename-based. "Out of scope" means no column in the table
types as any canonical field — not that the name contains `cctv`. A filename keyword would have
made this a lookup table of the two cases we happen to hold.
"""

from __future__ import annotations

from . import value_typer as vt

#: Reasons, in the order they are tested. First match wins, and the order matters: an officer
#: column disqualifies a table whatever else it contains.
REFUSED_OFFICER = "refused_officer_bearing"
OUT_OF_SCOPE = "out_of_scope_no_canonical_field"
NO_TIME_ANCHOR = "reference_no_time_anchor"
UNREAD = "unread_parser_gap"

#: The value shapes `value_typer` can actually recognise. Only these — a predicate this module
#: invents would be a second opinion on what an account looks like, and the whole point is to use
#: the same judgement the typer uses.
_PREDICATES = ("phone", "account", "amount", "imei", "imsi", "temporal", "cell_id")


def _column_signals(headers: list[str], records: list[dict]) -> set[str]:
    """Which canonical value shapes appear in this table's columns, judged from the values."""
    if not records:
        return set()
    sample = records[: min(len(records), 60)]
    found: set[str] = set()
    for header in headers or []:
        values = [str(r.get(header) or "").strip() for r in sample]
        values = [v for v in values if v]
        if len(values) < 3:
            continue
        hits = {
            "phone": vt._is_phone, "account": vt._is_acct_like, "amount": vt._is_amount,
            "imei": vt._is_imei, "imsi": vt._is_imsi,
            "temporal": vt._is_temporal, "cell_id": vt._is_cell_id,
        }
        for name, fn in hits.items():
            try:
                if sum(1 for v in values if fn(v)) >= max(3, int(len(values) * 0.6)):
                    found.add(name)
            except Exception:
                continue
    return found


def classify(parsed_file) -> str:
    """Why this table was not claimed by a profile. Call only for `source_type is None`."""
    headers = [str(h) for h in (parsed_file.headers or [])]
    records = parsed_file.records or []

    # An officer/handler column is disqualifying regardless of what else is present. Tested first
    # so a complaint register full of account numbers cannot be classified as a parser gap and
    # then "fixed" by someone adding a profile for it.
    if vt.has_admin_role_columns(headers):
        return REFUSED_OFFICER

    signals = _column_signals(headers, records)
    if not signals:
        return OUT_OF_SCOPE
    if "temporal" not in signals:
        # Real Bank/CDR/IPDR values but nothing to place them on the timeline. Mapping it better
        # will not produce a single event.
        return NO_TIME_ANCHOR
    return UNREAD


def summarise(parsed_files) -> dict:
    """`{reason: {"tables": n, "rows": n}}` over every table no profile claimed."""
    out: dict[str, dict[str, int]] = {}
    for pf in parsed_files:
        if pf.source_type:
            continue
        reason = classify(pf)
        row = out.setdefault(reason, {"tables": 0, "rows": 0})
        row["tables"] += 1
        row["rows"] += len(pf.records or [])
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["rows"]))
