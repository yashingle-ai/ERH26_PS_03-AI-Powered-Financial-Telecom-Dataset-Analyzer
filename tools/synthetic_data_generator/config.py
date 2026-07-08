"""Tier definitions for the synthetic dataset generator (research/12 §8.2)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tier:
    name: str
    n_persons: int
    days: int              # time span of activity
    calls_per_phone: int   # approx benign calls per phone over the span
    sessions_per_phone: int
    txns_per_account: int
    n_fraud_rings: int     # planted laundering rings (layering/circular/mule clusters)


TIERS: dict[str, Tier] = {
    # Small: unit tests + quick demo
    "smoke": Tier("smoke", n_persons=8, days=14, calls_per_phone=15,
                  sessions_per_phone=15, txns_per_account=25, n_fraud_rings=1),
    # Demo: fusion dashboard + worked example
    "demo": Tier("demo", n_persons=30, days=30, calls_per_phone=40,
                 sessions_per_phone=40, txns_per_account=60, n_fraud_rings=3),
    # Scale: performance/scalability testing (NFR-5)
    "scale": Tier("scale", n_persons=250, days=60, calls_per_phone=80,
                  sessions_per_phone=80, txns_per_account=120, n_fraud_rings=12),
}
