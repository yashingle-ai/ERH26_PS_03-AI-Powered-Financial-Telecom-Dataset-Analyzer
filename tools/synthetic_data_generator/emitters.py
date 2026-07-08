"""Write generated activity to files in realistic source formats (research/12 §8.1 step 4-5).

Deliberately emits bank statements across Excel / CSV / PDF and with a header identity
block, so downstream parsers (Phase 1) are exercised on heterogeneous layouts (NFR-1).
CDR and IPDR are emitted as delimited CSV per operator (confirmed structured/delimited).
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BANK_COLUMNS = ["Transaction Date", "Narration", "Debit", "Credit", "Balance", "Ref No"]
OPERATORS = ["jio", "airtel", "vi", "bsnl"]


def _fmt_dt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _fmt_date(dt):
    return dt.strftime("%d/%m/%Y")


def _bank_rows_by_account(txns):
    by_acc = defaultdict(list)
    for t in txns:
        by_acc[(t["account_no"], t["bank_name"], t["ifsc"], t["account_holder"])].append(t)
    return by_acc


def _with_balance(rows, rng):
    rows = sorted(rows, key=lambda r: r["txn_dt"])
    bal = round(rng.uniform(50_000, 500_000), 2)
    out = []
    for r in rows:
        bal += (r["credit"] or 0) - (r["debit"] or 0)
        out.append({
            # Include time: UPI/IMPS/RTGS records carry precise timestamps, which the
            # temporal-coincidence correlation (FR-9) depends on.
            "Transaction Date": r["txn_dt"].strftime("%d/%m/%Y %H:%M:%S"),
            "Narration": r["narration"],
            "Debit": r["debit"] if r["debit"] else "",
            "Credit": r["credit"] if r["credit"] else "",
            "Balance": round(bal, 2),
            "Ref No": r["ref_no"],
        })
    return out


def emit_bank(txns, out_dir, rng, acct_mobile=None):
    acct_mobile = acct_mobile or {}
    bank_dir = os.path.join(out_dir, "bank")
    os.makedirs(bank_dir, exist_ok=True)
    by_acc = _bank_rows_by_account(txns)
    files = []
    for i, ((acct, bank, ifsc, holder), rows) in enumerate(sorted(by_acc.items())):
        table_rows = _with_balance(rows, rng)
        df = pd.DataFrame(table_rows, columns=BANK_COLUMNS)
        fmt = ["xlsx", "csv", "pdf"][i % 3]  # spread across formats
        base = f"{bank.split()[0].lower()}_{acct}"
        # Registered mobile is the fusion bridge between bank and telecom (Doc 06 §8)
        meta = {"bank": bank, "ifsc": ifsc, "account_no": acct, "holder": holder,
                "mobile": acct_mobile.get(acct, "")}
        if fmt == "csv":
            path = os.path.join(bank_dir, base + ".csv")
            df2 = df.copy()
            df2.insert(0, "Account Number", acct)
            df2.insert(1, "Account Name", holder)
            df2.insert(2, "Customer Mobile", meta["mobile"])
            df2.to_csv(path, index=False)
        elif fmt == "xlsx":
            path = os.path.join(bank_dir, base + ".xlsx")
            _write_xlsx_statement(path, df, meta)
        else:
            path = os.path.join(bank_dir, base + ".pdf")
            _write_pdf_statement(path, table_rows, meta)
        files.append({"file": os.path.relpath(path, out_dir), "format": fmt, **meta,
                      "rows": len(rows)})
    return files


def _write_xlsx_statement(path, df, meta):
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        # Header identity block (Doc 06: identity lives above the table)
        header = pd.DataFrame({
            "A": ["Bank", "Account Name", "Account Number", "IFSC", "Registered Mobile", ""],
            "B": [meta["bank"], meta["holder"], meta["account_no"], meta["ifsc"],
                  meta["mobile"], ""],
        })
        header.to_excel(xw, sheet_name="Statement", index=False, header=False, startrow=0)
        df.to_excel(xw, sheet_name="Statement", index=False, startrow=6)


def _write_pdf_statement(path, rows, meta):
    doc = SimpleDocTemplate(path, pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"<b>{meta['bank']}</b>", styles["Title"]),
        Paragraph("Account Statement", styles["Heading2"]),
        Paragraph(f"Account Name: {meta['holder']}", styles["Normal"]),
        Paragraph(f"Account Number: {meta['account_no']} &nbsp;&nbsp; IFSC: {meta['ifsc']}",
                  styles["Normal"]),
        Paragraph(f"Registered Mobile: {meta['mobile']}", styles["Normal"]),
        Spacer(1, 8),
    ]
    data = [BANK_COLUMNS] + [[str(r[c]) for c in BANK_COLUMNS] for r in rows]
    tbl = Table(data, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
    ]))
    story.append(tbl)
    doc.build(story)


def emit_cdr(cdr_rows, out_dir, rng):
    cdr_dir = os.path.join(out_dir, "cdr")
    os.makedirs(cdr_dir, exist_ok=True)
    cols = {
        "calling_number": "Calling Party Number", "called_number": "Called Party Number",
        "call_dt": "Call Date", "duration_sec": "Duration (sec)", "call_type": "Call Type",
        "imei": "IMEI", "imsi": "IMSI", "cell_id": "Cell ID", "tower_location": "Tower Location",
    }
    files = _emit_split_csv(cdr_rows, cdr_dir, out_dir, cols, "call_dt", rng, "cdr")
    return files


def emit_ipdr(ipdr_rows, out_dir, rng):
    ipdr_dir = os.path.join(out_dir, "ipdr")
    os.makedirs(ipdr_dir, exist_ok=True)
    cols = {
        "subscriber_msisdn": "Subscriber ID", "private_ip": "Private IP", "public_ip": "Public IP",
        "source_port": "Source Port", "session_start": "Session Start Time",
        "session_end": "Session End Time", "bytes_up": "Uplink Bytes",
        "bytes_down": "Downlink Bytes", "dest_ip": "Destination IP", "imei": "IMEI",
    }
    files = _emit_split_csv(ipdr_rows, ipdr_dir, out_dir, cols, "session_start", rng, "ipdr")
    return files


def _emit_split_csv(rows, sub_dir, out_dir, colmap, dt_key, rng, kind):
    """Split rows across operators to simulate multiple providers (FR-2/3)."""
    buckets = defaultdict(list)
    for r in rows:
        buckets[rng.choice(OPERATORS)].append(r)
    files = []
    for op, op_rows in buckets.items():
        recs = []
        for r in op_rows:
            rec = {}
            for k, label in colmap.items():
                v = r[k]
                if hasattr(v, "strftime"):
                    v = _fmt_dt(v)
                rec[label] = v
            recs.append(rec)
        df = pd.DataFrame(recs, columns=list(colmap.values()))
        path = os.path.join(sub_dir, f"{kind}_{op}.csv")
        df.to_csv(path, index=False)
        files.append({"file": os.path.relpath(path, out_dir), "operator": op, "rows": len(op_rows)})
    return files


def emit_ground_truth(ground_truth, out_dir):
    path = os.path.join(out_dir, "ground_truth.json")
    with open(path, "w") as f:
        json.dump(ground_truth, f, indent=2)
    return os.path.relpath(path, out_dir)


def emit_metadata(tier, seed, file_manifest, ground_truth, out_dir, metadata_dir):
    os.makedirs(metadata_dir, exist_ok=True)
    meta = {
        "dataset": f"ERakshak synthetic — {tier.name}",
        "source": "tools/synthetic_data_generator (self-generated)",
        "license": "Synthetic — free for project use; contains no real personal data",
        "download_url": None,
        "version": "1.0",
        "generated_with": {"tier": tier.name, "seed": seed,
                           "persons": tier.n_persons, "days": tier.days,
                           "fraud_rings": tier.n_fraud_rings},
        "schema": "Maps to canonical model in research/06_data_understanding.md §4",
        "preprocessing": "None — raw generated files as an operator/bank would export",
        "counts": {k: len(v) for k, v in file_manifest.items()},
        "ground_truth_scenarios": len(ground_truth),
        "known_limitations": [
            "Schemas are modeled (research/06), not from real operator/bank exports (Q1-Q3).",
            "Fraud patterns are stylized; real laundering is noisier.",
            "Finance<->telecom bridge is guaranteed by construction; real data may be weaker.",
        ],
        "files": file_manifest,
    }
    path = os.path.join(metadata_dir, f"{tier.name}_metadata.json")
    with open(path, "w") as f:
        json.dump(meta, f, indent=2, default=str)
    return path
