"""Rule-based detectors (FR-11). Configurable, explainable — each flag cites its reason.

Every rule returns flags: {entity_id, rule, weight, detail}. Thresholds come from
config/scoring_rules.yaml (NFR-6); nothing is hard-coded.
"""

from __future__ import annotations

import time
from datetime import timedelta

import networkx as nx

from ..core import config
from ..core.logging_config import get_logger

log = get_logger(__name__)


def _enabled(cfg, name):
    r = cfg.get("rules", {}).get(name, {})
    return r if r.get("enabled", False) else None


def structuring(feats, cfg):
    r = _enabled(cfg, "structuring")
    if not r:
        return []
    thr = r["reporting_threshold_inr"]
    lo = thr * (1 - r["just_below_band_pct"])
    flags = []
    for eid, f in feats.items():
        near = [a for (_t, a) in f["credits"] if lo <= a < thr]
        if len(near) >= r["min_occurrences"]:
            flags.append({"entity_id": eid, "rule": "structuring", "weight": r["weight"],
                          "detail": f"{len(near)} credits in [{lo:.0f}, {thr:.0f}) "
                                    f"(just below reporting threshold)"})
    return flags


def rapid_in_out(feats, cfg):
    r = _enabled(cfg, "rapid_in_out")
    if not r:
        return []
    flags = []
    for eid, f in feats.items():
        if f["max_rapid_forward"] >= r["min_forwarded_pct"]:
            flags.append({"entity_id": eid, "rule": "rapid_in_out", "weight": r["weight"],
                          "detail": f"{f['max_rapid_forward']*100:.0f}% of a credit forwarded "
                                    f"within {r['max_hold_minutes']}min"})
    return flags


def mule_account(feats, cfg):
    r = _enabled(cfg, "mule_account")
    if not r:
        return []
    flags = []
    for eid, f in feats.items():
        if f["fan_in"] >= r["min_fan_in"] and f["max_rapid_forward"] >= r["min_forwarded_pct"]:
            flags.append({"entity_id": eid, "rule": "mule_account", "weight": r["weight"],
                          "detail": f"fan-in={f['fan_in']} with "
                                    f"{f['max_rapid_forward']*100:.0f}% rapid forwarding"})
    return flags


def _transfer_digraph(transfers):
    g = nx.DiGraph()
    for tr in transfers:
        g.add_edge(tr["from_entity"], tr["to_entity"], amount=tr.get("amount"), time=tr.get("time"))
    return g


def circular_flow(transfers, cfg):
    r = _enabled(cfg, "circular_flow")
    if not r:
        return []
    g = _transfer_digraph(transfers)
    limits = config.graph_limits()
    # review fix C4: bound worst-case-exponential cycle enumeration by count AND time.
    try:
        gen = nx.simple_cycles(g, length_bound=r["max_cycle_length"])
    except TypeError:  # older networkx without length_bound
        gen = (c for c in nx.simple_cycles(g) if len(c) <= r["max_cycle_length"])
    cycles = []
    t0 = time.monotonic()
    for c in gen:
        cycles.append(c)
        if len(cycles) >= limits["max_cycles"] or \
                (time.monotonic() - t0) > limits["max_cycle_seconds"]:
            log.warning("circular_flow: cycle enumeration capped at %d cycles / %.1fs "
                        "(graph too dense) — results partial", len(cycles),
                        limits["max_cycle_seconds"])
            break
    # one flag per entity, recording how many cycles it participates in
    count: dict[str, int] = {}
    shortest: dict[str, int] = {}
    for cyc in cycles:
        if len(cyc) < 2:
            continue
        for eid in cyc:
            count[eid] = count.get(eid, 0) + 1
            shortest[eid] = min(shortest.get(eid, 99), len(cyc))
    return [{"entity_id": eid, "rule": "circular_flow", "weight": r["weight"],
             "detail": f"in {n} money cycle(s), shortest length {shortest[eid]}"}
            for eid, n in count.items()]


def layering(transfers, cfg):
    r = _enabled(cfg, "layering")
    if not r:
        return []
    g = _transfer_digraph(transfers)
    span = timedelta(hours=r["max_span_hours"])
    min_hops = r["min_hops"]
    flagged = set()
    # review fix C4: bound DFS exploration so a dense graph cannot blow up.
    limits = config.graph_limits()
    budget = [limits["max_layering_paths"]]

    def dfs(node, path, start_time):
        if budget[0] <= 0:
            return
        if len(path) - 1 >= min_hops:
            flagged.update(path)
            return
        for succ in g.successors(node):
            if succ in path:
                continue
            budget[0] -= 1
            if budget[0] <= 0:
                return
            t = g[node][succ].get("time")
            st = start_time if start_time is not None else t
            if t is None or st is None or (t - st) <= span:
                dfs(succ, path + [succ], st)

    for n in g.nodes:
        if budget[0] <= 0:
            log.warning("layering: DFS path budget exhausted (%d) — results partial",
                        limits["max_layering_paths"])
            break
        dfs(n, [n], None)

    return [{"entity_id": eid, "rule": "layering", "weight": r["weight"],
             "detail": f"part of a {min_hops}+ hop transfer chain"} for eid in flagged]


def call_transfer_coincidence(feats, cfg):
    r = _enabled(cfg, "call_transfer_coincidence")
    if not r:
        return []
    return [{"entity_id": eid, "rule": "call_transfer_coincidence", "weight": r["weight"],
             "detail": f"{f['coincidence_count']} call+IP+transfer coincidence(s)"}
            for eid, f in feats.items() if f["coincidence_count"] > 0]


def run_all(feats, transfers, cfg):
    flags = []
    flags += structuring(feats, cfg)
    flags += rapid_in_out(feats, cfg)
    flags += mule_account(feats, cfg)
    flags += circular_flow(transfers, cfg)
    flags += layering(transfers, cfg)
    flags += call_transfer_coincidence(feats, cfg)
    return flags
