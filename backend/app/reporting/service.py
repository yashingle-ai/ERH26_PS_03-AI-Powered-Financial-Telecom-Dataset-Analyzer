"""Forensic reporting (Phase 7, FR-16/17).

Generates an investigation-ready report (PDF via reportlab, Word via python-docx) with:
executive summary, top risk entities + reasons, correlation evidence (with provenance),
money-flow findings, and an optional Suspicious Transaction Report (STR) section.

Every finding carries provenance / references so the output is evidentiary (NFR-7).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def _stamp() -> str:
    # Wall-clock is fine here (report generation, not part of the deterministic pipeline).
    return datetime.now(IST).strftime("%Y%m%d_%H%M%S")


def _top_entities(data, n=15):
    return sorted(data["risk"].values(), key=lambda r: -r["risk_score"])[:n]


def _top_transfers(data, n=15):
    return sorted(data["transfers"], key=lambda t: -(t.get("amount") or 0))[:n]


def _build_charts(data, out_dir) -> list[tuple[str, str]]:
    """E2: render charts (risk bars, activity timeline) as PNGs for the report."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    charts = []
    stamp = _stamp()

    # 1. Top risk entities bar
    top = [r for r in _top_entities(data, 10) if r["risk_score"] > 0]
    if top:
        fig, ax = plt.subplots(figsize=(7, 3.2))
        labels = [str(r["label"])[:18] for r in top][::-1]
        vals = [r["risk_score"] for r in top][::-1]
        ax.barh(labels, vals, color="#c0392b")
        ax.set_xlabel("Risk score")
        ax.set_title("Top risk entities")
        fig.tight_layout()
        p = os.path.join(out_dir, f"chart_risk_{stamp}.png")
        fig.savefig(p, dpi=120)
        plt.close(fig)
        charts.append(("Top risk entities", p))

    # 2. Activity-over-time timeline (events per day by type)
    from collections import defaultdict
    by_day = defaultdict(lambda: defaultdict(int))
    for e in data.get("events", []):
        ts = e.get("timestamp_start")
        if ts:
            by_day[str(ts)[:10]][e["event_type"]] += 1
    if by_day:
        days = sorted(by_day)[:120]
        fig, ax = plt.subplots(figsize=(7, 3.0))
        for et, color in (("TRANSACTION", "#d62728"), ("CALL", "#1f77b4"),
                          ("IP_SESSION", "#2ca02c")):
            ax.plot(days, [by_day[d].get(et, 0) for d in days], label=et, color=color)
        ax.set_title("Activity over time")
        ax.legend(fontsize=7)
        ax.set_xticks(days[:: max(1, len(days) // 8)])
        ax.tick_params(axis="x", labelrotation=45, labelsize=6)
        fig.tight_layout()
        p = os.path.join(out_dir, f"chart_timeline_{stamp}.png")
        fig.savefig(p, dpi=120)
        plt.close(fig)
        charts.append(("Activity over time", p))

    return charts


def generate(data: dict, out_dir: str, fmt: str = "pdf") -> str:
    os.makedirs(out_dir, exist_ok=True)
    if fmt == "docx":
        return _generate_docx(data, out_dir)
    return _generate_pdf(data, out_dir)


# --------------------------------------------------------------------------- PDF
def _generate_pdf(data, out_dir) -> str:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    path = os.path.join(out_dir, f"forensic_report_{_stamp()}.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm)
    styles = getSampleStyleSheet()
    S = data["summary"]
    story = []

    story.append(Paragraph("ERakshak — Forensic Investigation Report", styles["Title"]))
    story.append(Paragraph("AI-Powered Financial &amp; Telecom Dataset Analyzer "
                           "(Bank · CDR · IPDR Fusion)", styles["Normal"]))
    story.append(Paragraph(f"Generated: {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')} · "
                           f"Dataset: {os.path.basename(data['input_dir'])} · "
                           f"Window W = {data['window']} min", styles["Normal"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("1. Executive Summary", styles["Heading2"]))
    summ = [["Files", S["files"]], ["Events", S["events"]],
            ["Transactions / Calls / IP sessions",
             f"{S['transactions']} / {S['calls']} / {S['ip_sessions']}"],
            ["Resolved entities", S["entities"]],
            ["Correlation coincidences", S["correlation_hits"]],
            ["High-risk entities", S["high_risk_entities"]],
            ["Rejected rows", S["rejected_rows"]]]
    story.append(_pdf_table(summ, Table, TableStyle, colors, header=False))
    story.append(Spacer(1, 10))

    # E2: charts
    for title, img in _build_charts(data, out_dir):
        story.append(Paragraph(title, styles["Heading3"]))
        story.append(Image(img, width=170 * mm, height=70 * mm))
        story.append(Spacer(1, 8))

    story.append(Paragraph("2. Top Risk Entities", styles["Heading2"]))
    rows = [["Entity", "Risk", "Band", "Reasons"]]
    for r in _top_entities(data):
        rows.append([str(r["label"])[:28], r["risk_score"], r["band"],
                     ", ".join(sorted({f["rule"] for f in r["rule_flags"]}))[:60]])
    story.append(_pdf_table(rows, Table, TableStyle, colors))
    story.append(Spacer(1, 10))

    story.append(Paragraph("3. Cross-Dataset Correlation Evidence", styles["Heading2"]))
    if not data["correlation_hits"]:
        story.append(Paragraph("No call+IP+transfer coincidences at the current window.",
                               styles["Normal"]))
    for h in sorted(data["correlation_hits"],
                    key=lambda x: -(x["transaction"].get("amount") or 0))[:12]:
        story.append(Paragraph(f"• <b>{h['entity_label']}</b>: {h['explanation']}",
                               styles["Normal"]))
        prov = h["transaction"].get("provenance", {})
        story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;<i>Evidence: ref {h['transaction'].get('ref_no')} · "
                               f"source {prov.get('source_file')} row {prov.get('row')}</i>",
                               styles["Normal"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("4. Money-Flow Findings (largest transfers)", styles["Heading2"]))
    rows = [["From", "To", "Amount", "Ref"]]
    for t in _top_transfers(data):
        rows.append([_label(data, t["from_entity"])[:22], _label(data, t["to_entity"])[:22],
                     t.get("amount"), t.get("ref")])
    story.append(_pdf_table(rows, Table, TableStyle, colors))
    story.append(Spacer(1, 10))

    story.append(Paragraph("5. Suspicious Transaction Report (STR) — Draft", styles["Heading2"]))
    for line in _str_lines(data):
        story.append(Paragraph(line, styles["Normal"]))

    story.append(Spacer(1, 12))
    story.append(Paragraph("<i>Generated by ERakshak. Findings are investigative leads derived "
                           "from the supplied data and require analyst verification.</i>",
                           styles["Italic"]))
    doc.build(story)
    return path


def _pdf_table(rows, Table, TableStyle, colors, header=True):
    t = Table([[str(c) for c in r] for r in rows], repeatRows=1 if header else 0)
    style = [("FONTSIZE", (0, 0), (-1, -1), 8),
             ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
             ("VALIGN", (0, 0), (-1, -1), "TOP")]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    t.setStyle(TableStyle(style))
    return t


# -------------------------------------------------------------------------- DOCX
def _generate_docx(data, out_dir) -> str:
    from docx import Document

    path = os.path.join(out_dir, f"forensic_report_{_stamp()}.docx")
    doc = Document()
    S = data["summary"]
    doc.add_heading("ERakshak — Forensic Investigation Report", 0)
    doc.add_paragraph("AI-Powered Financial & Telecom Dataset Analyzer (Bank · CDR · IPDR Fusion)")
    doc.add_paragraph(f"Generated: {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')} · "
                      f"Dataset: {os.path.basename(data['input_dir'])} · Window W = {data['window']} min")

    doc.add_heading("1. Executive Summary", 1)
    for k, v in [("Files", S["files"]), ("Events", S["events"]),
                 ("Transactions/Calls/IP", f"{S['transactions']}/{S['calls']}/{S['ip_sessions']}"),
                 ("Entities", S["entities"]), ("Correlation hits", S["correlation_hits"]),
                 ("High-risk entities", S["high_risk_entities"]), ("Rejected rows", S["rejected_rows"])]:
        doc.add_paragraph(f"{k}: {v}", style="List Bullet")

    # E2: charts
    from docx.shared import Inches
    for title, img in _build_charts(data, out_dir):
        doc.add_heading(title, 3)
        doc.add_picture(img, width=Inches(6.2))

    doc.add_heading("2. Top Risk Entities", 1)
    tbl = doc.add_table(rows=1, cols=4)
    tbl.style = "Light Grid Accent 1"
    for i, h in enumerate(["Entity", "Risk", "Band", "Reasons"]):
        tbl.rows[0].cells[i].text = h
    for r in _top_entities(data):
        c = tbl.add_row().cells
        c[0].text = str(r["label"])
        c[1].text = str(r["risk_score"])
        c[2].text = r["band"]
        c[3].text = ", ".join(sorted({f["rule"] for f in r["rule_flags"]}))

    doc.add_heading("3. Cross-Dataset Correlation Evidence", 1)
    if not data["correlation_hits"]:
        doc.add_paragraph("No call+IP+transfer coincidences at the current window.")
    for h in sorted(data["correlation_hits"],
                    key=lambda x: -(x["transaction"].get("amount") or 0))[:12]:
        doc.add_paragraph(f"{h['entity_label']}: {h['explanation']}", style="List Bullet")

    doc.add_heading("4. Money-Flow Findings", 1)
    tbl = doc.add_table(rows=1, cols=4)
    tbl.style = "Light Grid Accent 1"
    for i, h in enumerate(["From", "To", "Amount", "Ref"]):
        tbl.rows[0].cells[i].text = h
    for t in _top_transfers(data):
        c = tbl.add_row().cells
        c[0].text = _label(data, t["from_entity"])
        c[1].text = _label(data, t["to_entity"])
        c[2].text = str(t.get("amount"))
        c[3].text = str(t.get("ref"))

    doc.add_heading("5. Suspicious Transaction Report (STR) — Draft", 1)
    for line in _str_lines(data):
        doc.add_paragraph(line, style="List Bullet")

    doc.add_paragraph("Generated by ERakshak. Findings require analyst verification.")
    doc.save(path)
    return path


def _label(data, eid):
    return str((data["entities"].get(eid, {}) or {}).get("label", eid))


def _str_lines(data) -> list[str]:
    """F2: FIU-IND-style STR narrative lines (one suspected subject per entry)."""
    lines = []
    n = 0
    for r in _top_entities(data, 10):
        if r["band"] in ("high", "medium") and r["rule_flags"]:
            n += 1
            reasons = "; ".join(f["rule"].replace("_", " ") for f in r["rule_flags"][:5])
            details = "; ".join(f["detail"] for f in r["rule_flags"][:3])
            lines.append(
                f"STR-{n:03d} | Suspected subject: {r['label']} | Risk {r['risk_score']} "
                f"({r['band']}) | Grounds of suspicion: {reasons} | Basis: {details} | "
                f"Recommended action: file STR with FIU-IND; freeze/monitor per SOP."
            )
    return lines or ["No suspicious entities above threshold; no STR recommended."]
