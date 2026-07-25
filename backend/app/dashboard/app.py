"""ERakshak investigator dashboard (Streamlit — Phase 6, FR-14/15, NFR-4).

Run from repo root:
    ./.venv/bin/streamlit run backend/app/dashboard/app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure repo root on path when launched by streamlit
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from backend.app import pipeline
from backend.app.api.security import authenticate_user
from backend.app.core import config
from backend.app.core.logging_config import audit
from backend.app.dashboard import viz
from backend.app.reporting import service as reporting

st.set_page_config(page_title="ERakshak — Fusion Analyzer", layout="wide", page_icon="🛡️")


# ---- Auth gate (review fix C2/H2): no access to sensitive PII without login ----
def _login_gate():
    if st.session_state.get("user"):
        return
    st.title("🛡️ ERakshak — Sign in")
    st.caption("Investigator access only. Handles sensitive financial & telecom data.")
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in"):
            user = authenticate_user(u, p)
            if user:
                st.session_state["user"] = user
                audit("dashboard_login_ok", user=u)
                st.rerun()
            else:
                audit("dashboard_login_failed", user=u)
                st.error("Invalid credentials")
    st.stop()


_login_gate()


@st.cache_resource(show_spinner="Parsing & fusing dataset…")
def _base(input_dir: str, include_pdf: bool):
    # G2: cache the expensive window-INDEPENDENT prefix; only correlation/detection re-run.
    return pipeline.run_base(input_dir, include_pdf=include_pdf)


@st.cache_data(show_spinner="Correlating & scoring…")
def run_pipeline(input_dir: str, window: int, include_pdf: bool = False):
    inv = _base(input_dir, include_pdf)
    pipeline.apply_analysis(inv, window_minutes=window)
    return {
        "summary": inv.summary(),
        "events": inv.events,
        "entities": inv.entities,
        "node_to_entity": inv.node_to_entity,
        "timeline": inv.timeline,
        "correlation_hits": inv.correlation_hits,
        "transfers": inv.transfers,
        "risk": inv.risk,
        "graph_payload": inv.graph["payload"],
        "metrics": inv.graph["metrics"],
        "reject_report": inv.reject_report(),
        "data_quality": inv.data_quality,
        "parsed_files": [pf.summary for pf in inv.parsed_files],
        "input_dir": input_dir,
        "window": window,
    }


def _dataset_dirs() -> list[str]:
    """Synthetic datasets under datasets/raw/* plus real case folders directly in datasets/."""
    dirs = []
    raw = ROOT / "datasets" / "raw"
    if raw.exists():
        dirs += [p for p in sorted(raw.glob("*")) if p.is_dir()]
    ds = ROOT / "datasets"
    if ds.exists():
        skip = {"raw", "processed", "intermediate", "external", "metadata"}
        dirs += [p for p in sorted(ds.glob("*")) if p.is_dir() and p.name not in skip]
    return [str(p) for p in dirs]


# ----- Sidebar -----
st.sidebar.title("🛡️ ERakshak")
st.sidebar.caption("Bank · CDR · IPDR Fusion Analyzer")

dirs = _dataset_dirs()
choice = st.sidebar.selectbox("Dataset", dirs or ["<none>"],
                              format_func=lambda p: Path(p).name)
window = st.sidebar.slider("Correlation window W (minutes)", 1, 60, 10)
include_pdf = st.sidebar.checkbox("Parse PDFs (slow on real cases)", value=False)
upload = st.sidebar.file_uploader("…or upload files (bank/cdr/ipdr)",
                                  accept_multiple_files=True)

if upload:
    # review fix H2: sanitize filename (no path traversal), validate extension/size/count
    lim = config.upload_limits()
    up_dir = ROOT / "data" / "uploads" / "session"
    up_dir.mkdir(parents=True, exist_ok=True)
    if len(upload) > lim["max_files"]:
        st.sidebar.error(f"Too many files (max {lim['max_files']})")
        st.stop()
    saved = 0
    for f in upload:
        safe_name = os.path.basename(f.name)          # strip any ../ path components
        ext = os.path.splitext(safe_name)[1].lower()
        buf = f.getbuffer()
        if ext not in lim["allowed_extensions"]:
            st.sidebar.warning(f"Skipped {safe_name}: extension not allowed")
            continue
        if len(buf) > lim["max_file_mb"] * 1024 * 1024:
            st.sidebar.warning(f"Skipped {safe_name}: exceeds {lim['max_file_mb']}MB")
            continue
        dest = (up_dir / safe_name).resolve()
        if up_dir.resolve() not in dest.parents:       # defense-in-depth
            st.sidebar.warning(f"Skipped {safe_name}: invalid path")
            continue
        dest.write_bytes(buf)
        saved += 1
    choice = str(up_dir)
    audit("dashboard_upload", user=st.session_state["user"]["username"], files=saved)
    st.sidebar.success(f"Uploaded {saved} file(s)")

if not choice or choice == "<none>":
    st.info("Select or upload a dataset to begin.")
    st.stop()

data = run_pipeline(choice, window, include_pdf)
S = data["summary"]

st.title("Financial & Telecom Fusion Analyzer")
st.caption(f"Dataset: `{Path(choice).name}` · window W = {window} min")

tabs = st.tabs(["📊 Overview", "🕸️ Network", "🧑 Entities", "⏱️ Timeline",
                "🎯 Correlations", "🔎 Search", "📄 Report", "🔥 Heat map", "🗣️ Ask",
                "🧪 Quality", "🛠 Mapping"])

# ---- Overview ----
with tabs[0]:
    c = st.columns(5)
    c[0].metric("Files", S["files"])
    c[1].metric("Events", S["events"])
    c[2].metric("Entities", S["entities"])
    c[3].metric("Correlation hits", S["correlation_hits"])
    c[4].metric("High-risk", S["high_risk_entities"])
    c = st.columns(4)
    c[0].metric("Transactions", S["transactions"])
    c[1].metric("Calls", S["calls"])
    c[2].metric("IP sessions", S["ip_sessions"])
    c[3].metric("Rejected rows", S["rejected_rows"])

    st.subheader("Top risk entities")
    rows = sorted(data["risk"].values(), key=lambda r: -r["risk_score"])[:15]
    df = pd.DataFrame([{
        "Entity": r["label"], "Risk": r["risk_score"], "Band": r["band"],
        "Flags": ", ".join(sorted({f["rule"] for f in r["rule_flags"]})),
    } for r in rows])
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---- Network ----
with tabs[1]:
    payload = data["graph_payload"]
    nodes = payload["nodes"]
    c1, c2, c3 = st.columns(3)
    min_risk = c1.slider("Min risk", 0, 100, 0)
    min_deg = c2.slider("Min degree", 0, 20, 0)
    focus_opts = ["(whole graph)"] + [n["id"] for n in
                                      sorted(nodes, key=lambda x: -(x.get("risk") or 0))[:100]]
    focus = c3.selectbox("Focus entity (1-hop)", focus_opts,
                         format_func=lambda i: i if i == "(whole graph)"
                         else (data["entities"].get(i, {}).get("label") or i))

    # E4: server-side subgraph — threshold + optional ego graph around one entity
    keep = {n["id"] for n in nodes
            if (n.get("risk") or 0) >= min_risk and (n.get("degree") or 0) >= min_deg}
    edges = payload["edges"]
    if focus != "(whole graph)":
        nbrs = {focus} | {e["target"] for e in edges if e["source"] == focus} \
            | {e["source"] for e in edges if e["target"] == focus}
        keep &= nbrs if keep else nbrs
        keep.add(focus)
    sub = {"nodes": [n for n in nodes if n["id"] in keep],
           "edges": [e for e in edges if e["source"] in keep and e["target"] in keep]}
    st.caption(f"Showing {len(sub['nodes'])} / {len(nodes)} entities · "
               "red = money flow, blue = communication · colour = risk, size = degree")
    if sub["nodes"]:
        st.plotly_chart(viz.network_figure(sub), use_container_width=True)
    else:
        st.info("No entities match the filter.")

# ---- Entities ----
with tabs[2]:
    core = {k: v for k, v in data["entities"].items() if not v.get("external")}
    df = pd.DataFrame([{
        "Entity": v["label"], "id": k,
        "Risk": (data["risk"].get(k, {}) or {}).get("risk_score", 0),
        "Band": (data["risk"].get(k, {}) or {}).get("band", "low"),
        "Types": ", ".join(sorted(v.get("types", []))),
        "Identifiers": len(v.get("identifiers", [])),
    } for k, v in core.items()]).sort_values("Risk", ascending=False)
    st.dataframe(df, use_container_width=True, hide_index=True)

    sel = st.selectbox("Drill into entity", df["id"],
                       format_func=lambda i: data["entities"][i]["label"])
    if sel:
        r = data["risk"].get(sel, {})
        st.markdown(f"### {data['entities'][sel]['label']} — risk **{r.get('risk_score')}** "
                    f"({r.get('band')})")
        st.write("**Identifiers:**",
                 ", ".join(f"{t}:{v}" for t, v in sorted(data["entities"][sel]["identifiers"])))
        if r.get("rule_flags"):
            st.write("**Why flagged:**")
            for f in r["rule_flags"]:
                st.markdown(f"- **{f['rule']}** — {f['detail']}")

# ---- Timeline ----
with tabs[3]:
    core = {k: v for k, v in data["entities"].items() if not v.get("external")}
    order = sorted(core, key=lambda k: -(data["risk"].get(k, {}) or {}).get("risk_score", 0))
    sel = st.selectbox("Entity", order, format_func=lambda i: core[i]["label"], key="tl")
    evs = data["timeline"].get(sel, [])
    if evs:
        st.plotly_chart(viz.timeline_figure(evs, core[sel]["label"]), use_container_width=True)
    else:
        st.info("No events for this entity.")

# ---- Correlations ----
with tabs[4]:
    st.subheader(f"Call + IP + transfer coincidences (within {window} min)")
    hits = data["correlation_hits"]
    if not hits:
        st.info("No coincidences at this window.")
    for h in sorted(hits, key=lambda x: -(x["transaction"].get("amount") or 0)):
        with st.expander(f"{h['entity_label']} — ₹{h['transaction'].get('amount')} "
                         f"@ {h['transaction']['time']}"):
            st.write(h["explanation"])
            st.json({"transaction": h["transaction"], "call": h["call"],
                     "ip_session": h["ip_session"]}, expanded=False)

# ---- Search ----
with tabs[5]:
    st.subheader("Search / filter events by entity, amount, time & location (FR-15)")
    col = st.columns(3)
    q = col[0].text_input("Entity / IP / phone / narration contains")
    etype = col[1].selectbox("Type", ["ALL", "TRANSACTION", "CALL", "IP_SESSION"])
    loc = col[2].text_input("Location / cell-tower contains")
    col2 = st.columns(4)
    min_amt = col2[0].number_input("Min amount", value=0.0)
    max_amt = col2[1].number_input("Max amount (0=∞)", value=0.0)
    date_from = col2[2].text_input("From (YYYY-MM-DD)")
    date_to = col2[3].text_input("To (YYYY-MM-DD)")

    def _match(e):
        if etype != "ALL" and e["event_type"] != etype:
            return False
        amt = e.get("amount") or 0
        if min_amt and amt < min_amt:
            return False
        if max_amt and amt > max_amt:
            return False
        ts = e.get("timestamp_start")
        if date_from and ts and str(ts)[:10] < date_from:
            return False
        if date_to and ts and str(ts)[:10] > date_to:
            return False
        attrs = e.get("attributes") or {}
        if loc:
            locblob = f"{attrs.get('location','')} {attrs.get('cell_id','')}".lower()
            if loc.lower() not in locblob:
                return False
        if q:
            blob = f"{data['entities'].get(e.get('entity_id'),{}).get('label','')} {attrs}".lower()
            if q.lower() not in blob:
                return False
        return True

    res = [e for e in data["events"] if _match(e)][:500]
    st.caption(f"{len(res)} events (showing ≤500)")
    st.dataframe(pd.DataFrame([{
        "time": e["timestamp_start"], "type": e["event_type"],
        "entity": data["entities"].get(e.get("entity_id"), {}).get("label"),
        "amount": e.get("amount"), "direction": e.get("direction"),
        "location": (e.get("attributes") or {}).get("location"),
        "detail": str(e.get("attributes"))[:80],
    } for e in res]), use_container_width=True, hide_index=True)

# ---- Report ----
with tabs[6]:
    st.subheader("Forensic report export (FR-16)")
    st.write("Generate an investigation-ready report with the risk summary, correlation "
             "evidence, and money-flow findings.")
    fmt = st.radio("Format", ["PDF", "Word (docx)"], horizontal=True)
    if st.button("Generate report"):
        out_dir = ROOT / "data" / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = reporting.generate(data, out_dir, fmt="pdf" if fmt == "PDF" else "docx")
        with open(path, "rb") as fh:
            st.download_button("Download report", fh.read(), file_name=os.path.basename(path))
        st.success(f"Report written to {path}")

# ---- Heat map (F3) ----
with tabs[7]:
    st.subheader("Risk heat map — entities × typologies (FR-18)")
    import plotly.graph_objects as go
    top = sorted(data["risk"].values(), key=lambda r: -r["risk_score"])[:20]
    top = [r for r in top if r["rule_flags"]]
    rule_set = sorted({f["rule"] for r in top for f in r["rule_flags"]})
    if top and rule_set:
        z, ylabels = [], []
        for r in top:
            wt = {f["rule"]: f["weight"] for f in r["rule_flags"]}
            z.append([round(wt.get(rule, 0) * 100, 1) for rule in rule_set])
            ylabels.append(str(r["label"])[:22])
        fig = go.Figure(go.Heatmap(z=z, x=rule_set, y=ylabels, colorscale="Reds",
                                   colorbar=dict(title="rule wt")))
        fig.update_layout(height=520, margin=dict(l=10, r=10, t=30, b=10),
                          title="Which typologies drive each high-risk entity")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No flagged entities to chart.")

# ---- Ask / NL query (F1) ----
with tabs[8]:
    st.subheader("Natural-language query (rule-based)")
    st.caption("Examples: 'transfers over 100000', 'calls to 9099102222', "
               "'events on 2024-08-01', 'high risk entities'")
    nlq = st.text_input("Ask")
    if nlq:
        from backend.app.search import nl_query
        answer = nl_query.answer(nlq, data)
        st.write(answer["explanation"])
        if answer.get("rows") is not None:
            st.dataframe(pd.DataFrame(answer["rows"]), use_container_width=True, hide_index=True)

# ---- Quality: rejects (B3), balance breaks (A5), fuzzy suggestions (C3) ----
with tabs[9]:
    st.subheader("Data quality & review")
    st.markdown("**Ingestion rejects (per file / reason)**")
    rr = data.get("reject_report", [])
    if rr:
        st.dataframe(pd.DataFrame(rr), use_container_width=True, hide_index=True)
    else:
        st.caption("No rejects.")

    st.markdown("**Bank ledger consistency (A5)** — accounts whose running balance doesn't reconcile")
    dq = data.get("data_quality", [])
    if dq:
        st.dataframe(pd.DataFrame(dq), use_container_width=True, hide_index=True)
    else:
        st.caption("No balance inconsistencies detected (or no balances present).")

    st.markdown("**Possible same-entity pairs (C3, review-only — not merged)**")
    from backend.app.entity_resolution import suggestions
    sugg = suggestions.suggest(data["entities"])
    if sugg:
        st.dataframe(pd.DataFrame(sugg), use_container_width=True, hide_index=True)
        st.caption("Confirm manually, then add an entity_map.csv row to merge authoritatively.")
    else:
        st.caption("No fuzzy link suggestions above threshold.")

# ---- Mapping: manual column mapping for low-confidence files (B5) ----
with tabs[10]:
    st.subheader("Manual column mapping (B5)")
    st.caption("Map an unrecognized file's columns to canonical fields; saves a profile so it "
               "auto-detects next run.")
    from backend.app.ingestion import mapping_writer
    pend = [p for p in data.get("parsed_files", [])
            if p.get("needs_manual_mapping") or not p.get("source_type")]
    if not pend:
        st.success("No files need manual mapping.")
    else:
        names = [p["file"] for p in pend]
        sel = st.selectbox("File", names)
        pf = next(p for p in pend if p["file"] == sel)
        st.write("Detected columns:", pf.get("headers"))
        src = st.selectbox("Source type", list(mapping_writer.CANONICAL_TARGETS))
        cols = ["(none)"] + list(pf.get("headers") or [])
        aliases: dict = {}
        for tgt in mapping_writer.CANONICAL_TARGETS[src]:
            pick = st.selectbox(f"→ {tgt}", cols, key=f"map_{tgt}")
            if pick != "(none)":
                aliases.setdefault(tgt, []).append(pick)
        req = st.text_input("required_any (comma-separated header that identifies this layout)",
                            value=(pf.get("headers") or [""])[0])
        pid = st.text_input("Profile id", value=f"custom_{src.lower()}")
        if st.button("Save mapping profile"):
            path = mapping_writer.save_profile(pid, src, "TRANSACTION" if src in ("BANK", "CRYPTO")
                                               else ("CALL" if src == "CDR" else "IP_SESSION"),
                                               aliases, [c.strip() for c in req.split(",") if c.strip()])
            st.success(f"Saved {path}. Clear cache / re-run to apply.")
            run_pipeline.clear()
            _base.clear()
