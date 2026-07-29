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
from .entity_resolution import common_imei as er_common_imei
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
    correlation_hits: list = field(default_factory=list)          # STRONG only (FR-9)
    correlation_hits_medium: list = field(default_factory=list)   # MEDIUM (call+txn, no IP)
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
            # `rejected_rows` keeps its original meaning — every dropped row — so any
            # figure previously quoted still compares. The split below is what an analyst
            # actually needs, because the total mixes two very different things.
            "rejected_rows": sum(r.get("rejected", r.get("rows", 0)) for r in self.rejects),
            "reject_entries": len(self.rejects),
            # Non-evidentiary drops: blank layout rows, and events de-duplicated after a
            # successful parse. Neither is a row we failed to read, and on the real case
            # they were roughly a third of the total — reporting them together made the
            # headline look like a far larger evidence gap than it is.
            "non_evidentiary_rows": sum(r.get("rejected", r.get("rows", 0))
                                        for r in self.rejects
                                        if r.get("evidentiary") is False),
            "unmapped_rows": sum(r.get("rejected", r.get("rows", 0)) for r in self.rejects
                                 if r.get("evidentiary") is not False),
            "entities": len(core),
            # Headline FR-9 count — STRONG only. Do not inflate with MEDIUM.
            "correlation_hits": len(self.correlation_hits),
            "correlation_hits_medium": len(self.correlation_hits_medium),
            "transfers": len(self.transfers),
            "high_risk_entities": len(high),
            # "0 high-risk entities" reads as "nothing to look at here". On the real case
            # it meant something narrower: no entity exhibits enough distinct typologies
            # to clear the band, while 25 sat at medium and were worth an analyst's time.
            # The band is deliberately hard to reach — score = 0.7*Σweights + 0.3*ml, so
            # high needs nearly every typology at once — and rescaling it per case would
            # manufacture high-risk labels rather than find them. Reporting the
            # distribution and the top score instead lets the headline explain itself.
            "risk_bands": {b: sum(1 for r in self.risk.values() if r["band"] == b)
                           for b in ("high", "medium", "low")},
            "top_risk_score": max((r["risk_score"] for r in self.risk.values()),
                                  default=0.0),
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
    # LEA Common-IMEI reports in the case folder are the same kind of bridge, auto-discovered.
    link_events += er_common_imei.load_common_imei_links(input_dir, inv.events)
    inv.entities, inv.node_to_entity = er.resolve(inv.events + link_events)
    er.assign_entities(inv.events, inv.node_to_entity, inv.entities)

    inv.timeline = timeline_builder.build(inv.events)
    inv.transfers = money_flow.build_transfers(inv.events)
    inv.data_quality = validation.check_balances(inv.events)   # A5
    return inv


def apply_analysis(inv: Investigation, window_minutes: int | None = None) -> Investigation:
    """Window-DEPENDENT stages: correlation, detection/risk, graph."""
    all_hits = window_correlator.correlate(
        inv.timeline, inv.entities, inv.events, window_minutes)
    inv.correlation_hits, inv.correlation_hits_medium = window_correlator.split_by_tier(all_hits)
    # Risk coincidence_count uses STRONG only — MEDIUM must not inflate the score.
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
