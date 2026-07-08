"""CLI: run the full investigation pipeline on a dataset and print/save results.

Usage:
    ./.venv/bin/python -m scripts.run_pipeline --input datasets/raw/demo --window 10 [--eval]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import pipeline  # noqa: E402
from backend.app.detection import evaluate as ev  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--window", type=int, default=10)
    ap.add_argument("--eval", action="store_true", help="evaluate vs ground_truth.json")
    ap.add_argument("--persist", action="store_true", help="write results to the database")
    ap.add_argument("--save", default=None, help="write summary JSON to this path")
    args = ap.parse_args()

    inv = pipeline.run(args.input, window_minutes=args.window, persist=args.persist)
    summary = inv.summary()
    print(json.dumps(summary, indent=2))

    if args.persist:
        import os

        from backend.app.persistence import store
        ds = os.path.basename(args.input.rstrip("/"))
        print("PERSISTED (read-back):", json.dumps(store.load_summary(ds), indent=2))

    if args.eval:
        gt_path = os.path.join(args.input, "ground_truth.json")
        if os.path.exists(gt_path):
            gt = json.load(open(gt_path))
            report = ev.evaluate(gt, inv.risk, inv.node_to_entity)
            print("EVALUATION:", json.dumps(report, indent=2))
        else:
            print("(no ground_truth.json to evaluate)")

    if args.save:
        os.makedirs(os.path.dirname(args.save) or ".", exist_ok=True)
        json.dump(summary, open(args.save, "w"), indent=2)
        print("saved:", args.save)


if __name__ == "__main__":
    main()
