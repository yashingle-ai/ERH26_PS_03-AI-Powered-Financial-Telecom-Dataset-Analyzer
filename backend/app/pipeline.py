"""End-to-end investigation pipeline (orchestrator).

Runs the full fusion flow on a directory of Bank/CDR/IPDR files and returns one
Investigation object the dashboard and reporting consume:

  ingest -> normalize -> resolve entities -> timeline -> correlate -> money-flow
         -> detect + risk score -> build graph

Store-in / store-out per stage (research/05 §8) keeps each phase independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .core.logging_config import get_logger
from .correlation import timeline_builder, window_correlator
from .detection import service as detection
from .entity_resolution import service as er
from .graph import money_flow
from .graph import service as graph_service
from .ingestion import service as ingestion
from .normalization import service as normalization

log = get_logger(__name__)


@dataclass
class Investigation:
    input_dir: str
    parsed_files: list = field(default_factory=list)
    events: list = field(default_factory=list)
    rejects: list = field(default_factory=list)
    entities: dict = field(default_factory=dict)
    node_to_entity: dict = field(default_factory=dict)
    timeline: dict = field(default_factory=dict)
    correlation_hits: list = field(default_factory=list)
    transfers: list = field(default_factory=list)
    risk: dict = field(default_factory=dict)
    graph: dict = field(default_factory=dict)

    def summary(self) -> dict:
        from collections import Counter
        ev_types = Counter(e["event_type"] for e in self.events)
        core = {k: v for k, v in self.entities.items() if not v.get("external")}
        high = [r for r in self.risk.values() if r["band"] == "high"]
        return {
            "files": len(self.parsed_files),
            "events": len(self.events),
            "transactions": ev_types.get("TRANSACTION", 0),
            "calls": ev_types.get("CALL", 0),
            "ip_sessions": ev_types.get("IP_SESSION", 0),
            "rejects": len(self.rejects),
            "entities": len(core),
            "correlation_hits": len(self.correlation_hits),
            "transfers": len(self.transfers),
            "high_risk_entities": len(high),
        }


def run(input_dir: str, window_minutes: int | None = None,
        persist: bool = False) -> Investigation:
    log.info("pipeline start: %s (window=%s)", input_dir, window_minutes)
    inv = Investigation(input_dir=input_dir)

    inv.parsed_files = ingestion.parse_directory(input_dir)
    inv.events, inv.rejects = normalization.normalize_parsed_files(inv.parsed_files)
    log.info("ingested %d files -> %d events (%d rejects)",
             len(inv.parsed_files), len(inv.events), len(inv.rejects))

    inv.entities, inv.node_to_entity = er.resolve(inv.events)
    er.assign_entities(inv.events, inv.node_to_entity, inv.entities)

    inv.timeline = timeline_builder.build(inv.events)
    inv.correlation_hits = window_correlator.correlate(
        inv.timeline, inv.entities, inv.events, window_minutes)

    inv.transfers = money_flow.build_transfers(inv.events)
    inv.risk = detection.detect(inv.events, inv.transfers, inv.correlation_hits, inv.entities)
    inv.graph = graph_service.build(inv.events, inv.entities, inv.risk)
    log.info("pipeline done: %s", inv.summary())

    if persist:
        from .persistence import store
        store.persist_investigation(inv)
    return inv
