"""FastAPI service (Phase 9 + review fixes C2/M2/M3).

Versioned (/v1), JWT-authenticated, RBAC-protected, with a consistent error schema and
audit logging. Health is public; all data endpoints require an authenticated analyst.

Run:  ./.venv/bin/uvicorn backend.app.api.main:app --reload
Auth: POST /v1/auth/token (form: username, password) -> bearer token
Docs: http://localhost:8000/docs
"""

from __future__ import annotations

import os
from collections import Counter
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from backend.app import pipeline
from backend.app.api.security import (
    authenticate_user,
    create_access_token,
    initialise_auth,
    require_role,
)
from backend.app.core.logging_config import audit, get_logger, setup_logging

setup_logging()
log = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[3]
DATASETS = ROOT / "datasets" / "raw"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Resolve credentials/JWT secret eagerly so their "not set" warnings land at
    # boot. Lazily they only appear on first sign-in — and behind compose, nobody
    # can sign in without first reading the generated password out of the log.
    initialise_auth()
    yield


app = FastAPI(title="ERakshak API",
              description="AI-Powered Financial & Telecom Dataset Analyzer (ERH26_PS_03)",
              version="1.0.0",
              lifespan=lifespan)

_cors_origins = [
    o.strip()
    for o in os.getenv(
        "ERAKSHAK_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:8080,http://127.0.0.1:8080,"
        "http://localhost:4173,http://127.0.0.1:4173",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

v1 = APIRouter(prefix="/v1")


# ---- consistent error schema (review fix M3) --------------------------------
@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code,
                        content={"error": {"code": exc.status_code, "message": exc.detail}},
                        headers=getattr(exc, "headers", None))


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500,
                        content={"error": {"code": 500, "message": "Internal server error"}})


@lru_cache(maxsize=8)
def _analyze(ds: str, window: int):
    path = DATASETS / ds
    if not path.is_dir() or "/" in ds or ".." in ds:  # basic path-safety
        raise HTTPException(404, f"dataset '{ds}' not found")
    return pipeline.run(str(path), window_minutes=window)


class AnalyzeRequest(BaseModel):
    dataset: str
    window_minutes: int = 10
    persist: bool = False


def _iso(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _file_counts(inv) -> dict:
    counts = Counter((pf.source_type or "UNKNOWN").upper() for pf in inv.parsed_files)
    return {
        "bank": counts.get("BANK", 0),
        "cdr": counts.get("CDR", 0),
        "ipdr": counts.get("IPDR", 0),
        "other": sum(v for k, v in counts.items() if k not in {"BANK", "CDR", "IPDR"}),
    }


def _money_flow_series(inv) -> list[dict]:
    buckets: dict[str, dict] = {}
    for ev in inv.events:
        if ev.get("event_type") != "TRANSACTION":
            continue
        ts = ev.get("timestamp_start")
        if not isinstance(ts, datetime):
            continue
        key = ts.date().isoformat()
        if key not in buckets:
            buckets[key] = {"t": ts.strftime("%b %d"), "inflow": 0.0, "outflow": 0.0, "_d": key}
        amt = float(ev.get("amount") or 0)
        direction = (ev.get("direction") or "").upper()
        if direction in {"CREDIT", "IN", "CR"}:
            buckets[key]["inflow"] += amt
        else:
            buckets[key]["outflow"] += amt
    series = []
    for key in sorted(buckets):
        vals = buckets[key]
        series.append({
            "t": vals["t"],
            "inflow": round(vals["inflow"] / 1e7, 3),
            "outflow": round(vals["outflow"] / 1e7, 3),
        })
    return series[:30]


def _serialize_identifiers(entity: dict | None) -> list[dict]:
    if not entity:
        return []
    idents = entity.get("identifiers") or set()
    rows = []
    for item in idents:
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            kind, value = item[0], item[1]
        else:
            continue
        rows.append({"kind": str(kind), "value": str(value)})
    rows.sort(key=lambda r: (r["kind"], r["value"]))
    return rows


def _enrich_risk(row: dict, inv) -> dict:
    eid = row.get("entity_id")
    ent = inv.entities.get(eid, {}) if eid else {}
    feats = row.get("features") or {}
    out = dict(row)
    out["identifiers"] = _serialize_identifiers(ent)
    out["types"] = sorted(str(t) for t in (ent.get("types") or set()))
    out["external"] = bool(ent.get("external"))
    out["event_count"] = int(
        (feats.get("txn_count") or 0)
        + (feats.get("coincidence_count") or 0)
    )
    # Prefer raw txn volume when present
    out["volume"] = float((feats.get("total_in") or 0) + (feats.get("total_out") or 0))
    out["txn_count"] = int(feats.get("txn_count") or 0)
    return out


def _serialize_event(ev: dict, entities: dict) -> dict:
    ts = ev.get("timestamp_start")
    minute = None
    if isinstance(ts, datetime):
        minute = ts.hour * 60 + ts.minute
    prov = ev.get("provenance") or {}
    primary = ev.get("primary")
    attrs = dict(ev.get("attributes") or {})
    if ev.get("amount") is not None:
        attrs.setdefault("amount", ev.get("amount"))
    if ev.get("direction"):
        attrs.setdefault("direction", ev.get("direction"))
    if isinstance(primary, (tuple, list)) and len(primary) >= 2:
        attrs.setdefault("primary", f"{primary[0]}:{primary[1]}")
    eid = ev.get("entity_id")
    return {
        "id": f"{ev.get('event_type')}:{_iso(ts)}:{eid}:{prov.get('row')}",
        "event_type": ev.get("event_type"),
        "timestamp": _iso(ts),
        "timestamp_end": _iso(ev.get("timestamp_end")),
        "minute": minute,
        "entity_id": eid,
        "entity_label": (entities.get(eid) or {}).get("label") if eid else None,
        "counterparty_entity_id": ev.get("counterparty_entity_id"),
        "amount": ev.get("amount"),
        "direction": ev.get("direction"),
        "attributes": attrs,
        "provenance": {
            "source_file": prov.get("source_file") or prov.get("file"),
            "sheet": prov.get("sheet"),
            "row": prov.get("row"),
            "offset": prov.get("offset"),
            "profile": prov.get("profile"),
        },
    }


# ---- public ----
@app.get("/health")
def health():
    return {"status": "ok"}


# ---- auth ----
@v1.post("/auth/token")
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form.username, form.password)
    if not user:
        audit("login_failed", user=form.username)
        raise HTTPException(401, "Incorrect username or password")
    audit("login_ok", user=user["username"], roles=user["roles"])
    token = create_access_token(user["username"], user["roles"])
    return {"access_token": token, "token_type": "bearer"}


# ---- protected data endpoints ----
@v1.get("/datasets")
def datasets(user=Depends(require_role("analyst"))):
    return {"datasets": [p.name for p in sorted(DATASETS.glob("*")) if p.is_dir()]}


@v1.post("/analyze")
def analyze(req: AnalyzeRequest, user=Depends(require_role("analyst"))):
    inv = _analyze(req.dataset, req.window_minutes)
    audit("analyze", user=user["username"], dataset=req.dataset, window=req.window_minutes)
    if req.persist:
        from backend.app.persistence import store
        store.persist_investigation(inv, dataset=req.dataset)
        audit("persist", user=user["username"], dataset=req.dataset)
    top = sorted(inv.risk.values(), key=lambda r: -r["risk_score"])[:20]
    return {
        "dataset": req.dataset,
        "window_minutes": req.window_minutes,
        "summary": inv.summary(),
        "file_counts": _file_counts(inv),
        "money_flow_series": _money_flow_series(inv),
        "correlation_hits": inv.correlation_hits[:100],
        "top_risk": [_enrich_risk(r, inv) for r in top],
    }


@v1.get("/entities/{ds}")
def entities(ds: str, window: int = 10, limit: int = Query(50, le=500), offset: int = 0,
             user=Depends(require_role("analyst"))):
    inv = _analyze(ds, window)
    rows = sorted(inv.risk.values(), key=lambda r: -r["risk_score"])
    items = [_enrich_risk(r, inv) for r in rows[offset: offset + limit]]
    return {"total": len(rows), "items": items}


@v1.get("/events/{ds}")
def events(ds: str, window: int = 10, limit: int = Query(200, le=2000), offset: int = 0,
           event_type: str | None = None, user=Depends(require_role("analyst"))):
    inv = _analyze(ds, window)
    # Event timestamps are timezone-aware (normalization canonicalises every source),
    # so the fallback must be aware too — sorting an aware datetime against a naive
    # datetime.min raises TypeError and turns this endpoint into a 500. Normalization
    # currently rejects rows without a timestamp, but that is not this endpoint's
    # invariant to rely on.
    rows = sorted(
        inv.events,
        key=lambda e: e.get("timestamp_start") or datetime.min.replace(tzinfo=UTC),
    )
    if event_type:
        want = event_type.upper()
        rows = [e for e in rows if (e.get("event_type") or "").upper() == want]
    page = rows[offset: offset + limit]
    return {
        "total": len(rows),
        "items": [_serialize_event(e, inv.entities) for e in page],
    }


@v1.get("/graph/{ds}")
def graph(ds: str, window: int = 10, user=Depends(require_role("analyst"))):
    return _analyze(ds, window).graph["payload"]


# ---- data quality (A5 balance breaks + B3 ingestion rejects) ----------------
@v1.get("/data-quality/{ds}")
def data_quality(ds: str, window: int = 10, user=Depends(require_role("analyst"))):
    """Ledger-consistency breaks and per-file ingestion rejects.

    Neither is fatal: rows are surfaced, never silently dropped, so the analyst can
    see where the parsed ledger disagrees with itself before relying on it.
    """
    inv = _analyze(ds, window)
    return {
        "balance_breaks": inv.data_quality,
        "rejects": inv.reject_report(),
        "parsed_files": [pf.summary for pf in inv.parsed_files],
    }


# ---- fuzzy link suggestions (C3) — review-only, never auto-merged -----------
@v1.get("/suggestions/{ds}")
def link_suggestions(ds: str, window: int = 10,
                     threshold: float = Query(0.88, ge=0.5, le=1.0),
                     limit: int = Query(50, le=500),
                     user=Depends(require_role("analyst"))):
    from backend.app.entity_resolution import suggestions

    inv = _analyze(ds, window)
    rows = suggestions.suggest(inv.entities, threshold=threshold, max_pairs=limit)
    audit("suggestions", user=user["username"], dataset=ds, count=len(rows))
    return {"total": len(rows), "items": rows, "threshold": threshold}


# ---- natural-language query (F1) -------------------------------------------
# Two engines. "llm" translates the question into a validated QuerySpec (the LLM sees only
# the field vocabulary, never case data) and executes it locally. "rules" is the offline
# interpreter, used when no API key is configured or the question can't be planned — so
# the endpoint keeps working air-gapped.
class QueryRequest(BaseModel):
    q: str
    window_minutes: int = 10
    engine: str | None = None          # "llm" | "rules"; default: llm when available


@v1.post("/query/{ds}")
def nl_search(ds: str, req: QueryRequest, user=Depends(require_role("analyst"))):
    from backend.app.search import dsl, llm_planner, nl_query

    inv = _analyze(ds, req.window_minutes)

    if req.engine != "rules":
        try:
            spec = llm_planner.plan(req.q)
        except ValueError as e:        # the outbound-payload guard tripped
            raise HTTPException(400, str(e)) from e
        if spec is not None:
            out = dsl.execute(spec, inv)
            audit("nl_query", user=user["username"], dataset=ds, q=req.q, engine="llm")
            return {
                "query": req.q,
                "engine": "llm",
                "explanation": spec.explanation or "Structured query executed locally.",
                "rows": out["rows"],
                "matched": len(out["rows"]),
                "total": out["total"],
                "truncated": out["truncated"],
                # Resolved relative window, blank-key count, and any executor note —
                # all part of "what actually ran", which the analyst must be able to see.
                "window": out.get("window"),
                "skipped_blank": out.get("skipped_blank"),
                "note": out.get("note"),
                # The generated plan is part of the evidentiary record: an analyst must be
                # able to see exactly what was run, not just the answer.
                "spec": spec.model_dump(mode="json"),
            }

    result = nl_query.answer(req.q, {
        "entities": inv.entities,
        "risk": inv.risk,
        "events": inv.events,
        "correlation_hits": inv.correlation_hits,
    })
    rows = result.get("rows")
    audit("nl_query", user=user["username"], dataset=ds, q=req.q, engine="rules")
    return {
        "query": req.q,
        "engine": "rules",
        "explanation": result["explanation"],
        "rows": rows,
        "matched": len(rows) if rows is not None else 0,
        "total": result.get("total", len(rows) if rows is not None else 0),
        "truncated": bool(result.get("truncated")),
        "window": None,
        "skipped_blank": None,
        "note": None,
        "spec": None,
    }


app.include_router(v1)
