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
from .entity_resolution import mapping as er_mapping
from .entity_resolution import service as er
from .graph import money_flow
from .graph import service as graph_service
from .ingestion import service as ingestion
from .normalization import service as normalization
from .normalization import validation

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
    data_quality: list = field(default_factory=list)

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
            "rejected_rows": sum(r.get("rejected", r.get("rows", 0)) for r in self.rejects),
            "reject_entries": len(self.rejects),
            "entities": len(core),
            "correlation_hits": len(self.correlation_hits),
            "transfers": len(self.transfers),
            "high_risk_entities": len(high),
        }

    def reject_report(self) -> list[dict]:
        """B3: per-file / per-reason breakdown of what was dropped and why."""
        return sorted(self.rejects, key=lambda r: -r.get("rejected", r.get("rows", 0)))


def run_base(input_dir: str, include_pdf: bool = True) -> Investigation:
    """G2: window-INDEPENDENT prefix (the expensive part) — parse, normalize, resolve
    entities, build timeline & money-flow, validate. Cache this; only `apply_analysis`
    re-runs when the correlation window changes."""
    log.info("pipeline base: %s (pdf=%s)", input_dir, include_pdf)
    inv = Investigation(input_dir=input_dir)

    inv.parsed_files = ingestion.parse_directory(input_dir, include_pdf=include_pdf)
    inv.events, inv.rejects = normalization.normalize_parsed_files(inv.parsed_files)
    log.info("ingested %d files -> %d events (%d reject entries)",
             len(inv.parsed_files), len(inv.events), len(inv.rejects))

    # Merge analyst-supplied KYC/entity-map links (account<->phone/wallet) so cross-domain
    # correlation can fire. LINK events only contribute merge edges — not timeline/detection.
    link_events = er_mapping.load_link_events(input_dir)
    inv.entities, inv.node_to_entity = er.resolve(inv.events + link_events)
    er.assign_entities(inv.events, inv.node_to_entity, inv.entities)

    inv.timeline = timeline_builder.build(inv.events)
    inv.transfers = money_flow.build_transfers(inv.events)
    inv.data_quality = validation.check_balances(inv.events)   # A5
    return inv


def apply_analysis(inv: Investigation, window_minutes: int | None = None) -> Investigation:
    """Window-DEPENDENT stages: correlation, detection/risk, graph."""
    inv.correlation_hits = window_correlator.correlate(
        inv.timeline, inv.entities, inv.events, window_minutes)
    inv.risk = detection.detect(inv.events, inv.transfers, inv.correlation_hits, inv.entities)
    inv.graph = graph_service.build(inv.events, inv.entities, inv.risk)
    return inv


def run(input_dir: str, window_minutes: int | None = None,
        persist: bool = False, include_pdf: bool = True) -> Investigation:
    inv = run_base(input_dir, include_pdf=include_pdf)
    apply_analysis(inv, window_minutes)
    log.info("pipeline done: %s", inv.summary())
    if persist:
        from .persistence import store
        store.persist_investigation(inv)
    return inv
