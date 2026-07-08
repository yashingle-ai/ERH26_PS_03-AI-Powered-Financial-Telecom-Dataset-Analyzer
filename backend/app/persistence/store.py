"""Persistence layer (review fix C1) — durable canonical store + results.

The pipeline is in-memory for speed; this module writes an Investigation to a relational
store (SQLite by default, PostgreSQL via DATABASE_URL) so events, entities, provenance,
correlation hits, and risk assessments survive a restart — required for a forensic tool's
chain-of-custody. Rows are scoped by `dataset`; persisting a dataset replaces its prior rows.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

from ..core import config
from ..core.logging_config import get_logger
from ..models.canonical import (
    Base,
    CorrelationHitRow,
    Entity,
    EntityIdentifier,
    EntityLink,
    Event,
    RiskAssessment,
)

log = get_logger(__name__)


@lru_cache(maxsize=4)
def _engine(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    eng = create_engine(url, connect_args=connect_args, future=True)
    Base.metadata.create_all(eng)
    return eng


def get_session(url: str | None = None) -> Session:
    url = url or config.database_url()
    return sessionmaker(bind=_engine(url), future=True)()


def init_db(url: str | None = None) -> None:
    _engine(url or config.database_url())


def persist_investigation(inv, dataset: str | None = None, url: str | None = None) -> dict:
    """Write an Investigation to the store; returns row counts. Idempotent per dataset."""
    import os
    dataset = dataset or os.path.basename(inv.input_dir.rstrip("/"))
    url = url or config.database_url()
    counts = {"entities": 0, "identifiers": 0, "events": 0, "links": 0,
              "risk": 0, "correlation_hits": 0}

    with get_session(url) as s:
        # replace prior rows for this dataset (idempotent re-runs)
        for model in (Entity, EntityIdentifier, Event, EntityLink, RiskAssessment,
                      CorrelationHitRow):
            s.execute(delete(model).where(model.dataset == dataset))

        for eid, ent in inv.entities.items():
            if ent.get("external"):
                continue
            s.add(Entity(dataset=dataset, entity_id=eid,
                         display_label=ent.get("label"),
                         risk_score=(inv.risk.get(eid, {}) or {}).get("risk_score"),
                         oversized=str(ent.get("oversized", False))))
            counts["entities"] += 1
            for (id_type, id_value) in ent.get("identifiers", []):
                s.add(EntityIdentifier(dataset=dataset, entity_id=eid,
                                       id_type=id_type, id_value=str(id_value)))
                counts["identifiers"] += 1

        for ev in inv.events:
            s.add(Event(
                dataset=dataset, event_type=ev["event_type"],
                entity_id=ev.get("entity_id"),
                counterparty_entity_id=ev.get("counterparty_entity_id"),
                timestamp_start=ev["timestamp_start"], timestamp_end=ev.get("timestamp_end"),
                amount=ev.get("amount"), direction=ev.get("direction"),
                attributes=_jsonable(ev.get("attributes")), provenance=ev.get("provenance") or {},
            ))
            counts["events"] += 1

        for e in inv.graph.get("payload", {}).get("edges", []):
            s.add(EntityLink(dataset=dataset, from_entity_id=e["source"],
                             to_entity_id=e["target"], link_type=e.get("kind"),
                             amount=e.get("amount"), weight=float(e.get("count") or 1)))
            counts["links"] += 1

        for r in inv.risk.values():
            s.add(RiskAssessment(dataset=dataset, entity_id=r["entity_id"], label=r.get("label"),
                                 risk_score=r["risk_score"], band=r["band"],
                                 ml_score=r.get("ml_score"), rule_flags=r.get("rule_flags") or []))
            counts["risk"] += 1

        for h in inv.correlation_hits:
            s.add(CorrelationHitRow(dataset=dataset, entity_id=h.get("entity_id"),
                                    entity_label=h.get("entity_label"),
                                    window_minutes=h.get("window_minutes", 0),
                                    explanation=h.get("explanation"),
                                    evidence=_jsonable({"transaction": h.get("transaction"),
                                                        "call": h.get("call"),
                                                        "ip_session": h.get("ip_session")})))
            counts["correlation_hits"] += 1

        s.commit()
    log.info("persisted dataset=%s counts=%s url=%s", dataset, counts, url)
    return counts


def load_summary(dataset: str, url: str | None = None) -> dict:
    """Read back persisted counts for a dataset (proves durability)."""
    from sqlalchemy import func, select
    url = url or config.database_url()
    out = {}
    with get_session(url) as s:
        for name, model in (("entities", Entity), ("events", Event),
                            ("risk", RiskAssessment), ("correlation_hits", CorrelationHitRow)):
            out[name] = s.execute(
                select(func.count()).select_from(model).where(model.dataset == dataset)
            ).scalar_one()
    return out


def _jsonable(obj):
    """Convert datetimes inside attributes/evidence to ISO strings for JSON columns."""
    import datetime as _dt
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, _dt.datetime):
        return obj.isoformat()
    return obj
