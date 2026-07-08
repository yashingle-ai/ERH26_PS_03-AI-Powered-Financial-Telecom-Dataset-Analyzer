"""FastAPI service (Phase 9 + review fixes C2/M2/M3).

Versioned (/v1), JWT-authenticated, RBAC-protected, with a consistent error schema and
audit logging. Health is public; all data endpoints require an authenticated analyst.

Run:  ./.venv/bin/uvicorn backend.app.api.main:app --reload
Auth: POST /v1/auth/token (form: username, password) -> bearer token
Docs: http://localhost:8000/docs
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from backend.app import pipeline
from backend.app.api.security import (
    authenticate_user,
    create_access_token,
    require_role,
)
from backend.app.core.logging_config import audit, get_logger, setup_logging

setup_logging()
log = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[3]
DATASETS = ROOT / "datasets" / "raw"

app = FastAPI(title="ERakshak API",
              description="AI-Powered Financial & Telecom Dataset Analyzer (ERH26_PS_03)",
              version="1.0.0")
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
    return {
        "summary": inv.summary(),
        "correlation_hits": inv.correlation_hits[:100],
        "top_risk": sorted(inv.risk.values(), key=lambda r: -r["risk_score"])[:20],
    }


@v1.get("/entities/{ds}")
def entities(ds: str, window: int = 10, limit: int = Query(50, le=500), offset: int = 0,
             user=Depends(require_role("analyst"))):
    inv = _analyze(ds, window)
    rows = sorted(inv.risk.values(), key=lambda r: -r["risk_score"])
    return {"total": len(rows), "items": rows[offset: offset + limit]}


@v1.get("/graph/{ds}")
def graph(ds: str, window: int = 10, user=Depends(require_role("analyst"))):
    return _analyze(ds, window).graph["payload"]


app.include_router(v1)
