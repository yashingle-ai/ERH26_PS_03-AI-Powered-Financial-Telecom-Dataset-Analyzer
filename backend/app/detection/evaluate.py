"""Evaluate detection against the synthetic ground truth (NFR-3 — true vs false positives).

Maps ground-truth participant identifiers (accounts/phones) to resolved entities, then
checks whether those entities were flagged high/medium risk. Reports recall per scenario
type and overall.
"""

from __future__ import annotations

from collections import defaultdict

from ..normalization import normalizers as nz


def _entities_for_identifiers(ids: dict, node_to_entity: dict) -> set[str]:
    ents: set[str] = set()
    for acc in ids.get("accounts", []):
        e = node_to_entity.get(("ACCOUNT_NO", str(acc)))
        if e:
            ents.add(e)
    for ph in ids.get("phones", []):
        e = node_to_entity.get(("PHONE", nz.phone(ph)))
        if e:
            ents.add(e)
    return ents


def evaluate(ground_truth: list[dict], results: dict, node_to_entity: dict,
             flagged_bands=("high", "medium")) -> dict:
    """Detector recall = did the pattern's own rule fire on a participant entity?

    A planted scenario of type T is 'detected' when a participant entity carries a rule
    flag named T. This measures true-positive detection per pattern independently of the
    composite risk band (which is a separate triage/prioritization concern, reported too).
    """
    band_flagged = {eid for eid, r in results.items() if r["band"] in flagged_bands}
    per_type_total: dict[str, int] = defaultdict(int)
    per_type_hit: dict[str, int] = defaultdict(int)

    def entity_rules(eid):
        return {f["rule"] for f in (results.get(eid, {}) or {}).get("rule_flags", [])}

    for sc in ground_truth:
        ids = sc.get("identifiers", {})
        ents = _entities_for_identifiers(ids, node_to_entity)
        if not ents:
            continue
        stype = sc["type"]
        per_type_total[stype] += 1
        fired = any(stype in entity_rules(e) for e in ents)
        if fired:
            per_type_hit[stype] += 1

    total = sum(per_type_total.values())
    hit = sum(per_type_hit.values())
    return {
        "overall_recall": round(hit / total, 3) if total else None,
        "scenarios_evaluated": total,
        "scenarios_detected": hit,
        "per_type": {t: {"detected": per_type_hit[t], "total": per_type_total[t]}
                     for t in per_type_total},
        "entities_band_flagged": len(band_flagged),
        "entities_total": len(results),
    }
