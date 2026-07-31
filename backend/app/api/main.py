"""FastAPI service (Phase 9 + review fixes C2/M2/M3).

Versioned (/v1), JWT-authenticated, RBAC-protected, with a consistent error schema and
audit logging. Health is public; all data endpoints require an authenticated analyst.

Run:  ./.venv/bin/uvicorn backend.app.api.main:app --reload
Auth: POST /v1/auth/token (form: username, password) -> bearer token
Docs: http://localhost:8000/docs
"""

from __future__ import annotations

import os
import re
import threading
from collections import Counter
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from backend.app import pipeline
from backend.app.api.security import (
    authenticate_user,
    create_access_token,
    get_current_user,
    initialise_auth,
    require_role,
)
from backend.app.core.logging_config import audit, get_logger, setup_logging
from backend.app.detection import service as detection
from backend.app.ingestion import detector
from backend.app.reporting import service as reporting

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
def _analyze_uncoordinated(ds: str, window: int):
    path = DATASETS / ds
    if not path.is_dir() or "/" in ds or ".." in ds:  # basic path-safety
        raise HTTPException(404, f"dataset '{ds}' not found")
    return pipeline.run(str(path), window_minutes=window)


#: One lock per (dataset, window). See _analyze.
_analyze_locks: dict[tuple[str, int], threading.Lock] = {}
_analyze_locks_guard = threading.Lock()


def _analyze(ds: str, window: int):
    """Run the pipeline for a dataset, at most once at a time per key.

    lru_cache only memoises *completed* calls, so concurrent identical requests
    each miss the cache and each run the whole pipeline. That is fine for the
    synthetic fixtures and ruinous for a real case: six overlapping runs of a
    676 MB dataset drove the container to 6.4 of 7.6 GiB and 104% CPU, and the
    UI can easily produce them — several routes query analyze, and a retry or an
    impatient second click adds more.

    Serialising on the key means the first caller computes and the rest wait and
    then hit the warm cache. Requests run on FastAPI's threadpool (these are
    sync defs), so blocking here holds a worker but does not stall the loop.
    """
    key = (ds, window)
    with _analyze_locks_guard:
        lock = _analyze_locks.setdefault(key, threading.Lock())
    if not lock.acquire(blocking=False):
        log.info("analyze(%s, w=%s) already running — waiting for it instead of "
                 "starting a second run", ds, window)
        lock.acquire()
    try:
        return _analyze_uncoordinated(ds, window)
    finally:
        lock.release()


# `_analyze.cache_clear` is called after an upload; keep that surface working now
# that the memoised function is wrapped.
_analyze.cache_clear = _analyze_uncoordinated.cache_clear


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


#: Shared with the report generator so both agree on who is worst. See `detection.risk_rank`.
_risk_rank = detection.risk_rank


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


@v1.post("/auth/refresh")
def refresh(user=Depends(get_current_user)):
    """Exchange a still-valid token for a fresh one.

    Analysing a real case takes minutes, and an analyst reads results for far
    longer. Without this, a fixed-lifetime token expires mid-investigation and the
    UI drops them at the login screen — losing an in-flight run rather than any
    security being gained. No role gate: renewing is not a privileged action, and
    the roles carried over are the ones already in the presented token.
    """
    token = create_access_token(user["username"], user["roles"])
    audit("token_refresh", user=user["username"])
    return {"access_token": token, "token_type": "bearer"}


# ---- protected data endpoints ----
@v1.get("/datasets")
def datasets(user=Depends(require_role("analyst"))):
    return {"datasets": [p.name for p in sorted(DATASETS.glob("*")) if p.is_dir()]}


# ---- upload ----
#: Extensions the ingestion layer can actually open, plus archives it expands.
UPLOAD_EXTENSIONS = set(detector.FORMAT_BY_EXT) | {".zip"}
UPLOAD_KINDS = ("bank", "cdr", "ipdr", "other")
_MAX_UPLOAD_BYTES = int(os.getenv("ERAKSHAK_MAX_UPLOAD_MB", "256")) * 1024 * 1024
_MAX_UPLOAD_FILES = int(os.getenv("ERAKSHAK_MAX_UPLOAD_FILES", "200"))
_CHUNK = 1024 * 1024

#: Dataset names become directory names. Anything outside this set is refused rather
#: than escaped, so there is no encoding for a caller to slip through.
_SAFE_DATASET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

#: Fixture datasets that ship in the repository, and are therefore the only two
#: paths under datasets/ that .gitignore allowlists. Uploading into them mixes real
#: evidence into a tracked directory, where a later `git add -A` would commit it —
#: and no ignore pattern can tell an uploaded statement from a fixture one, since
#: both are a .csv in the same bank/ folder. Refuse the write instead.
FIXTURE_DATASETS = frozenset({"demo", "smoke"})


def _dataset_dir(ds: str, *, create: bool = False, writable: bool = False) -> Path:
    """Resolve a dataset directory, refusing anything that escapes DATASETS."""
    if not _SAFE_DATASET.match(ds) or ".." in ds:
        raise HTTPException(400, "invalid dataset name: use letters, digits, . _ - (max 64)")
    if writable and ds.lower() in FIXTURE_DATASETS:
        raise HTTPException(
            409,
            f"'{ds}' is a read-only sample dataset that ships with the repository. "
            "Use a new name for your case (e.g. 'fir-65-2024') so real evidence is "
            "never written into a tracked directory.",
        )
    path = (DATASETS / ds).resolve()
    # Defence in depth: the regex already excludes separators, but a symlinked
    # datasets/raw would still be a way out. Verify the resolved path, not the input.
    if not path.is_relative_to(DATASETS.resolve()):
        raise HTTPException(400, "invalid dataset name")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    elif not path.is_dir():
        raise HTTPException(404, f"dataset '{ds}' not found")
    return path


def _safe_filename(name: str) -> str:
    """Reduce a client-supplied filename to a bare, harmless basename.

    Uploads are attacker-controlled by definition. Take the last path component
    under both separators (a Windows client sends backslashes that PurePosixPath
    would keep), drop control characters, and refuse the traversal names outright.
    """
    base = re.split(r"[\\/]", name)[-1].strip()
    base = re.sub(r"[\x00-\x1f\x7f]", "", base)
    base = base.lstrip(".") if base in {".", ".."} else base
    if not base or base in {".", ".."}:
        raise HTTPException(400, "invalid filename")
    return base[:200]


def _unique_path(directory: Path, filename: str) -> Path:
    """Never overwrite existing evidence — suffix instead."""
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem, suffix = Path(filename).stem, Path(filename).suffix
    for n in range(1, 1000):
        candidate = directory / f"{stem}-{n}{suffix}"
        if not candidate.exists():
            return candidate
    raise HTTPException(409, f"too many files named like '{filename}'")


@v1.post("/upload/{ds}")
async def upload(ds: str,
                 files: list[UploadFile] = File(...),
                 kind: str = Form("other"),
                 user=Depends(require_role("analyst"))):
    """Accept Bank/CDR/IPDR files into datasets/raw/{ds}/{kind}/.

    `kind` only decides the subfolder — the parser identifies a file by its content,
    not its location, so a misfiled statement is still read as a statement.

    Every file is reported back with its own status. A rejected file must never be
    silently skipped: in a forensic tool, evidence you think you uploaded and
    evidence the system actually holds have to be the same set.
    """
    if kind not in UPLOAD_KINDS:
        raise HTTPException(400, f"kind must be one of {', '.join(UPLOAD_KINDS)}")
    if not files:
        raise HTTPException(400, "no files provided")
    if len(files) > _MAX_UPLOAD_FILES:
        raise HTTPException(413, f"too many files in one request (max {_MAX_UPLOAD_FILES})")

    target = _dataset_dir(ds, create=True, writable=True) / kind
    target.mkdir(parents=True, exist_ok=True)

    results, accepted, total_bytes = [], 0, 0
    for upload_file in files:
        name = _safe_filename(upload_file.filename or "")
        suffix = Path(name).suffix.lower()
        if suffix not in UPLOAD_EXTENSIONS:
            shown = suffix or "no extension"
            results.append({"file": name, "status": "rejected",
                            "reason": f"unsupported type '{shown}'"})
            continue

        dest = _unique_path(target, name)
        written = 0
        try:
            with dest.open("wb") as out:
                while chunk := await upload_file.read(_CHUNK):
                    written += len(chunk)
                    if written > _MAX_UPLOAD_BYTES:
                        raise ValueError(f"exceeds {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
                    out.write(chunk)
        except Exception as exc:
            # Streamed writes leave a partial file behind on failure; a truncated
            # statement that still parses is worse than no file at all.
            dest.unlink(missing_ok=True)
            results.append({"file": name, "status": "rejected", "reason": str(exc)})
            continue
        finally:
            await upload_file.close()

        accepted += 1
        total_bytes += written
        results.append({"file": dest.name, "status": "stored",
                        "bytes": written, "path": f"{ds}/{kind}/{dest.name}"})

    if accepted:
        # Results are memoised per (dataset, window); without this the next analyze
        # would confidently return figures that predate the upload.
        _analyze.cache_clear()

    audit("upload", user=user["username"], dataset=ds, kind=kind,
          accepted=accepted, rejected=len(results) - accepted, bytes=total_bytes)
    return {"dataset": ds, "kind": kind, "accepted": accepted,
            "rejected": len(results) - accepted, "bytes": total_bytes, "files": results}


@v1.post("/analyze")
def analyze(req: AnalyzeRequest, user=Depends(require_role("analyst"))):
    inv = _analyze(req.dataset, req.window_minutes)
    audit("analyze", user=user["username"], dataset=req.dataset, window=req.window_minutes)
    if req.persist:
        from backend.app.persistence import store
        store.persist_investigation(inv, dataset=req.dataset)
        audit("persist", user=user["username"], dataset=req.dataset)
    top = sorted(inv.risk.values(), key=_risk_rank)[:20]
    return {
        "dataset": req.dataset,
        "window_minutes": req.window_minutes,
        "summary": inv.summary(),
        "file_counts": _file_counts(inv),
        "money_flow_series": _money_flow_series(inv),
        "correlation_hits": inv.correlation_hits[:100],
        "correlation_hits_medium": inv.correlation_hits_medium[:100],
        "top_risk": [_enrich_risk(r, inv) for r in top],
    }


@v1.get("/entities/{ds}")
def entities(ds: str, window: int = 10, limit: int = Query(50, le=500), offset: int = 0,
             user=Depends(require_role("analyst"))):
    inv = _analyze(ds, window)
    rows = sorted(inv.risk.values(), key=_risk_rank)
    items = [_enrich_risk(r, inv) for r in rows[offset: offset + limit]]
    return {"total": len(rows), "items": items}


def _parse_bound(value: str | None) -> datetime | None:
    """Parse a time bound, returning None when absent or unparseable.

    Timezone-naive input is read as the canonical case timezone rather than UTC: every
    event has already been normalised to IST, so treating `start=2024-05-15` as UTC would
    silently shift the window by 5.5 hours.
    """
    if not value:
        return None
    try:
        from dateutil import parser as dtparser

        from ..normalization import normalizers as nz
        parsed = dtparser.parse(value, dayfirst=True)
    except (ValueError, OverflowError, TypeError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=nz.CANONICAL_TZ)


def _within(ts, lo: datetime | None, hi: datetime | None) -> bool:
    if not isinstance(ts, datetime):
        return False
    if lo and ts < lo:
        return False
    return not (hi and ts > hi)


def _event_location(ev: dict) -> str:
    """Location text for an event — tower location and cell id, same fields the DSL reads.

    `Field_.LOCATION` maps to `attributes.location` and `Field_.CELL_ID` to
    `attributes.cell_id`, so matching on both here keeps this endpoint and `/v1/query`
    answering the same question. A CDR that only carries a cell id is still located.
    """
    attrs = ev.get("attributes") or {}
    return " ".join(str(attrs.get(k) or "") for k in ("location", "cell_id")).strip()


@v1.get("/events/{ds}")
def events(ds: str, window: int = 10, limit: int = Query(200, le=2000), offset: int = 0,
           event_type: str | None = None,
           entity: str | None = None,
           location: str | None = None,
           min_amount: float | None = None,
           max_amount: float | None = None,
           start: str | None = None,
           end: str | None = None,
           user=Depends(require_role("analyst"))):
    """Chronological event listing with the four FR-15 filters.

    Entity, amount, time and location were reachable only through the `/v1/query` DSL; this
    endpoint filtered by `event_type` alone, so the primary listing could not answer the
    requirement its own DSL already covered. `location` matches tower location OR cell id,
    and `entity` matches the entity id or its label, because an analyst reading the UI has
    the label and not the internal id.
    """
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
    if entity:
        needle = entity.strip().lower()
        rows = [e for e in rows
                if needle == (e.get("entity_id") or "").lower()
                or needle == (e.get("counterparty_entity_id") or "").lower()
                or needle in str((inv.entities.get(e.get("entity_id")) or {})
                                 .get("label") or "").lower()]
    if location:
        needle = location.strip().lower()
        rows = [e for e in rows if needle in _event_location(e).lower()]
    if min_amount is not None:
        rows = [e for e in rows if (e.get("amount") or 0) >= min_amount]
    if max_amount is not None:
        rows = [e for e in rows if (e.get("amount") or 0) <= max_amount]
    if start or end:
        lo = _parse_bound(start)
        hi = _parse_bound(end)
        rows = [e for e in rows if _within(e.get("timestamp_start"), lo, hi)]
    page = rows[offset: offset + limit]
    return {
        "total": len(rows),
        "items": [_serialize_event(e, inv.entities) for e in page],
    }


@v1.get("/rule-eligibility/{ds}")
def rule_eligibility(ds: str, window: int = 10, user=Depends(require_role("analyst"))):
    """FR-11/12: per rule, was it enabled, could it apply to this case, and did it fire.

    `0 high-risk entities` reads to an investigator as "nothing suspicious here". This says
    which of the two it actually is for each rule — `structuring` finding no transaction near
    the reporting threshold is a legitimate finding about the case, not a missed detection,
    and it must not look the same as a rule that never ran.

    The computation existed in `rules.eligibility_report` and was tested, but nothing called
    it, so the distinction was unreachable from the product.
    """
    inv = _analyze(ds, window)
    rows = inv.rule_eligibility or []
    return {
        "dataset": ds,
        "window_minutes": window,
        "rules": rows,
        "rules_enabled": sum(1 for r in rows if r.get("enabled")),
        "rules_disabled": sum(1 for r in rows if not r.get("enabled")),
        "rules_that_fired": sum(1 for r in rows if (r.get("fired") or 0) > 0),
        "rules_enabled_but_inert": sum(
            1 for r in rows
            if r.get("enabled") and not r.get("fired") and (r.get("eligible") or 0) == 0),
    }


@v1.get("/risk-heatmap/{ds}")
def risk_heatmap(ds: str, window: int = 10, top: int = Query(20, ge=1, le=200),
                 user=Depends(require_role("analyst"))):
    """FR-18: entities x typologies, as a matrix the caller can render.

    The heat map existed only inside `dashboard/app.py`, so the React app — the primary UI —
    could not show which typologies drive each risky entity. Same shape as the Streamlit
    version so the two agree: rows are the top entities by risk score, columns are the rules
    that actually fired on them, and each cell is that rule's weight.

    Entities with no fired rule are excluded rather than drawn as an empty row, because a
    blank row reads as "assessed and clean" when it means "nothing fired". `rules_evaluated`
    is returned alongside so a caller can tell an empty matrix (nothing fired anywhere) from
    a missing one, which is the same distinction the reject report draws for rows.
    """
    inv = _analyze(ds, window)
    ranked = sorted(inv.risk.values(), key=_risk_rank)
    rows = [r for r in ranked if r.get("rule_flags")][:top]
    columns = sorted({f["rule"] for r in rows for f in r["rule_flags"]})

    matrix, entities_out = [], []
    for r in rows:
        weights = {f["rule"]: f["weight"] for f in r["rule_flags"]}
        matrix.append([round(float(weights.get(rule, 0.0)) * 100, 1) for rule in columns])
        eid = r.get("entity_id")
        entities_out.append({
            "entity_id": eid,
            "label": r.get("label"),
            "risk_score": r.get("risk_score"),
            "band": r.get("band"),
            "rules_fired": sorted(weights),
        })

    all_rules = sorted({f["rule"] for r in inv.risk.values() for f in (r.get("rule_flags") or [])})
    return {
        "dataset": ds,
        "window_minutes": window,
        "columns": columns,
        "entities": entities_out,
        "matrix": matrix,
        "unit": "rule weight x 100",
        "rules_evaluated": all_rules,
        "entities_scored": len(inv.risk),
        "entities_with_a_fired_rule": sum(1 for r in inv.risk.values() if r.get("rule_flags")),
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
    from backend.app.search import answer as answer_mod
    from backend.app.search import dsl, llm_planner, nl_query, offline_planner

    inv = _analyze(ds, req.window_minutes)

    spec = None
    engine = "rules"
    if req.engine != "rules":
        try:
            spec = llm_planner.plan(req.q)
        except ValueError as e:        # the outbound-payload guard tripped
            raise HTTPException(400, str(e)) from e
        if spec is not None:
            engine = "llm"

    # Air-gapped / no-key path: map common investigator phrasings onto a QuerySpec
    # so aggregation questions still get a real answer + auditable plan.
    if spec is None and req.engine != "llm":
        spec = offline_planner.plan(req.q)
        if spec is not None:
            engine = "offline"

    if spec is not None:
        out = dsl.execute(spec, inv)
        plain = answer_mod.compose_answer(spec, out)
        audit("nl_query", user=user["username"], dataset=ds, q=req.q, engine=engine)
        return {
            "query": req.q,
            "engine": engine,
            "answer": plain,
            "explanation": spec.explanation or "Structured query executed locally.",
            "rows": out["rows"],
            "matched": len(out["rows"]),
            "total": out["total"],
            "truncated": out["truncated"],
            "window": out.get("window"),
            "skipped_blank": out.get("skipped_blank"),
            "note": out.get("note"),
            "spec": spec.model_dump(mode="json"),
        }

    result = nl_query.answer(req.q, {
        "entities": inv.entities,
        "risk": inv.risk,
        "events": inv.events,
        "correlation_hits": inv.correlation_hits,
    })
    rows = result.get("rows")
    plain = answer_mod.compose_answer(
        None,
        {"rows": rows, "total": result.get("total", len(rows) if rows else 0),
         "truncated": result.get("truncated"), "note": None, "window": None},
        rules_explanation=result["explanation"],
    )
    audit("nl_query", user=user["username"], dataset=ds, q=req.q, engine="rules")
    return {
        "query": req.q,
        "engine": "rules",
        "answer": plain,
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


class ReportRequest(BaseModel):
    window_minutes: int = 10
    fmt: str = "pdf"


@v1.post("/report/{ds}")
def report(ds: str, req: ReportRequest, user=Depends(require_role("analyst"))):
    """Generate a forensic report (FR-16) and return the file.

    The generator existed and worked, but only the Streamlit dashboard could reach
    it — the React app, which is the primary UI, had no route to the problem
    statement's headline deliverable.

    Written under data/outputs/ as well as streamed back: that directory is
    gitignored and dockerignored because a report is derived from case evidence and
    inherits its sensitivity.
    """
    fmt = (req.fmt or "pdf").lower()
    if fmt not in {"pdf", "docx"}:
        raise HTTPException(400, "fmt must be 'pdf' or 'docx'")

    inv = _analyze(ds, req.window_minutes)
    payload = reporting.payload_from_investigation(inv, ds, req.window_minutes)
    out_dir = ROOT / "data" / "outputs"
    try:
        path = reporting.generate(payload, str(out_dir), fmt=fmt)
    except Exception:
        # The generator reaches into matplotlib and reportlab; a failure there is not
        # the analyst's fault and must not surface as a bare 500 with no context.
        log.exception("report generation failed for %s (fmt=%s)", ds, fmt)
        raise HTTPException(500, "report generation failed — see server logs") from None

    audit("report", user=user["username"], dataset=ds, fmt=fmt,
          window=req.window_minutes, path=Path(path).name)
    media = ("application/pdf" if fmt == "pdf" else
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    return FileResponse(path, media_type=media, filename=Path(path).name)


app.include_router(v1)
