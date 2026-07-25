"""Fuzzy link suggestions (C3) — REVIEW-ONLY, never auto-merged.

Deterministic resolution stays authoritative (Doc 03 Topic 3). This surfaces *candidate*
same-actor pairs (similar labels / shared beneficiary names) for an analyst to confirm —
it does not alter entities. Kept conservative to avoid the false-merge risk that would hurt
evidentiary trust (and CGNAT-style collapse).
"""

from __future__ import annotations

from difflib import SequenceMatcher


def _norm(s: str) -> str:
    return "".join(ch for ch in str(s).lower() if ch.isalnum() or ch == " ").strip()


def suggest(entities: dict, threshold: float = 0.88, max_pairs: int = 50) -> list[dict]:
    """Return candidate same-entity pairs by label similarity (review-only)."""
    # only consider named (person-like) entities, not raw ids
    named = [(eid, _norm(v.get("label", ""))) for eid, v in entities.items()
             if v.get("label") and any(c.isalpha() for c in str(v.get("label")))
             and not v.get("external")]
    named = [(eid, lab) for eid, lab in named if len(lab) >= 5]
    out: list[dict] = []
    for i in range(len(named)):
        for j in range(i + 1, len(named)):
            a, la = named[i]
            b, lb = named[j]
            if abs(len(la) - len(lb)) > 6:
                continue
            r = SequenceMatcher(None, la, lb).ratio()
            if r >= threshold and la != lb:
                out.append({"entity_a": a, "label_a": entities[a]["label"],
                            "entity_b": b, "label_b": entities[b]["label"],
                            "similarity": round(r, 3)})
    out.sort(key=lambda x: -x["similarity"])
    return out[:max_pairs]
