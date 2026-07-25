"""Detection service (Phase 4, FR-11/12/13) — rules + ML -> composite risk score.

Rules-first (explainable, defensible) blended with an unsupervised Isolation Forest that
surfaces anomalies the rules miss. The composite risk score (0-100) mixes the two with the
weights in config/scoring_rules.yaml and always exposes the contributing factors (NFR-3/7).
"""

from __future__ import annotations

import os
from collections import defaultdict

import numpy as np
from sklearn.ensemble import IsolationForest

from ..core import config
from ..core.logging_config import get_logger
from . import features as featmod
from . import rules as rulemod

log = get_logger(__name__)
MODEL_VERSION = "isoforest-1.0"

_ML_FEATURES = ["txn_count", "total_in", "total_out", "fan_in", "fan_out",
                "n_ips", "n_imeis", "night_ratio", "inout_ratio",
                "max_rapid_forward", "coincidence_count",
                "max_calls_hour", "max_dormancy_days"]


def _ml_scores(feats: dict) -> dict[str, float]:
    cfg = config.scoring_rules().get("ml", {}).get("isolation_forest", {})
    if not cfg.get("enabled", True) or len(feats) < 8:
        return {eid: 0.0 for eid in feats}  # too few samples to model
    eids = list(feats)
    X = np.array([[float(feats[e].get(k, 0) or 0) for k in _ML_FEATURES] for e in eids])
    model = IsolationForest(
        contamination=cfg.get("contamination", 0.05),
        random_state=cfg.get("random_state", 42),
    )
    model.fit(X)
    raw = -model.score_samples(X)  # higher = more anomalous
    lo, hi = raw.min(), raw.max()
    norm = (raw - lo) / (hi - lo) if hi > lo else np.zeros_like(raw)
    _save_model(model, X.shape, cfg)
    return {e: float(s) for e, s in zip(eids, norm)}


def _save_model(model, shape, cfg) -> None:
    """Review fix M7: persist the fitted model + metadata for reproducibility/versioning."""
    try:
        import joblib
        out = os.path.join("data", "models")
        os.makedirs(out, exist_ok=True)
        joblib.dump(model, os.path.join(out, f"{MODEL_VERSION}.joblib"))
        meta = {"version": MODEL_VERSION, "features": _ML_FEATURES,
                "n_samples": shape[0], "n_features": shape[1],
                "contamination": cfg.get("contamination", 0.05),
                "random_state": cfg.get("random_state", 42)}
        import json
        with open(os.path.join(out, f"{MODEL_VERSION}.meta.json"), "w") as f:
            json.dump(meta, f, indent=2)
        log.info("saved model %s (%d samples, %d features)", MODEL_VERSION, shape[0], shape[1])
    except Exception as e:  # persistence must never break detection
        log.warning("model persistence failed: %s", e)


def detect(events: list[dict], transfers: list[dict], correlation_hits: list[dict],
           entities: dict) -> dict:
    cfg = config.scoring_rules()
    feats = featmod.build(events, transfers, correlation_hits)
    flags = rulemod.run_all(feats, transfers, cfg)
    ml = _ml_scores(feats)

    by_entity: dict[str, dict] = defaultdict(lambda: {"rules": [], "rule_weight": 0.0})
    for fl in flags:
        e = by_entity[fl["entity_id"]]
        e["rules"].append({"rule": fl["rule"], "detail": fl["detail"], "weight": fl["weight"]})
        e["rule_weight"] += fl["weight"]

    rs_cfg = cfg.get("risk_score", {})
    w_ml = rs_cfg.get("ml_weight", 0.3)
    w_rules = rs_cfg.get("rules_weight", 0.7)
    bands = rs_cfg.get("bands", {"low": [0, 39], "medium": [40, 69], "high": [70, 100]})

    results: dict[str, dict] = {}
    all_eids = set(feats) | set(by_entity)
    for eid in all_eids:
        rule_component = min(1.0, by_entity[eid]["rule_weight"])
        ml_component = ml.get(eid, 0.0)
        score = round(100 * (w_rules * rule_component + w_ml * ml_component), 1)
        band = "low"
        for name, (lo, hi) in bands.items():
            if lo <= score <= hi:
                band = name
        results[eid] = {
            "entity_id": eid,
            "label": entities.get(eid, {}).get("label"),
            "risk_score": score,
            "band": band,
            "ml_score": round(ml_component, 3),
            "rule_flags": by_entity[eid]["rules"],
            "features": {k: feats.get(eid, {}).get(k) for k in _ML_FEATURES},
        }
    # write risk score back onto entities (FR-12)
    for eid, r in results.items():
        if eid in entities:
            entities[eid]["risk_score"] = r["risk_score"]
    return results
