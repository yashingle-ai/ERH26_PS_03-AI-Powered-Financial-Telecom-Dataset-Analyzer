"""Persistence layer (review fix C1) — durable canonical store + results.

The pipeline is in-memory for speed; this module writes an Investigation to a relational
store (SQLite by default, PostgreSQL via DATABASE_URL) so events, entities, provenance,
correlation hits, and risk assessments survive a restart — required for a forensic tool's
chain-of-custody. Rows are scoped by `dataset`; persisting a dataset replaces its prior rows.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, delete, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from ..core import config
from ..core.logging_config import get_logger
from ..models.canonical import (
    AnalysisSnapshot,
    Base,
    CorrelationHitRow,
    Entity,
    EntityIdentifier,
    EntityLink,
    Event,
    RiskAssessment,
)

log = get_logger(__name__)


#: Columns added after the first release, as {table: {column: DDL type}}. `create_all` creates
#: missing TABLES and silently leaves an existing table's shape alone, so a column added to a
#: model never reaches a database that already exists — the next insert fails with "no such
#: column" on the one machine that has been running longest. There is no Alembic here, and
#: introducing it for a single nullable column is not proportionate, so this closes the gap
#: explicitly rather than leaving it to be discovered in the field.
_ADDED_COLUMNS = {"risk_assessment": {"ml_scored": "BOOLEAN"}}


def _add_missing_columns(eng) -> None:
    """Add post-release nullable columns to tables that predate them. Idempotent, additive.

    Deliberately narrow: nullable adds only, never a drop, a rename or a type change, because
    those need a real migration and a backup. Anything it cannot do is left for one.
    """
    insp = inspect(eng)
    for table, columns in _ADDED_COLUMNS.items():
        if not insp.has_table(table):
            continue                                    # create_all will build it in full
        have = {c["name"] for c in insp.get_columns(table)}
        for name, ddl_type in columns.items():
            if name in have:
                continue
            with eng.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))
            log.info("added missing column %s.%s (%s)", table, name, ddl_type)


@lru_cache(maxsize=4)
def _engine(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    eng = create_engine(url, connect_args=connect_args, future=True)
    Base.metadata.create_all(eng)
    _add_missing_columns(eng)
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
                                 ml_score=r.get("ml_score"), ml_scored=r.get("ml_scored"),
                                 rule_flags=r.get("rule_flags") or []))
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


# ---- durable Investigation snapshots (survive API restart) --------------------
#
# Relational `persist_investigation` stores a forensic subset (events/entities/risk)
# but cannot rebuild the live Investigation the API serves (transfers, graph payload,
# medium hits, rejects, parsed_files, …). Snapshots pickle the full object to disk and
# keep a DB index row so `/v1/datasets` can show READY without re-running the pipeline.


def _cache_dir() -> Path:
    raw = os.getenv("ERAKSHAK_ANALYSIS_CACHE")
    if raw:
        d = Path(raw)
    else:
        # Prefer beside the SQLite file when using the default URL; else repo data/.
        d = config.ROOT / "data" / "analysis_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _blob_name(dataset: str, window_minutes: int) -> str:
    # Dataset names are already constrained by the API to a safe charset.
    return f"{dataset}__w{int(window_minutes)}.pkl"


def has_analysis_snapshot(dataset: str, window_minutes: int, url: str | None = None) -> bool:
    from sqlalchemy import select
    url = url or config.database_url()
    with get_session(url) as s:
        row = s.execute(
            select(AnalysisSnapshot).where(
                AnalysisSnapshot.dataset == dataset,
                AnalysisSnapshot.window_minutes == int(window_minutes),
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        return Path(row.blob_path).is_file()


def list_analysis_snapshots(url: str | None = None) -> list[dict]:
    """Metadata for every durable snapshot (for the Investigations list)."""
    from sqlalchemy import select
    url = url or config.database_url()
    out = []
    with get_session(url) as s:
        rows = s.execute(select(AnalysisSnapshot).order_by(AnalysisSnapshot.dataset)).scalars()
        for row in rows:
            if not Path(row.blob_path).is_file():
                continue
            out.append({
                "dataset": row.dataset,
                "window_minutes": row.window_minutes,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "summary": row.summary or {},
                "file_counts": row.file_counts or {},
            })
    return out


def save_analysis_snapshot(inv, dataset: str, window_minutes: int,
                           file_counts: dict | None = None,
                           url: str | None = None) -> dict:
    """Pickle `inv` to disk and upsert the DB index row. Returns snapshot metadata."""
    import datetime as _dt
    import pickle

    from sqlalchemy import delete

    url = url or config.database_url()
    window_minutes = int(window_minutes)
    cache = _cache_dir()
    blob = cache / _blob_name(dataset, window_minutes)
    # Write via temp + replace so a crash mid-write cannot leave a half pickle that
    # later loads as a corrupt Investigation.
    tmp = blob.with_suffix(".pkl.tmp")
    with open(tmp, "wb") as f:
        pickle.dump(inv, f, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(blob)

    summary = inv.summary() if hasattr(inv, "summary") else {}
    file_counts = file_counts or {}
    created = _dt.datetime.now(tz=_dt.timezone.utc)

    with get_session(url) as s:
        s.execute(
            delete(AnalysisSnapshot).where(
                AnalysisSnapshot.dataset == dataset,
                AnalysisSnapshot.window_minutes == window_minutes,
            )
        )
        s.add(AnalysisSnapshot(
            dataset=dataset,
            window_minutes=window_minutes,
            created_at=created,
            summary=summary,
            file_counts=file_counts,
            blob_path=str(blob.resolve()),
        ))
        s.commit()

    meta = {
        "dataset": dataset,
        "window_minutes": window_minutes,
        "created_at": created.isoformat(),
        "summary": summary,
        "file_counts": file_counts,
        "blob_path": str(blob),
    }
    log.info("saved analysis snapshot dataset=%s window=%s path=%s",
             dataset, window_minutes, blob)
    return meta


def load_analysis_snapshot(dataset: str, window_minutes: int, url: str | None = None):
    """Return the pickled Investigation, or None if missing/unreadable."""
    import pickle

    from sqlalchemy import select

    url = url or config.database_url()
    window_minutes = int(window_minutes)
    with get_session(url) as s:
        row = s.execute(
            select(AnalysisSnapshot).where(
                AnalysisSnapshot.dataset == dataset,
                AnalysisSnapshot.window_minutes == window_minutes,
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        path = Path(row.blob_path)
    if not path.is_file():
        log.warning("analysis snapshot row exists but blob missing: %s", path)
        return None
    try:
        with open(path, "rb") as f:
            inv = pickle.load(f)
    except Exception as e:
        log.warning("failed to load analysis snapshot %s: %s", path, e)
        return None
    log.info("loaded analysis snapshot dataset=%s window=%s", dataset, window_minutes)
    return inv


def delete_analysis_snapshots(dataset: str, window_minutes: int | None = None,
                              url: str | None = None) -> int:
    """Drop snapshot index rows (+ blob files). All windows if `window_minutes` is None."""
    from sqlalchemy import delete, select

    url = url or config.database_url()
    removed = 0
    with get_session(url) as s:
        q = select(AnalysisSnapshot).where(AnalysisSnapshot.dataset == dataset)
        if window_minutes is not None:
            q = q.where(AnalysisSnapshot.window_minutes == int(window_minutes))
        rows = list(s.execute(q).scalars())
        for row in rows:
            path = Path(row.blob_path)
            path.unlink(missing_ok=True)
            path.with_suffix(".pkl.tmp").unlink(missing_ok=True)
            removed += 1
        if window_minutes is None:
            s.execute(delete(AnalysisSnapshot).where(AnalysisSnapshot.dataset == dataset))
        else:
            s.execute(delete(AnalysisSnapshot).where(
                AnalysisSnapshot.dataset == dataset,
                AnalysisSnapshot.window_minutes == int(window_minutes),
            ))
        s.commit()
    if removed:
        log.info("deleted %d analysis snapshot(s) for dataset=%s window=%s",
                 removed, dataset, window_minutes)
    return removed


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
