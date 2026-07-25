"""Graph / network service (Phase 5, FR-14/18).

Builds the investigation graph: entities are nodes; edges are money-flow (from
transactions) and communication (from calls). Computes network metrics used by the
dashboard and report: degree/centrality (key actors), communities (rings), and exposes a
node/edge payload for visualization with drill-down.
"""

from __future__ import annotations

from collections import defaultdict

import networkx as nx

from ..core.logging_config import get_logger
from . import money_flow

log = get_logger(__name__)


def build_communication_edges(events: list[dict]) -> list[dict]:
    """Aggregate calls between two entities into weighted communication edges."""
    agg: dict[tuple, dict] = defaultdict(lambda: {"count": 0})
    for e in events:
        if e["event_type"] != "CALL":
            continue
        a, b = e.get("entity_id"), e.get("counterparty_entity_id")
        if a and b and a != b:
            agg[(a, b)]["count"] += 1
    return [{"from_entity": a, "to_entity": b, "count": v["count"]} for (a, b), v in agg.items()]


def build(events: list[dict], entities: dict, risk_results: dict | None = None) -> dict:
    transfers = money_flow.build_transfers(events)
    comms = build_communication_edges(events)
    risk_results = risk_results or {}

    g = nx.MultiDiGraph()
    for eid, ent in entities.items():
        g.add_node(eid, label=ent.get("label"),
                   risk=(risk_results.get(eid, {}) or {}).get("risk_score", ent.get("risk_score")),
                   types=sorted(ent.get("types", [])), external=ent.get("external", False))

    money_agg: dict[tuple, dict] = defaultdict(lambda: {"amount": 0.0, "count": 0})
    for tr in transfers:
        k = (tr["from_entity"], tr["to_entity"])
        money_agg[k]["amount"] += tr.get("amount") or 0.0
        money_agg[k]["count"] += 1
    for (a, b), v in money_agg.items():
        g.add_edge(a, b, kind="MONEY_FLOW", amount=round(v["amount"], 2), count=v["count"])
    for c in comms:
        g.add_edge(c["from_entity"], c["to_entity"], kind="COMMUNICATION", count=c["count"])

    metrics = _metrics(g)
    return {"graph": g, "transfers": transfers, "comms": comms, "metrics": metrics,
            "payload": to_payload(g, metrics)}


def _metrics(g: nx.MultiDiGraph) -> dict:
    simple = nx.DiGraph()
    for u, v, data in g.edges(data=True):
        w = data.get("amount", data.get("count", 1)) or 1
        if simple.has_edge(u, v):
            simple[u][v]["weight"] += w
        else:
            simple.add_edge(u, v, weight=w)
    for n in g.nodes:
        simple.add_node(n)

    # Exact betweenness is O(V*E) — too slow on large real graphs. Sample k pivots when big.
    n_nodes = simple.number_of_nodes()
    try:
        if n_nodes > 800:
            k = min(200, n_nodes)
            centrality = nx.betweenness_centrality(simple, k=k, weight="weight", seed=42)
            log.info("large graph (%d nodes): approx betweenness with k=%d pivots", n_nodes, k)
        else:
            centrality = nx.betweenness_centrality(simple, weight="weight")
    except Exception as e:
        log.warning("betweenness_centrality failed (%s); falling back to degree", e)
        centrality = {n: simple.degree(n) for n in simple.nodes}
    degree = dict(simple.degree())
    undirected = simple.to_undirected()
    communities: dict[str, int] = {}
    try:
        for i, comm in enumerate(nx.community.greedy_modularity_communities(undirected)):
            for n in comm:
                communities[n] = i
    except Exception as e:
        log.warning("community detection failed (%s); defaulting to single community", e)
        communities = {n: 0 for n in undirected.nodes}
    return {"centrality": centrality, "degree": degree, "communities": communities}


def to_payload(g: nx.MultiDiGraph, metrics: dict) -> dict:
    """Node/edge lists for the dashboard (drill-down friendly)."""
    nodes = []
    for n, d in g.nodes(data=True):
        nodes.append({
            "id": n, "label": d.get("label"), "risk": d.get("risk"),
            "types": d.get("types"), "external": d.get("external"),
            "community": metrics["communities"].get(n, 0),
            "centrality": round(metrics["centrality"].get(n, 0.0), 4),
            "degree": metrics["degree"].get(n, 0),
        })
    edges = []
    for u, v, d in g.edges(data=True):
        edges.append({"source": u, "target": v, "kind": d.get("kind"),
                      "amount": d.get("amount"), "count": d.get("count")})
    return {"nodes": nodes, "edges": edges}
