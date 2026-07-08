"""Structured logging setup (review fix H1).

Single entry point so every module logs consistently. Level from LOG_LEVEL env.
Use `get_logger(__name__)` in modules; call `setup_logging()` once at process start
(API/dashboard/CLI entrypoints).
"""

from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s :: %(message)s"


def setup_logging(level: str | None = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    lvl = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root = logging.getLogger("erakshak")
    root.setLevel(lvl)
    root.addHandler(handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    # namespace all app loggers under "erakshak"
    short = name.split("backend.app.")[-1] if "backend.app." in name else name
    return logging.getLogger(f"erakshak.{short}")


def audit(action: str, **fields) -> None:
    """Audit-trail logger (review fix H1/C2) — security-relevant events."""
    logger = get_logger("audit")
    kv = " ".join(f"{k}={v}" for k, v in fields.items())
    logger.info("AUDIT %s %s", action, kv)
