"""Detection service (Phase 4, FR-11/12/13) — rules + ML -> composite risk score.

Rules-first (explainable, defensible) blended with an unsupervised Isolation Forest that
surfaces anomalies the rules miss. The composite risk score (0-100) mixes the two with the
weights in config/scoring_rules.yaml and always exposes the contributing factors (NFR-3/7).
"""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.ensemble import IsolationForest

from ..core import config
from ..core.logging_config import get_logger
from . import features as featmod
from . import rules as rulemod

log = get_logger(__name__)
MODEL_VERSION = "isoforest-1.0"

# Anchored to the repo, not the process CWD: `detect()` runs from the API server,
# the CLI and pytest, each with a different working directory, and a relative
# path scattered a stray data/models/ tree into whichever one happened to be active.
ROOT = Path(__file__).resolve().parents[3]
MODEL_DIR = Path(os.getenv("ERAKSHAK_MODEL_DIR") or (ROOT / "data" / "models"))

_ML_FEATURES = ["txn_count", "total_in", "total_out", "fan_in", "fan_out",
                "n_ips", "n_imeis", "night_ratio", "inout_ratio",
                "max_rapid_forward", "coincidence_count",
                "max_calls_hour", "max_dormancy_days"]


def _ml_scores(feats: dict) -> tuple[dict[str, float], set[str]]:
    """Anomaly score per entity, plus the set the forest was actually fitted on.

    Fitted over entities we hold observations for — not over the counterparties as well.
    `features.build` gives a feature vector to any entity named in a transfer, so most of
    `feats` can be entities seen only as somebody else's payee: on the demo dataset that is
    **74 of 104**, and every one of the 74 carries a vector whose only non-zero cell is a
    transfer-derived credit. Fitting the forest over that mixture makes "a counterparty with
    one credit and nothing else" the definition of normal, so a real account holder — with
    calls, sessions and hundreds of transactions — becomes an outlier *by construction*
    rather than by behaviour.

    Measured, before this restriction was put back: every one of the 30 observed entities but
    one moved by more than 0.05, mean |delta| 0.252 and max 0.414. At `ml_weight` 0.3 that is
    an average of **7.6 risk-score points and a worst case of 12.4** — enough to cross the
    medium/high band boundary at 70 — caused entirely by who else was in the fit.

    Entities outside the fit get 0.0, which is what they got before they had feature vectors
    at all, so their score comes from the rules alone. That is the defensible half anyway:
    an anomaly score for an entity whose own records are absent would be asserting a
    behavioural profile we do not have. The returned set is what makes that 0.0 legible —
    min-max normalisation also hands 0.0 to the least anomalous *fitted* entity, so the two
    kinds of zero are otherwise indistinguishable.
    """
    cfg = config.scoring_rules().get("ml", {}).get("isolation_forest", {})
    observed = [e for e, f in feats.items() if (f.get("total_events") or 0) > 0]
    if not cfg.get("enabled", True) or len(observed) < 8:
        return {eid: 0.0 for eid in feats}, set()  # too few samples to model
    X = np.array([[float(feats[e].get(k, 0) or 0) for k in _ML_FEATURES] for e in observed])
    model = IsolationForest(
        contamination=cfg.get("contamination", 0.05),
        random_state=cfg.get("random_state", 42),
    )
    model.fit(X)
    raw = -model.score_samples(X)  # higher = more anomalous
    lo, hi = raw.min(), raw.max()
    norm = (raw - lo) / (hi - lo) if hi > lo else np.zeros_like(raw)
    if _persist_enabled():
        _save_model(model, X.shape, cfg)
    scores = {eid: 0.0 for eid in feats}
    scores.update({e: float(s) for e, s in zip(observed, norm)})
    return scores, set(observed)


def _persist_enabled() -> bool:
    """Whether a fitted model should be written to disk.

    Off by default. The forest is refit on every `detect()` call, and `detect()`
    runs on every read of /v1/analyze, /v1/entities, /v1/graph and friends — so
    saving unconditionally meant each page view rewrote the committed artifact
    with a model fit on whatever dataset was being browsed. That is the opposite
    of the reproducibility this was meant to provide, and on a real case it would
    silently write a case-derived model into a tracked file.

    Opt in with ERAKSHAK_PERSIST_MODEL=1 when you actually intend to train.
    """
    return os.getenv("ERAKSHAK_PERSIST_MODEL", "").strip().lower() in {"1", "true", "yes", "on"}


def _save_model(model, shape, cfg) -> None:
    """Review fix M7: persist the fitted model + metadata for reproducibility/versioning."""
    try:
        import json

        import joblib
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, MODEL_DIR / f"{MODEL_VERSION}.joblib")
        meta = {"version": MODEL_VERSION, "features": _ML_FEATURES,
                "n_samples": shape[0], "n_features": shape[1],
                "contamination": cfg.get("contamination", 0.05),
                "random_state": cfg.get("random_state", 42)}
        with open(MODEL_DIR / f"{MODEL_VERSION}.meta.json", "w") as f:
            json.dump(meta, f, indent=2)
        log.info("saved model %s (%d samples, %d features) -> %s",
                 MODEL_VERSION, shape[0], shape[1], MODEL_DIR)
    except Exception as e:  # persistence must never break detection
        log.warning("model persistence failed: %s", e)


def risk_rank(row: dict) -> tuple:
    """The order an investigator reads risk rows in: score, typology breadth, raw weight.

    One definition, shared by /v1/entities, /v1/analyze, the heat map and the report, because
    two copies of a ranking rule drift and then two screens disagree about who is worst.

    `risk_score` saturates: the enabled rule weights sum to 1.2 against a rule component
    capped at 1.0, so an entity exhibiting six typologies and one exhibiting eight can score
    identically. Ordering on score alone then leaves them in dict order — at the top of the
    list, which is the part that gets read.
    """
    return (-(row.get("risk_score") or 0),
            -(row.get("typologies_fired") or 0),
            -(row.get("rule_weight_raw") or 0.0))


def eligibility(events: list[dict], transfers: list[dict], correlation_hits: list[dict],
                medium_hits: list[dict] | None = None) -> list[dict]:
    """Per-rule audit trail: enabled, eligible, fired.

    `rules.eligibility_report` was written and tested but never called by anything, so the
    one artefact that separates "this rule found nothing" from "this rule could not run" was
    unreachable — the same shape F3 was in, where the report generator existed with no HTTP
    route. This is the remaining half of F1, and the half that survives: the calibration half
    was withdrawn once `FIR-0006-2025 U` reached a top risk score of 85.1 on the identical
    unrescaled config, proving the gates were never the problem.

    Features are rebuilt here rather than threaded through `detect`, which keeps that
    function's signature and its callers untouched for one extra pass over the events.
    """
    cfg = config.scoring_rules()
    feats = featmod.build(events, transfers, correlation_hits, medium_hits)
    return rulemod.eligibility_report(feats, transfers, cfg)


def detect(events: list[dict], transfers: list[dict], correlation_hits: list[dict],
           entities: dict, medium_hits: list[dict] | None = None) -> dict:
    cfg = config.scoring_rules()
    feats = featmod.build(events, transfers, correlation_hits, medium_hits)
    flags = rulemod.run_all(feats, transfers, cfg)
    ml, ml_fitted = _ml_scores(feats)

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
        raw_weight = by_entity[eid]["rule_weight"]
        rule_component = min(1.0, raw_weight)
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
            # The enabled rule weights sum to 1.2 while `rule_component` is capped at 1.0, so
            # an entity exhibiting six typologies and one exhibiting eight receive the same
            # rule component and `risk_score` cannot separate them — precisely where an
            # investigator needs the ranking to be sharpest. These three fields restore that
            # discrimination without touching the score, per the rule against redefining a
            # headline metric: they are added, not substituted.
            "typologies_fired": len(by_entity[eid]["rules"]),
            "rule_weight_raw": round(raw_weight, 3),
            "rule_component_saturated": raw_weight > 1.0,
            # Whether `ml_score` is a measurement or an absence. 0.0 is returned both for the
            # least anomalous fitted entity and for every entity the forest was not fitted on
            # (no records of its own, or fewer than 8 observed entities in the whole case —
            # gap D5). Without this an investigator cannot tell "we looked and found nothing
            # unusual" from "we never had anything to look at".
            "ml_scored": eid in ml_fitted,
            "features": {k: feats.get(eid, {}).get(k) for k in _ML_FEATURES},
        }
    # write risk score back onto entities (FR-12)
    for eid, r in results.items():
        if eid in entities:
            entities[eid]["risk_score"] = r["risk_score"]
    return results
