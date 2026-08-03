"""In-process analyze progress — polled by the UI while /v1/analyze runs.

The pipeline is synchronous and can take minutes on a real FIR case. This module
holds a thread-safe status dict keyed by (dataset, window) so a second HTTP
request can report stage / percent / ETA without splitting the pipeline into jobs.
"""

from __future__ import annotations

import contextvars
import threading
import time
from typing import Any

_lock = threading.Lock()
_jobs: dict[tuple[str, int], dict[str, Any]] = {}

#: Bound by the API thread that owns the in-flight analyze so pipeline stages can
#: report without threading (dataset, window) through every call.
_bound_dataset: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "analyze_progress_dataset", default=None
)
_bound_window: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "analyze_progress_window", default=None
)

# Ordered stages and their share of the overall bar (must sum to ~100).
STAGES: list[tuple[str, str, float]] = [
    ("parse", "Parsing evidence files", 55.0),
    ("normalize", "Normalising fields & timestamps", 8.0),
    ("resolve", "Resolving entities", 7.0),
    ("documents", "Indexing narrative documents", 5.0),
    ("timeline", "Building timeline & transfers", 5.0),
    ("correlate", "Correlating call / IP / transfers", 8.0),
    ("detect", "Scoring risk & typologies", 7.0),
    ("graph", "Building investigation graph", 4.0),
    ("persist", "Saving durable snapshot", 1.0),
]

_STAGE_WEIGHT = {k: w for k, _label, w in STAGES}
_STAGE_LABEL = {k: label for k, label, _w in STAGES}
_STAGE_ORDER = [k for k, *_ in STAGES]


def bind(dataset: str, window: int):
    """Bind this thread/context to a progress key (API analyze path)."""
    return (
        _bound_dataset.set(dataset),
        _bound_window.set(int(window)),
    )


def unbind(tokens) -> None:
    ds_tok, win_tok = tokens
    _bound_dataset.reset(ds_tok)
    _bound_window.reset(win_tok)


def report(**kwargs) -> None:
    """Update progress for the bound job, if any (no-op in CLI)."""
    ds = _bound_dataset.get()
    win = _bound_window.get()
    if ds is None or win is None:
        return
    update(ds, win, **kwargs)


def _key(dataset: str, window: int) -> tuple[str, int]:
    return (dataset, int(window))


def _prefix_pct(stage_id: str) -> float:
    total = 0.0
    for sid, _label, w in STAGES:
        if sid == stage_id:
            break
        total += w
    return total


def start(dataset: str, window: int, *, force: bool = False) -> None:
    """Mark a job as running. Replaces any prior status for the same key."""
    now = time.monotonic()
    with _lock:
        _jobs[_key(dataset, window)] = {
            "dataset": dataset,
            "window_minutes": int(window),
            "status": "running",
            "stage": "parse",
            "stage_label": _STAGE_LABEL["parse"],
            "message": "Starting pipeline…",
            "percent": 0.0,
            "stage_index": 0,
            "stage_count": len(STAGES),
            "done": 0,
            "total": 0,
            "force": bool(force),
            "started_at": now,
            "updated_at": now,
            "eta_seconds": None,
            "elapsed_seconds": 0.0,
            "error": None,
        }


def update(
    dataset: str,
    window: int,
    *,
    stage: str | None = None,
    message: str | None = None,
    done: int | None = None,
    total: int | None = None,
    fraction: float | None = None,
) -> None:
    """Update progress for an in-flight analyze.

    `fraction` is 0..1 progress *within* the current stage. When `done`/`total`
    are set, fraction is derived from them.
    """
    key = _key(dataset, window)
    with _lock:
        job = _jobs.get(key)
        if not job or job.get("status") != "running":
            return
        if stage and stage in _STAGE_WEIGHT:
            job["stage"] = stage
            job["stage_label"] = _STAGE_LABEL.get(stage, stage)
            try:
                job["stage_index"] = _STAGE_ORDER.index(stage)
            except ValueError:
                pass
        if message is not None:
            job["message"] = message
        if done is not None:
            job["done"] = int(done)
        if total is not None:
            job["total"] = int(total)

        if fraction is None and job.get("total"):
            fraction = min(1.0, max(0.0, job["done"] / max(job["total"], 1)))
        if fraction is None:
            fraction = 0.0
        fraction = min(1.0, max(0.0, float(fraction)))

        sid = job["stage"]
        base = _prefix_pct(sid)
        weight = _STAGE_WEIGHT.get(sid, 1.0)
        job["percent"] = round(min(99.5, base + weight * fraction), 1)

        now = time.monotonic()
        job["updated_at"] = now
        elapsed = now - job["started_at"]
        job["elapsed_seconds"] = round(elapsed, 1)
        pct = job["percent"]
        if pct >= 1.0:
            job["eta_seconds"] = round(elapsed * (100.0 - pct) / pct, 1)
        else:
            job["eta_seconds"] = None


def finish(dataset: str, window: int, *, error: str | None = None,
           from_cache: bool = False) -> None:
    with _lock:
        key = _key(dataset, window)
        job = _jobs.get(key) or {
            "dataset": dataset,
            "window_minutes": int(window),
            "started_at": time.monotonic(),
            "stage_count": len(STAGES),
            "stage_index": len(STAGES) - 1,
        }
        now = time.monotonic()
        job.update({
            "status": "error" if error else "done",
            "percent": 100.0 if not error else job.get("percent", 0),
            "message": error or ("Loaded from cache" if from_cache else "Complete"),
            "stage": "persist" if not error else job.get("stage", "parse"),
            "stage_label": (
                "Error" if error
                else ("Cache hit" if from_cache else _STAGE_LABEL["persist"])
            ),
            "eta_seconds": 0,
            "elapsed_seconds": round(now - job.get("started_at", now), 1),
            "updated_at": now,
            "error": error,
            "from_cache": from_cache,
            "done": job.get("total") or job.get("done") or 0,
            "total": job.get("total") or 0,
        })
        _jobs[key] = job


def get(dataset: str, window: int) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(_key(dataset, window))
        if not job:
            return None
        out = dict(job)
        if out.get("status") == "running" and "started_at" in out:
            out["elapsed_seconds"] = round(time.monotonic() - out["started_at"], 1)
            pct = float(out.get("percent") or 0)
            if pct >= 1.0:
                out["eta_seconds"] = round(
                    out["elapsed_seconds"] * (100.0 - pct) / pct, 1
                )
        out.pop("started_at", None)
        out.pop("updated_at", None)
        out["stages"] = [
            {"id": sid, "label": label, "weight": w}
            for sid, label, w in STAGES
        ]
        return out


def clear(dataset: str, window: int | None = None) -> None:
    with _lock:
        if window is None:
            for k in [k for k in _jobs if k[0] == dataset]:
                _jobs.pop(k, None)
        else:
            _jobs.pop(_key(dataset, window), None)
