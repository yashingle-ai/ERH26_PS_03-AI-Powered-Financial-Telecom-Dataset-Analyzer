"""Configuration loader — central access to settings, scoring rules, and mapping profiles.

All tunables live in YAML under `config/` (NFR-6). This module loads them once and exposes
typed accessors so no thresholds are hard-coded in business logic.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

# Repo root = three levels up from this file (backend/app/core/config.py)
ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = ROOT / "config"


def _load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def settings() -> dict:
    path = Path(os.getenv("ERAKSHAK_CONFIG", CONFIG_DIR / "settings.yaml"))
    return _load_yaml(path)


@lru_cache(maxsize=1)
def scoring_rules() -> dict:
    path = Path(os.getenv("ERAKSHAK_SCORING_RULES", CONFIG_DIR / "scoring_rules.yaml"))
    return _load_yaml(path)


@lru_cache(maxsize=1)
def profiles() -> dict[str, list[dict]]:
    """Load all mapping profiles grouped by source folder (banks/cdr/ipdr)."""
    out: dict[str, list[dict]] = {"banks": [], "cdr": [], "ipdr": []}
    base = CONFIG_DIR / "profiles"
    for group in out:
        gdir = base / group
        if not gdir.exists():
            continue
        for p in sorted(gdir.glob("*.yaml")):
            out[group].append(_load_yaml(p))
    return out


def correlation_window_minutes() -> int:
    return int(settings().get("correlation", {}).get("default_window_minutes", 10))


def auto_detect_threshold() -> float:
    return float(settings().get("ingestion", {}).get("auto_detect_confidence_threshold", 0.8))


def timezone_name() -> str:
    return settings().get("app", {}).get("timezone", "Asia/Kolkata")


def merge_key_types() -> set[str]:
    er = settings().get("entity_resolution", {})
    return set(er.get("merge_key_types", ["PHONE", "ACCOUNT_NO", "IMEI", "IMSI"]))


def max_component_size() -> int:
    return int(settings().get("entity_resolution", {}).get("max_component_size", 50))


def graph_limits() -> dict:
    g = settings().get("graph", {})
    return {
        "max_cycles": int(g.get("max_cycles", 5000)),
        "max_cycle_seconds": float(g.get("max_cycle_seconds", 5.0)),
        "max_layering_paths": int(g.get("max_layering_paths", 20000)),
    }


def upload_limits() -> dict:
    u = settings().get("uploads", {})
    return {
        "allowed_extensions": set(u.get("allowed_extensions",
                                        [".xlsx", ".xls", ".csv", ".txt", ".pdf"])),
        "max_file_mb": int(u.get("max_file_mb", 25)),
        "max_files": int(u.get("max_files", 50)),
    }


def database_url() -> str:
    import os
    return os.getenv("DATABASE_URL") or settings().get("persistence", {}).get(
        "database_url", "sqlite:///./data/erakshak.db")


def persistence_enabled() -> bool:
    import os
    if os.getenv("ERAKSHAK_PERSIST") == "0":
        return False
    return bool(settings().get("persistence", {}).get("enabled", True))


def api_version() -> str:
    return settings().get("api", {}).get("version", "v1")
