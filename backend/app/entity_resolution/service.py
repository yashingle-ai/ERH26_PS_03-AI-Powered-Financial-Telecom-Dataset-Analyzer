"""Entity resolution (Phase 2, FR-10) — deterministic, graph-based, explainable.

Build a graph whose nodes are identifiers. Identifiers that co-occur on the same record
belong to the SAME real-world entity, so we connect them. Each connected component is one
resolved entity.

Review fix C3 (CGNAT over-merge):
  Only *merge-key* identifier types (PHONE, ACCOUNT_NO, IMEI, IMSI — from config) create
  merge edges. Public IP is intentionally NOT a merge key, because carrier-grade NAT means
  many unrelated subscribers share one public IP; merging on it would collapse innocent
  people into one entity. IP is still recorded as an identifier of whichever entity owned
  the session, but it never links two different entities.

Review fix C3 (circuit breaker):
  If any component exceeds `max_component_size`, it is treated as a resolution failure
  (bad/aliased key) — the offending high-degree identifier is logged and the merge is not
  trusted; the component is still returned but flagged so it can be reviewed.
"""

from __future__ import annotations

import networkx as nx

from ..core import config
from ..core.logging_config import get_logger

log = get_logger(__name__)

_LABEL_PRIORITY = ["HOLDER", "PHONE", "ACCOUNT_NO", "IP", "IMEI"]


def resolve(events: list[dict]) -> tuple[dict, dict]:
    """Return (entities, node_to_entity)."""
    merge_keys = config.merge_key_types()
    g = nx.Graph()

    # attach non-merge identifiers (e.g. IP) to their owning primary, tracked separately
    attach: dict = {}  # primary_node -> set of non-merge identifier nodes

    for ev in events:
        own = ev.get("own_identifiers", [])
        primary = ev.get("primary")
        merge_nodes = [n for n in own if n[0] in merge_keys]
        other_nodes = [n for n in own if n[0] not in merge_keys]

        for node in merge_nodes:
            g.add_node(node)
        if primary and primary[0] in merge_keys:
            for node in merge_nodes:
                if node != primary:
                    g.add_edge(primary, node)
        elif merge_nodes:  # primary isn't a merge key; still connect the merge nodes
            for node in merge_nodes[1:]:
                g.add_edge(merge_nodes[0], node)

        anchor = primary if (primary and primary[0] in merge_keys) else (
            merge_nodes[0] if merge_nodes else None)
        if anchor is not None:
            attach.setdefault(anchor, set()).update(other_nodes)

    node_to_entity: dict = {}
    entities: dict = {}
    max_size = config.max_component_size()
    for i, comp in enumerate(nx.connected_components(g)):
        eid = f"E{i:05d}"
        idents = set(comp)
        oversized = len(idents) > max_size
        if oversized:
            # C3 circuit breaker: likely a shared/aliased key merged too much.
            hub = max(idents, key=lambda n: g.degree(n))
            log.warning("entity %s oversized (%d identifiers); suspicious hub key %s — "
                        "flagging component for review", eid, len(idents), hub)
        for node in comp:
            node_to_entity[node] = eid
        entities[eid] = {"identifiers": idents, "types": {t for (t, _v) in idents},
                         "label": None, "oversized": oversized}

    # attach non-merge identifiers (IP) to the resolved entity of their anchor
    for anchor, others in attach.items():
        eid = node_to_entity.get(anchor)
        if not eid:
            continue
        for node in others:
            entities[eid]["identifiers"].add(node)
            entities[eid]["types"].add(node[0])
            # map IP -> owning entity so counterparty/lookup resolves, but note it may be
            # shared: first owner wins, later owners keep their own entity (no merge).
            node_to_entity.setdefault(node, eid)

    holder_by_account: dict = {}
    for ev in events:
        if ev["event_type"] == "TRANSACTION":
            holder = (ev.get("attributes") or {}).get("holder")
            if holder:
                holder_by_account[ev["primary"]] = holder
    for eid, ent in entities.items():
        ent["label"] = _pick_label(ent["identifiers"], holder_by_account)

    log.info("resolved %d entities from %d events (merge keys=%s)",
             len(entities), len(events), sorted(merge_keys))
    return entities, node_to_entity


def _pick_label(identifiers: set, holder_by_account: dict) -> str:
    for node in identifiers:
        if node in holder_by_account:
            return holder_by_account[node]
    by_type = {t: v for (t, v) in identifiers}
    for t in _LABEL_PRIORITY:
        if t in by_type:
            return f"{by_type[t]}"
    return next(iter(f"{v}" for (_t, v) in identifiers), "unknown")


def assign_entities(events: list[dict], node_to_entity: dict, entities: dict) -> None:
    """Populate entity_id / counterparty_entity_id on each event in place."""
    next_ext = [len(entities)]

    def ext_entity(node):
        if node in node_to_entity:
            return node_to_entity[node]
        eid = f"E{next_ext[0]:05d}"
        next_ext[0] += 1
        entities[eid] = {"identifiers": {node}, "types": {node[0]},
                         "label": str(node[1]), "external": True, "oversized": False}
        node_to_entity[node] = eid
        return eid

    for ev in events:
        ev["entity_id"] = node_to_entity.get(ev["primary"])
        cp = ev.get("counterparty")
        ev["counterparty_entity_id"] = ext_entity(cp) if cp else None
