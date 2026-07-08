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


@st.cache_data(show_spinner="Running fusion pipeline…")
def run_pipeline(input_dir: str, window: int):
    inv = pipeline.run(input_dir, window_minutes=window)
    # return plain structures (cache-friendly) + keep graph payload
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
        "input_dir": input_dir,
        "window": window,
    }


def _dataset_dirs() -> list[str]:
    base = ROOT / "datasets" / "raw"
    return [str(p) for p in sorted(base.glob("*")) if p.is_dir()]


# ----- Sidebar -----
st.sidebar.title("🛡️ ERakshak")
st.sidebar.caption("Bank · CDR · IPDR Fusion Analyzer")

dirs = _dataset_dirs()
choice = st.sidebar.selectbox("Dataset", dirs or ["<none>"],
                              format_func=lambda p: Path(p).name)
window = st.sidebar.slider("Correlation window W (minutes)", 1, 60, 10)
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

data = run_pipeline(choice, window)
S = data["summary"]

st.title("Financial & Telecom Fusion Analyzer")
st.caption(f"Dataset: `{Path(choice).name}` · window W = {window} min")

tabs = st.tabs(["📊 Overview", "🕸️ Network", "🧑 Entities", "⏱️ Timeline",
                "🎯 Correlations", "🔎 Search", "📄 Report"])

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
    c[3].metric("Rejected rows", S["rejects"])

    st.subheader("Top risk entities")
    rows = sorted(data["risk"].values(), key=lambda r: -r["risk_score"])[:15]
    df = pd.DataFrame([{
        "Entity": r["label"], "Risk": r["risk_score"], "Band": r["band"],
        "Flags": ", ".join(sorted({f["rule"] for f in r["rule_flags"]})),
    } for r in rows])
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---- Network ----
with tabs[1]:
    st.plotly_chart(viz.network_figure(data["graph_payload"]), use_container_width=True)
    st.caption("Red edges = money flow · Blue edges = communication · "
               "Node color = risk · Node size = degree")

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
    st.subheader("Search / filter events (FR-15)")
    col = st.columns(4)
    q = col[0].text_input("Entity / IP / phone / narration contains")
    etype = col[1].selectbox("Type", ["ALL", "TRANSACTION", "CALL", "IP_SESSION"])
    min_amt = col[2].number_input("Min amount", value=0.0)
    max_amt = col[3].number_input("Max amount (0=∞)", value=0.0)

    def _match(e):
        if etype != "ALL" and e["event_type"] != etype:
            return False
        amt = e.get("amount") or 0
        if min_amt and amt < min_amt:
            return False
        if max_amt and amt > max_amt:
            return False
        if q:
            blob = f"{data['entities'].get(e.get('entity_id'),{}).get('label','')} " \
                   f"{e.get('attributes')}".lower()
            if q.lower() not in blob:
                return False
        return True

    res = [e for e in data["events"] if _match(e)][:500]
    st.caption(f"{len(res)} events (showing ≤500)")
    st.dataframe(pd.DataFrame([{
        "time": e["timestamp_start"], "type": e["event_type"],
        "entity": data["entities"].get(e.get("entity_id"), {}).get("label"),
        "amount": e.get("amount"), "direction": e.get("direction"),
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
