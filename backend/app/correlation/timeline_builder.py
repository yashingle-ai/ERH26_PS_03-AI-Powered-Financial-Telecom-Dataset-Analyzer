"""Unified per-entity timeline (FR-8). Groups normalized events by entity, sorted by time."""

from __future__ import annotations

from collections import defaultdict


def build(events: list[dict]) -> dict[str, list[dict]]:
    """entity_id -> chronological list of that entity's events (all three types)."""
    by_entity: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        eid = ev.get("entity_id")
        if eid:
            by_entity[eid].append(ev)
    for eid in by_entity:
        by_entity[eid].sort(key=lambda e: e["timestamp_start"])
    return by_entity
