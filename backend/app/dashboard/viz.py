"""Plotly figures for the dashboard: unified timeline and investigation network (FR-14, NFR-4)."""

from __future__ import annotations

import networkx as nx
import plotly.graph_objects as go

EVENT_COLOR = {"TRANSACTION": "#d62728", "CALL": "#1f77b4", "IP_SESSION": "#2ca02c"}
EVENT_ROW = {"TRANSACTION": 3, "CALL": 2, "IP_SESSION": 1}


def timeline_figure(events: list[dict], label: str = "", max_points: int = 1500) -> go.Figure:
    fig = go.Figure()
    for etype in ("TRANSACTION", "CALL", "IP_SESSION"):
        evs = [e for e in events if e["event_type"] == etype]
        if not evs:
            continue
        # E5: downsample very dense series so the chart stays responsive
        if len(evs) > max_points:
            step = len(evs) // max_points + 1
            evs = sorted(evs, key=lambda e: e["timestamp_start"])[::step]
            etype_label = f"{etype} (sampled)"
        else:
            etype_label = etype
        xs = [e["timestamp_start"] for e in evs]
        ys = [EVENT_ROW[etype]] * len(evs)
        texts = [_event_hover(e) for e in evs]
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="markers", name=etype_label,
            marker=dict(size=11, color=EVENT_COLOR[etype], line=dict(width=1, color="white")),
            text=texts, hoverinfo="text",
        ))
    fig.update_yaxes(tickvals=[1, 2, 3], ticktext=["IP session", "Call", "Transaction"],
                     range=[0.5, 3.5])
    fig.update_layout(title=f"Unified timeline — {label}", height=380,
                      margin=dict(l=10, r=10, t=40, b=10), legend_orientation="h")
    return fig


def _event_hover(e: dict) -> str:
    a = e.get("attributes") or {}
    t = e["timestamp_start"].strftime("%Y-%m-%d %H:%M:%S")
    if e["event_type"] == "TRANSACTION":
        return f"{t}<br>{e.get('direction')} {e.get('amount')}<br>{a.get('narration','')}"
    if e["event_type"] == "CALL":
        return f"{t}<br>call {e.get('direction')}<br>dur {a.get('duration')}s<br>{a.get('location','')}"
    return f"{t}<br>IP {a.get('public_ip')}<br>end {e.get('timestamp_end')}"


def network_figure(payload: dict, max_nodes: int = 200) -> go.Figure:
    nodes = payload["nodes"]
    edges = payload["edges"]
    # For very large graphs, keep the highest-degree nodes
    if len(nodes) > max_nodes:
        keep = {n["id"] for n in sorted(nodes, key=lambda x: -(x.get("degree") or 0))[:max_nodes]}
        nodes = [n for n in nodes if n["id"] in keep]
        edges = [e for e in edges if e["source"] in keep and e["target"] in keep]

    g = nx.DiGraph()
    for n in nodes:
        g.add_node(n["id"])
    for e in edges:
        g.add_edge(e["source"], e["target"])
    pos = nx.spring_layout(g, seed=42, k=0.6)

    edge_traces = []
    for kind, color in (("MONEY_FLOW", "#d62728"), ("COMMUNICATION", "#1f77b4")):
        ex, ey = [], []
        for e in edges:
            if e["kind"] != kind or e["source"] not in pos or e["target"] not in pos:
                continue
            x0, y0 = pos[e["source"]]
            x1, y1 = pos[e["target"]]
            ex += [x0, x1, None]
            ey += [y0, y1, None]
        edge_traces.append(go.Scatter(x=ex, y=ey, mode="lines", name=kind,
                                      line=dict(width=0.8, color=color), hoverinfo="none",
                                      opacity=0.5))

    nx_, ny_, colors, texts, sizes = [], [], [], [], []
    for n in nodes:
        if n["id"] not in pos:
            continue
        x, y = pos[n["id"]]
        nx_.append(x)
        ny_.append(y)
        risk = n.get("risk") or 0
        colors.append(risk)
        sizes.append(10 + (n.get("degree") or 0) * 0.6)
        texts.append(f"{n.get('label')}<br>risk {risk}<br>types {n.get('types')}"
                     f"<br>degree {n.get('degree')}")
    node_trace = go.Scatter(
        x=nx_, y=ny_, mode="markers", name="entity", text=texts, hoverinfo="text",
        marker=dict(size=sizes, color=colors, colorscale="YlOrRd", cmin=0, cmax=100,
                    showscale=True, colorbar=dict(title="Risk"), line=dict(width=1, color="#333")),
    )
    fig = go.Figure(data=[*edge_traces, node_trace])
    fig.update_layout(title="Investigation network (money-flow + communication)",
                      showlegend=True, height=600, margin=dict(l=10, r=10, t=40, b=10),
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig
