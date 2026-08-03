"""Load repo-root ``.env`` into the process environment once.

Entrypoints (API, Streamlit, CLI) import this early so ``os.getenv`` sees local
settings without exporting variables in the shell each session. Existing process
env wins (``override=False``) — tests and Docker-injected vars stay authoritative.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_LOADED = False


def load_env() -> None:
    global _LOADED
    if _LOADED:
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_ROOT / ".env", override=False)
    _LOADED = True


load_env()
