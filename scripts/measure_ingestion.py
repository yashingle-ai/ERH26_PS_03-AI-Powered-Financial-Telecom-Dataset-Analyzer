"""CLI: ingestion + normalization metrics for a case folder, without the analysis stages.

Exists so the before/after figures quoted in `docs/PS_COMPLIANCE_AND_FIX_PLAN.md` are
reproducible from the repository by one command, rather than from a scratch script. The
window-dependent stages (correlation, detection, graph) are deliberately excluded — they do
not affect any ingestion figure and they dominate runtime, so excluding them makes an A/B
over parsing changes cheap enough to run per experiment.

Both recovery paths are switchable from the environment so the two arms of a measurement
run the SAME build, which is the only way a moved number is attributable to one change:

    ERAKSHAK_VALUE_TYPING=0|1        instance-level column typing
    ERAKSHAK_STRUCTURE_RECOVERY=0|1  broken-grid geometry recovery

Usage:
    python -m scripts.measure_ingestion --input "datasets/FIR 65-2024" --save out.json
    ERAKSHAK_STRUCTURE_RECOVERY=0 python -m scripts.measure_ingestion --input ... --label off
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.ingestion import service as ingestion  # noqa: E402
from backend.app.ingestion import structure, value_typer  # noqa: E402
from backend.app.normalization import service as normalization  # noqa: E402


def _rows(reject: dict) -> int:
    """Rows a reject entry accounts for. `rejected` when present, else `rows`."""
    return reject.get("rejected", reject.get("rows", 0))


def measure(input_dir: str, include_pdf: bool = True) -> dict:
    t0 = time.time()
    skipped: list[dict] = []
    parsed = ingestion.parse_directory(input_dir, include_pdf=include_pdf,
                                       skipped_out=skipped)
    parse_seconds = round(time.time() - t0, 1)

    t0 = time.time()
    events, norm_rejects = normalization.normalize_parsed_files(parsed)
    normalize_seconds = round(time.time() - t0, 1)

    # Same composition the pipeline uses, so the two agree by construction.
    parse_rejects = [r for pf in parsed for r in (pf.rejects or [])]
    rejects = parse_rejects + skipped + norm_rejects

    by_reason: Counter = Counter()
    for r in rejects:
        by_reason[r.get("reason", "?")] += _rows(r)

    return {
        "input": input_dir,
        "flags": {
            "value_typing": value_typer.enabled(),
            "structure_recovery": structure.enabled(),
        },
        "parsed_tables": len(parsed),
        "distinct_source_files": len({pf.path for pf in parsed}),
        "needs_manual_mapping": sum(1 for pf in parsed if pf.needs_manual_mapping),
        "tables_by_source": dict(
            Counter(pf.source_type or "UNRECOGNISED" for pf in parsed).most_common()),
        "tables_by_profile": dict(
            Counter(pf.profile_id or "none" for pf in parsed).most_common(15)),
        "records_parsed": sum(len(pf.records) for pf in parsed),
        "rows_in_unrecognised_tables": sum(
            len(pf.records) for pf in parsed if not pf.source_type),
        "value_inferred_tables": sum(1 for pf in parsed if pf.value_map),
        "events": len(events),
        "events_by_type": dict(Counter(e["event_type"] for e in events)),
        "rejected_rows": sum(_rows(r) for r in rejects),
        "reject_entries": len(rejects),
        "non_evidentiary_rows": sum(_rows(r) for r in rejects
                                    if r.get("evidentiary") is False),
        "unmapped_rows": sum(_rows(r) for r in rejects
                             if r.get("evidentiary") is not False),
        "files_never_opened": sum(1 for r in skipped if r.get("file_skipped")
                                  and not r.get("duplicate_of")),
        "duplicate_exhibits": sum(1 for r in skipped if r.get("duplicate_of")),
        "rejected_rows_by_reason": dict(by_reason.most_common()),
        "seconds": {"parse": parse_seconds, "normalize": normalize_seconds},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--no-pdf", action="store_true", help="skip PDFs entirely")
    ap.add_argument("--label", default=None, help="label recorded in the output")
    ap.add_argument("--save", default=None, help="write metrics JSON to this path")
    args = ap.parse_args()

    out = measure(args.input, include_pdf=not args.no_pdf)
    if args.label:
        out["label"] = args.label
    text = json.dumps(out, indent=2, default=str)
    print(text)
    if args.save:
        with open(args.save, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"\nwrote {args.save}", file=sys.stderr)


if __name__ == "__main__":
    main()
