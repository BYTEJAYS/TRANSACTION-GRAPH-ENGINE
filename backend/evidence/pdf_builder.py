"""
PDF evidence report builder using ReportLab.

Generates a professional fraud investigation PDF from an evidence dict
produced by EvidenceGenerator.generate().
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# ── Palette ───────────────────────────────────────────────────────────────────
_BLACK      = "#0a0a0f"
_RED        = "#dc2626"
_CYAN       = "#0e7490"
_GOLD       = "#b45309"
_SLATE_900  = "#0f172a"
_SLATE_700  = "#334155"
_SLATE_500  = "#64748b"
_SLATE_300  = "#cbd5e1"
_SLATE_100  = "#f1f5f9"
_SLATE_50   = "#f8fafc"
_WHITE      = "#ffffff"


def build_pdf(evidence: Dict[str, Any], output_path: str) -> bool:
    """
    Build a fraud investigation PDF.

    Returns True if the file was written successfully, False if ReportLab
    is unavailable (the JSON file is always generated regardless).
    """
    if not REPORTLAB_AVAILABLE:
        return False

    _hex = {
        "black": _BLACK, "red": _RED, "cyan": _CYAN, "gold": _GOLD,
        "s900": _SLATE_900, "s700": _SLATE_700, "s500": _SLATE_500,
        "s300": _SLATE_300, "s100": _SLATE_100, "s50": _SLATE_50,
        "white": _WHITE,
    }
    C = {k: colors.HexColor(v) for k, v in _hex.items()}

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=22 * mm,
        leftMargin=22 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title="Fraud Investigation Report",
        author="TGIE — Transaction Graph Intelligence Engine",
    )

    base = getSampleStyleSheet()

    def style(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    S = {
        "h1": style("H1",
            fontSize=18, fontName="Helvetica-Bold",
            textColor=C["black"], spaceAfter=1 * mm),
        "sub": style("Sub",
            fontSize=8, fontName="Helvetica",
            textColor=C["s500"], spaceAfter=5 * mm),
        "sec": style("Sec",
            fontSize=10, fontName="Helvetica-Bold",
            textColor=C["cyan"], spaceBefore=5 * mm, spaceAfter=3 * mm),
        "body": style("Body",
            fontSize=9, fontName="Helvetica",
            textColor=C["s700"], spaceAfter=2 * mm, leading=14),
        "mono": style("Mono",
            fontSize=8, fontName="Courier",
            textColor=C["s700"], spaceAfter=1 * mm),
        "path": style("Path",
            fontSize=9, fontName="Courier-Bold",
            textColor=C["red"], spaceAfter=2 * mm, leading=16),
        "foot": style("Foot",
            fontSize=7, fontName="Helvetica",
            textColor=C["s300"]),
        "foot_r": style("FootR",
            fontSize=7, fontName="Helvetica-Bold",
            textColor=C["red"], alignment=TA_RIGHT),
    }

    meta    = evidence["fraud_metadata"]
    details = evidence["fraud_details"]
    amounts = details["amounts"]
    risk    = details["risk_explanation"]
    cash    = details["cash_flow"]

    story = []

    # ── Cover banner ─────────────────────────────────────────────────────────
    banner = Table(
        [["FRAUD INVESTIGATION REPORT", "CONFIDENTIAL"]],
        colWidths=[120 * mm, 48 * mm],
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), C["black"]),
        ("TEXTCOLOR",    (0, 0), (0,  0),  C["white"]),
        ("TEXTCOLOR",    (1, 0), (1,  0),  C["red"]),
        ("FONTNAME",     (0, 0), (0,  0),  "Helvetica-Bold"),
        ("FONTNAME",     (1, 0), (1,  0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (0,  0),  14),
        ("FONTSIZE",     (1, 0), (1,  0),   8),
        ("ALIGN",        (1, 0), (1,  0),  "RIGHT"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1),  10),
        ("BOTTOMPADDING",(0, 0), (-1, -1),  10),
        ("LEFTPADDING",  (0, 0), (0,  0),    8),
        ("RIGHTPADDING", (1, 0), (1,  0),    8),
    ]))
    story.append(banner)
    story.append(Spacer(1, 4 * mm))

    # ── Metadata grid ────────────────────────────────────────────────────────
    ts_display = meta["detection_timestamp"][:19].replace("T", " ") + " UTC"
    meta_rows = [
        ["Case ID",        evidence["case_id"],
         "Graph ID",       meta["graph_id"]],
        ["Fraud Type",     meta["fraud_type"],
         "Confidence",     meta["confidence_level"]],
        ["Risk Score",     f"{meta['fraud_score']:.4f}",
         "Verdict",        meta["verdict"]],
        ["Detected At",    ts_display,
         "Txns Analyzed",  str(meta["transactions_analyzed"])],
    ]
    meta_tbl = Table(meta_rows, colWidths=[32 * mm, 65 * mm, 32 * mm, 39 * mm])
    meta_tbl.setStyle(TableStyle([
        ("FONTNAME",     (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",     (0, 0), (-1, -1),  8),
        ("FONTNAME",     (0, 0), (0, -1),  "Helvetica-Bold"),
        ("FONTNAME",     (2, 0), (2, -1),  "Helvetica-Bold"),
        ("TEXTCOLOR",    (0, 0), (0, -1),  C["s500"]),
        ("TEXTCOLOR",    (2, 0), (2, -1),  C["s500"]),
        ("TEXTCOLOR",    (1, 0), (1, -1),  C["s900"]),
        ("TEXTCOLOR",    (3, 0), (3, -1),  C["s900"]),
        ("TEXTCOLOR",    (1, 2), (1,  2),  C["red"]),
        ("TEXTCOLOR",    (3, 2), (3,  2),  C["red"]),
        ("GRID",         (0, 0), (-1, -1), 0.3, C["s300"]),
        ("BACKGROUND",   (0, 0), (0, -1),  C["s50"]),
        ("BACKGROUND",   (2, 0), (2, -1),  C["s50"]),
        ("TOPPADDING",   (0, 0), (-1, -1),  4),
        ("BOTTOMPADDING",(0, 0), (-1, -1),  4),
        ("LEFTPADDING",  (0, 0), (-1, -1),  6),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 4 * mm))

    def section(num: str, title: str):
        story.append(HRFlowable(width="100%", thickness=0.4, color=C["cyan"]))
        story.append(Paragraph(f"{num} — {title}", S["sec"]))

    # ── 01 Fraud Classification ───────────────────────────────────────────────
    section("01", "FRAUD CLASSIFICATION")
    story.append(Paragraph(f"<b>Type:</b> {details['fraud_type']}", S["body"]))
    story.append(Paragraph(f"<b>Why Flagged:</b> {risk['why_flagged']}", S["body"]))

    # ── 02 Financial Summary ─────────────────────────────────────────────────
    section("02", "FINANCIAL SUMMARY")
    fin_rows = [
        ["Metric", "Value"],
        ["Total Suspicious Amount", f"₹{amounts['total_suspicious_amount']:,.2f}"],
        ["Largest Single Transfer",  f"₹{amounts['largest_transfer']:,.2f}"],
        ["Average Transfer",         f"₹{amounts['average_transfer']:,.2f}"],
        ["Total Transaction Count",  str(amounts["total_transaction_count"])],
    ]
    fin_tbl = Table(fin_rows, colWidths=[85 * mm, 60 * mm])
    fin_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  C["s900"]),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  C["white"]),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTNAME",     (0, 1), (0, -1),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1),  9),
        ("TEXTCOLOR",    (0, 1), (0, -1),  C["s700"]),
        ("TEXTCOLOR",    (1, 1), (1, -1),  C["red"]),
        ("GRID",         (0, 0), (-1, -1), 0.3, C["s300"]),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C["white"], C["s50"]]),
        ("TOPPADDING",   (0, 0), (-1, -1),  5),
        ("BOTTOMPADDING",(0, 0), (-1, -1),  5),
        ("LEFTPADDING",  (0, 0), (-1, -1),  6),
    ]))
    story.append(fin_tbl)
    story.append(Spacer(1, 3 * mm))

    # ── 03 Accounts Involved ─────────────────────────────────────────────────
    section("03", "ACCOUNTS INVOLVED")
    accs = details["accounts_involved"]
    if accs:
        COLS = 4
        rows = []
        batch = []
        for acc in accs:
            batch.append(acc)
            if len(batch) == COLS:
                rows.append(batch)
                batch = []
        if batch:
            rows.append(batch + [""] * (COLS - len(batch)))

        col_w = [42 * mm, 42 * mm, 42 * mm, 42 * mm]
        acc_tbl = Table(rows, colWidths=col_w)
        acc_tbl.setStyle(TableStyle([
            ("FONTNAME",     (0, 0), (-1, -1), "Courier"),
            ("FONTSIZE",     (0, 0), (-1, -1),  8),
            ("TEXTCOLOR",    (0, 0), (-1, -1),  C["s700"]),
            ("GRID",         (0, 0), (-1, -1),  0.3, C["s300"]),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [C["white"], C["s50"]]),
            ("TOPPADDING",   (0, 0), (-1, -1),   4),
            ("BOTTOMPADDING",(0, 0), (-1, -1),   4),
            ("LEFTPADDING",  (0, 0), (-1, -1),   6),
        ]))
        story.append(acc_tbl)
    story.append(Spacer(1, 3 * mm))

    # ── 04 Fraud Path ────────────────────────────────────────────────────────
    section("04", "FRAUD PATH")
    fraud_path = details["fraud_path"]
    if fraud_path:
        path_str = " → ".join(fraud_path)
        story.append(Paragraph(path_str, S["path"]))
    else:
        story.append(Paragraph("No deterministic path identified", S["body"]))

    # ── 05 Cash Flow (conditional) ───────────────────────────────────────────
    next_sec = 5
    if cash["has_cash_involvement"]:
        section("05", "CASH FLOW INVOLVEMENT")
        if cash["cash_inflows"]:
            story.append(Paragraph("<b>Cash Inflows:</b>", S["body"]))
            for cf in cash["cash_inflows"]:
                story.append(Paragraph(
                    f"  {cf['source']} → {cf['account']}"
                    f"    ₹{cf['amount']:,.2f}",
                    S["mono"],
                ))
        if cash["cash_outflows"]:
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph("<b>Cash Outflows:</b>", S["body"]))
            for cf in cash["cash_outflows"]:
                story.append(Paragraph(
                    f"  {cf['account']} → {cf['destination']}"
                    f"    ₹{cf['amount']:,.2f}",
                    S["mono"],
                ))
        next_sec = 6

    # ── 06 Risk Explanation ──────────────────────────────────────────────────
    section(f"0{next_sec}", "RISK EXPLANATION")

    story.append(Paragraph("<b>Suspicious Topology:</b>", S["body"]))
    story.append(Paragraph(risk["suspicious_topology"], S["body"]))

    story.append(Paragraph("<b>Propagation Behavior:</b>", S["body"]))
    story.append(Paragraph(risk["propagation_behavior"], S["body"]))

    story.append(Paragraph("<b>Anomaly Indicators:</b>", S["body"]))
    for ind in risk["anomaly_indicators"]:
        story.append(Paragraph(f"• {ind}", S["body"]))

    if risk.get("flagged_accounts"):
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("<b>Flagged Accounts:</b>", S["body"]))
        story.append(Paragraph(
            ", ".join(risk["flagged_accounts"]), S["mono"]
        ))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 8 * mm))
    story.append(HRFlowable(width="100%", thickness=0.3, color=C["s300"]))
    story.append(Spacer(1, 2 * mm))

    foot_rows = [[
        "Transaction Graph Intelligence Engine  —  TGIE",
        meta["detection_timestamp"][:10],
        "CONFIDENTIAL — FOR AUTHORIZED USE ONLY",
    ]]
    foot_tbl = Table(foot_rows, colWidths=[80 * mm, 30 * mm, 58 * mm])
    foot_tbl.setStyle(TableStyle([
        ("FONTNAME",   (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",   (0, 0), (-1, -1),  7),
        ("TEXTCOLOR",  (0, 0), (-1, -1),  C["s300"]),
        ("ALIGN",      (2, 0), (2,  0),  "RIGHT"),
        ("TEXTCOLOR",  (2, 0), (2,  0),   C["red"]),
        ("FONTNAME",   (2, 0), (2,  0),  "Helvetica-Bold"),
    ]))
    story.append(foot_tbl)

    doc.build(story)
    return True
