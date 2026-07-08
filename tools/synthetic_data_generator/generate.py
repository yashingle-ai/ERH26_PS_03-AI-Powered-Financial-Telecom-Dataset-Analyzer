"""CLI: generate a synthetic, fused, labeled ERakshak dataset.

Usage:
    python -m tools.synthetic_data_generator.generate --tier smoke --out datasets/raw/smoke

Produces (research/12 §8):
    <out>/bank/*.{xlsx,csv,pdf}   bank statements across formats
    <out>/cdr/cdr_<operator>.csv  call detail records per operator
    <out>/ipdr/ipdr_<operator>.csv internet protocol detail records per operator
    <out>/ground_truth.json       planted suspicious scenarios (free labels, NFR-3)
    datasets/metadata/<tier>_metadata.json  provenance + limitations
"""

from __future__ import annotations

import argparse
import os
import random

from .activity import ActivityGenerator
from .config import TIERS
from .emitters import (
    emit_bank,
    emit_cdr,
    emit_ground_truth,
    emit_ipdr,
    emit_metadata,
)
from .population import build_population


def main():
    ap = argparse.ArgumentParser(description="Generate synthetic Bank/CDR/IPDR datasets.")
    ap.add_argument("--tier", choices=list(TIERS), default="smoke")
    ap.add_argument("--out", default=None, help="Output dir (default datasets/raw/<tier>)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--metadata-dir", default="datasets/metadata")
    args = ap.parse_args()

    tier = TIERS[args.tier]
    out_dir = args.out or os.path.join("datasets", "raw", tier.name)
    os.makedirs(out_dir, exist_ok=True)

    print(f"[generate] tier={tier.name} persons={tier.n_persons} "
          f"days={tier.days} fraud_rings={tier.n_fraud_rings} seed={args.seed}")

    people = build_population(tier.n_persons, seed=args.seed)
    gen = ActivityGenerator(people, tier, seed=args.seed).run()

    rng = random.Random(args.seed + 99)
    acct_mobile = {acc.account_no: p.phones[0] for p in people for acc in p.accounts}
    manifest = {
        "bank": emit_bank(gen.bank_txns, out_dir, rng, acct_mobile),
        "cdr": emit_cdr(gen.cdr_rows, out_dir, rng),
        "ipdr": emit_ipdr(gen.ipdr_rows, out_dir, rng),
    }
    gt_path = emit_ground_truth(gen.ground_truth, out_dir)
    meta_path = emit_metadata(tier, args.seed, manifest, gen.ground_truth, out_dir, args.metadata_dir)

    print(f"[generate] bank_txns={len(gen.bank_txns)} cdr_rows={len(gen.cdr_rows)} "
          f"ipdr_rows={len(gen.ipdr_rows)} scenarios={len(gen.ground_truth)}")
    print(f"[generate] bank files={len(manifest['bank'])} "
          f"cdr files={len(manifest['cdr'])} ipdr files={len(manifest['ipdr'])}")
    print(f"[generate] wrote {out_dir}/ (+ {gt_path}) and metadata {meta_path}")


if __name__ == "__main__":
    main()
