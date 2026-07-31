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
from . import features as featmod

log = get_logger(__name__)


def _enabled(cfg, name):
    r = cfg.get("rules", {}).get(name, {})
    return r if r.get("enabled", False) else None


def structuring(feats, cfg):
    """Credits clustered just below the reporting threshold, WITHIN `window_hours`.

    `window_hours` was declared in the config and never read: the timestamp was discarded at
    `for (_t, a, asset) in f["credits"]` and every in-band credit in the case counted, however
    far apart. Three ₹9.5-lakh receipts years apart are not smurfing — they are a business that
    deals in large sums. Structuring is a *deliberate split of one sum*, so the burst is the
    signal and the window is what makes it a burst.

    Concentrated the check on the window rather than deleting the key, because the key names
    the right idea: FATF's smurfing typology is about evading a per-report threshold, which is
    assessed per reporting period.
    """
    r = _enabled(cfg, "structuring")
    if not r:
        return []
    thr = r["reporting_threshold_inr"]
    lo = thr * (1 - r["just_below_band_pct"])
    window = timedelta(hours=r.get("window_hours", 24))
    need = r["min_occurrences"]
    flags = []
    for eid, f in feats.items():
        # A3: the reporting threshold is an INR fiat limit — only count INR credits.
        near = sorted(t for (t, a, asset) in f["credits"]
                      if asset == "INR" and t is not None and lo <= a < thr)
        if len(near) < need:
            continue
        best, j = 0, 0
        for i in range(len(near)):
            while near[i] - near[j] > window:
                j += 1
            best = max(best, i - j + 1)
        if best >= need:
            flags.append({"entity_id": eid, "rule": "structuring", "weight": r["weight"],
                          "detail": f"{best} credits in [{lo:.0f}, {thr:.0f}) within "
                                    f"{r.get('window_hours', 24)}h "
                                    f"(just below reporting threshold; "
                                    f"{len(near)} in the band overall)"})
    return flags


def rapid_in_out(feats, cfg):
    """Money credited then forwarded out within this rule's OWN configured hold window.

    `f["max_rapid_forward"]` is a single precomputed scalar and cannot serve two rules that
    configure different windows — `rapid_in_out` asks for 60 minutes, `mule_account` for 120.
    It was computed once at 120 while this rule's flag text printed `max_hold_minutes` (60), so
    every flag stated a window that had not been measured. Measuring per rule costs one pass
    over an entity's own credits and debits and makes the detail true.
    """
    r = _enabled(cfg, "rapid_in_out")
    if not r:
        return []
    hold = r.get("max_hold_minutes", featmod.ML_HOLD_MINUTES)
    flags = []
    for eid, f in feats.items():
        forwarded = featmod.max_rapid_forward(f["credits"], f["debits"], hold)
        if forwarded >= r["min_forwarded_pct"]:
            flags.append({"entity_id": eid, "rule": "rapid_in_out", "weight": r["weight"],
                          "detail": f"{forwarded*100:.0f}% of a credit forwarded "
                                    f"within {hold}min"})
    return flags


def mule_account(feats, cfg):
    r = _enabled(cfg, "mule_account")
    if not r:
        return []
    hold = r.get("max_hold_minutes", featmod.ML_HOLD_MINUTES)
    flags = []
    for eid, f in feats.items():
        if f["fan_in"] < r["min_fan_in"]:
            continue                       # cheap half first; the fan-in gate rejects most
        forwarded = featmod.max_rapid_forward(f["credits"], f["debits"], hold)
        if forwarded >= r["min_forwarded_pct"]:
            # Say when the evidence is counterparty-side. A flag on an account whose own
            # statement we hold and one inferred from someone else's transfers are different
            # strengths of finding, and an analyst has to be able to tell them apart.
            basis = (" (from counterparty-side transfers; this account's own statement is "
                     "not in the case)" if f.get("from_transfers_only") else "")
            flags.append({"entity_id": eid, "rule": "mule_account", "weight": r["weight"],
                          "detail": f"fan-in={f['fan_in']} with "
                                    f"{forwarded*100:.0f}% rapid forwarding within "
                                    f"{hold}min{basis}"})
    return flags


#: Percentile of the case's own INR transfer amounts used to cap the noise floor.
#: Deliberately the median: a filter meant to drop "tiny" transfers must not exclude
#: the typical transfer, whatever scale the case happens to run at.
_NOISE_FLOOR_PERCENTILE = 0.50


def adaptive_amount_floor(transfers, min_amount_inr) -> float:
    """Lower a configured noise floor to fit the case's own scale — never raise it.

    `min_amount_inr` exists to drop benign small hops. It was fixed at ₹10,000, which
    was below the median on the synthetic fixture (₹26,015) but sat at the **p90** of the
    real case (median ₹997): it excluded roughly nine transfers in ten from layering and
    circular-flow detection, so those rules were searching a tenth of the graph.

    Taking the minimum of the configured value and the case median means a case at the
    scale the config assumed is unaffected, while a smaller-scale case is not silently
    filtered away. It can only make detection more sensitive, never less — the safe
    direction for a forensic tool, since the cost of a missed lead outweighs a reviewed
    false one.
    """
    if not min_amount_inr:
        return 0.0
    amounts = sorted(
        float(t["amount"]) for t in transfers
        if t.get("amount") is not None and (t.get("asset") or "INR") == "INR"
    )
    if not amounts:
        return float(min_amount_inr)
    median = amounts[int(len(amounts) * _NOISE_FLOOR_PERCENTILE)]
    return float(min(float(min_amount_inr), median))


def _passes_amount_gate(tr, min_amount_inr) -> bool:
    """D1: drop tiny INR transfers (benign noise) from structural detection; always keep
    non-INR (crypto) edges since their unit amounts aren't comparable to an INR floor."""
    if not min_amount_inr:
        return True
    if (tr.get("asset") or "INR") != "INR":
        return True
    amt = tr.get("amount")
    return amt is None or amt >= min_amount_inr


def _transfer_digraph(transfers, min_amount_inr=0):
    g = nx.DiGraph()
    for tr in transfers:
        if not _passes_amount_gate(tr, min_amount_inr):
            continue
        g.add_edge(tr["from_entity"], tr["to_entity"], amount=tr.get("amount"), time=tr.get("time"))
    return g


def circular_flow(transfers, cfg):
    r = _enabled(cfg, "circular_flow")
    if not r:
        return []
    g = _transfer_digraph(transfers, adaptive_amount_floor(transfers, r.get("min_amount_inr", 0)))
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
    g = _transfer_digraph(transfers, adaptive_amount_floor(transfers, r.get("min_amount_inr", 0)))
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
    """Fires on a call+transfer coincidence, with or without an overlapping IP session.

    Counting STRONG only meant this rule — named for the pair, not the triple — could never
    fire while STRONG was 0, which it is on both real cases: 7,358 eligible entities, 0 fired.

    The two tiers are not equal evidence and are not weighted equally. A MEDIUM hit is the
    same call+transfer pair with no corroborating IP session, so a MEDIUM-only entity carries
    `medium_weight` (default half). Measured on the demo set, firing on MEDIUM at all takes
    this rule's entity-level recall from 0.500 to 1.000 — it catches both ends of the call
    rather than one — at a precision cost of 0.333 -> 0.200, which is the same range as the
    committed `layering` (0.195) and above `rapid_in_out` (0.107).

    Halving is an evidential judgement, not a measured suppression: at the full weight every
    one of the 30 eligible demo entities received an identical +10.5, which carries no ranking
    information. It does NOT change which entities change band — the same three cross into
    medium either way, and all three already held three other typologies.

    The detail states which tier produced the hit, so a MEDIUM coincidence is never read as a
    decisive call+IP+transfer one.
    """
    r = _enabled(cfg, "call_transfer_coincidence")
    if not r:
        return []
    # Default rather than require, so an existing config without the key keeps working —
    # halved, not silently promoted to STRONG strength.
    medium_weight = r.get("medium_weight", r["weight"] / 2)
    out = []
    for eid, f in feats.items():
        strong = f.get("coincidence_count", 0)
        medium = f.get("coincidence_medium_count", 0)
        if not (strong or medium):
            continue
        weight = r["weight"]
        if strong and medium:
            detail = (f"{strong} call+IP+transfer and {medium} call+transfer "
                      f"coincidence(s)")
        elif strong:
            detail = f"{strong} call+IP+transfer coincidence(s)"
        else:
            weight = medium_weight
            detail = (f"{medium} call+transfer coincidence(s) with no overlapping IP "
                      f"session — weaker tier, weighted {medium_weight:g} not "
                      f"{r['weight']:g}")
        out.append({"entity_id": eid, "rule": "call_transfer_coincidence",
                    "weight": weight, "detail": detail})
    return out


def comm_burst(feats, cfg):
    r = _enabled(cfg, "comm_burst")
    if not r:
        return []
    thr = r["max_calls_per_hour"]
    return [{"entity_id": eid, "rule": "comm_burst", "weight": r["weight"],
             "detail": f"{f['max_calls_hour']} calls within one hour (burst)"}
            for eid, f in feats.items() if f.get("max_calls_hour", 0) >= thr]


def dormant_activation(feats, cfg):
    r = _enabled(cfg, "dormant_activation")
    if not r:
        return []
    thr = r["min_dormancy_days"]
    return [{"entity_id": eid, "rule": "dormant_activation", "weight": r["weight"],
             "detail": f"reactivated after {f['max_dormancy_days']:.0f} days dormant"}
            for eid, f in feats.items() if f.get("max_dormancy_days", 0) >= thr]


_RULE_FNS = (
    ("structuring", structuring, "feats"),
    ("rapid_in_out", rapid_in_out, "feats"),
    ("mule_account", mule_account, "feats"),
    ("circular_flow", circular_flow, "transfers"),
    ("layering", layering, "transfers"),
    ("call_transfer_coincidence", call_transfer_coincidence, "feats"),
    ("comm_burst", comm_burst, "feats"),
    ("dormant_activation", dormant_activation, "feats"),
)


def eligibility_report(feats, transfers, cfg) -> list[dict]:
    """Per rule: was it enabled, could it apply here, and did it fire.

    "0 high-risk entities" is read by an investigator as *nothing suspicious in this
    case*. On the real case it actually meant something different for each rule:
    `structuring` had no candidate transaction anywhere near the ₹10 lakh reporting
    threshold (case p99 is ₹100,000), so it could not fire — a legitimate finding, not a
    miss. `layering` was searching a tenth of the transfer graph because its noise floor
    sat at the case's p90.

    A rule that never ran and a rule that ran and found nothing must not look identical.
    This is the audit trail that separates them.
    """
    out = []
    inr = sorted(float(t["amount"]) for t in transfers
                 if t.get("amount") is not None and (t.get("asset") or "INR") == "INR")
    for name, fn, arg in _RULE_FNS:
        r = cfg.get("rules", {}).get(name, {})
        if not r.get("enabled", False):
            out.append({"rule": name, "enabled": False, "eligible": None,
                        "fired": 0, "note": "disabled in config"})
            continue
        fired = len({f["entity_id"] for f in fn(feats if arg == "feats" else transfers, cfg)})
        row = {"rule": name, "enabled": True, "fired": fired, "note": None}
        if name == "structuring" and inr:
            thr = r["reporting_threshold_inr"]
            lo = thr * (1 - r["just_below_band_pct"])
            row["eligible"] = sum(1 for a in inr if lo <= a < thr)
            if row["eligible"] == 0:
                row["note"] = (f"no transaction in [{lo:,.0f}, {thr:,.0f}); case max is "
                               f"{inr[-1]:,.0f} — the typology does not occur here")
        elif name in ("layering", "circular_flow") and inr:
            floor = adaptive_amount_floor(transfers, r.get("min_amount_inr", 0))
            row["eligible"] = sum(1 for a in inr if a >= floor)
            configured = float(r.get("min_amount_inr", 0) or 0)
            if floor < configured:
                row["note"] = (f"noise floor lowered {configured:,.0f} -> {floor:,.0f} "
                               f"to match this case's scale")
        else:
            row["eligible"] = _eligible_count(name, feats, r)
            if row["eligible"] == 0 and row["fired"] == 0:
                row["note"] = _INERT_NOTES.get(name)
        out.append(row)
    return out


#: What each rule's own precondition is, independent of its firing threshold. `len(feats)` was
#: used for these five, which is the entity count and tells an analyst nothing: on
#: `fir-65-2024` `mule_account` reported 9,996 eligible and 0 fired, when the meaningful
#: statement is that only a handful of entities have the fan-in the rule requires at all.
#: Eligibility has to be the structural precondition, or "eligible" is a headcount wearing a
#: diagnosis.
_ELIGIBILITY: dict[str, object] = {
    # fan-in is the structural half of the mule signature; forwarding is the behavioural half
    "mule_account": lambda f, r: f["fan_in"] >= r.get("min_fan_in", 0),
    # forwarding is only observable when money is seen arriving AND leaving
    "rapid_in_out": lambda f, r: bool(f["credits"]) and bool(f["debits"]),
    # a coincidence needs both legs present for the same entity
    "call_transfer_coincidence": lambda f, r: bool(f["call_times"]) and (
        bool(f["txn_times"]) or bool(f["credits"]) or bool(f["debits"])),
    "comm_burst": lambda f, r: bool(f["call_times"]),
    # a dormancy gap needs at least two transactions to measure between
    "dormant_activation": lambda f, r: len(f["txn_times"]) >= 2,
}

#: Said when a rule has no eligible entity at all. This is a finding about the evidence, and
#: it is the sentence that stops `fired=0` reading as "nothing suspicious here".
_INERT_NOTES = {
    "mule_account": "no entity reaches the required fan-in, so the typology's structural "
                    "precondition does not occur in this case",
    "rapid_in_out": "no entity is seen both receiving and sending, so forwarding cannot be "
                    "observed — a one-hop view of the money trail",
    "call_transfer_coincidence": "no entity holds both a call and a transaction, so no "
                                 "coincidence is possible at any window",
    "comm_burst": "no call records are attributed to any entity",
    "dormant_activation": "no entity has two or more transactions to measure a gap between",
}


def _eligible_count(name: str, feats: dict, rule_cfg: dict) -> int:
    """Entities meeting a rule's structural precondition, before its threshold applies."""
    test = _ELIGIBILITY.get(name)
    if test is None:
        return len(feats)
    return sum(1 for f in feats.values() if test(f, rule_cfg))


def run_all(feats, transfers, cfg):
    flags = []
    for _name, fn, arg in _RULE_FNS:
        flags += fn(feats if arg == "feats" else transfers, cfg)
    return flags
