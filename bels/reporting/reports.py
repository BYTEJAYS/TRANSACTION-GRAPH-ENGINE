"""
ForensicReporter — generates forensic-grade reports in JSON, CSV and PDF.

Report types:
  • evidence_verification   — one evidence item, hashes, status, latest verification.
  • blockchain_audit        — ledger status + integrity proof + transaction census.
  • case_timeline           — chronological narrative of an investigation.
  • chain_of_custody        — the immutable custody trail for one evidence item.
  • integrity_verification  — re-validation of the whole ledger.

PDF uses reportlab when available; otherwise a clean text PDF-substitute is returned so
the endpoint never hard-fails.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List

from .. import config
from ..security import utc_now_iso


class ForensicReporter:
    def __init__(self, svc=None) -> None:
        # Lazy import avoids a circular dependency at module import time.
        if svc is None:
            from ..service import service as svc
        self.svc = svc

    # ── report builders (return structured dicts) ────────────────────────────
    def evidence_verification(self, evidence_id: str) -> Dict[str, Any]:
        rec = self.svc.get_evidence(evidence_id)
        if not rec:
            return {"error": f"evidence {evidence_id} not found"}
        verify = self.svc.verify(evidence_id, actor="reporter", role="auditor")
        return {
            "report_type": "Evidence Verification Report",
            "generated_at": utc_now_iso(),
            "evidence": rec.model_dump(),
            "verification": verify.model_dump(),
            "certificate": self.svc.certificate(evidence_id),
        }

    def blockchain_audit(self) -> Dict[str, Any]:
        status = self.svc.blockchain_status()
        integrity = self.svc.chain_integrity()
        evidence = [e.model_dump() for e in self.svc.list_evidence()]
        return {
            "report_type": "Blockchain Audit Report",
            "generated_at": utc_now_iso(),
            "blockchain_status": status,
            "integrity": integrity,
            "evidence_count": len(evidence),
            "evidence": evidence,
        }

    def case_timeline(self, case_id: str) -> Dict[str, Any]:
        case = self.svc.get_case(case_id)
        if not case:
            return {"error": f"case {case_id} not found"}
        events: List[Dict[str, Any]] = []
        for eid in case["evidence_ids"]:
            for ev in self.svc.get_custody(eid):
                events.append({**ev, "evidence_id": eid})
        events.sort(key=lambda e: e["timestamp"])
        return {
            "report_type": "Case Timeline Report",
            "generated_at": utc_now_iso(),
            "case": {k: v for k, v in case.items() if k != "evidence"},
            "evidence_count": len(case["evidence_ids"]),
            "timeline": events,
        }

    def chain_of_custody(self, evidence_id: str) -> Dict[str, Any]:
        rec = self.svc.get_evidence(evidence_id)
        if not rec:
            return {"error": f"evidence {evidence_id} not found"}
        return {
            "report_type": "Chain of Custody Report",
            "generated_at": utc_now_iso(),
            "evidence": rec.model_dump(),
            "custody_events": self.svc.get_custody(evidence_id),
        }

    def integrity_verification(self) -> Dict[str, Any]:
        return {
            "report_type": "Integrity Verification Report",
            "generated_at": utc_now_iso(),
            "blockchain_status": self.svc.blockchain_status(),
            "integrity": self.svc.chain_integrity(),
        }

    # ── serialisation ─────────────────────────────────────────────────────────
    @staticmethod
    def to_json(report: Dict[str, Any]) -> bytes:
        return json.dumps(report, indent=2, default=str).encode()

    @staticmethod
    def to_csv(report: Dict[str, Any]) -> bytes:
        """Flatten the most table-like collection in the report into CSV."""
        buf = io.StringIO()
        rows: List[Dict[str, Any]] = []
        for key in ("evidence", "timeline", "custody_events"):
            val = report.get(key)
            if isinstance(val, list) and val and isinstance(val[0], dict):
                rows = val
                break
        if not rows:
            # Fall back to a flat key/value dump.
            writer = csv.writer(buf)
            writer.writerow(["field", "value"])
            for k, v in report.items():
                writer.writerow([k, json.dumps(v, default=str) if isinstance(v, (dict, list)) else v])
        else:
            fields = sorted({k for r in rows for k in r.keys()})
            writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow({k: (json.dumps(v, default=str) if isinstance(v, (dict, list)) else v)
                                 for k, v in r.items()})
        return buf.getvalue().encode()

    def to_pdf(self, report: Dict[str, Any]) -> bytes:
        try:
            return self._reportlab_pdf(report)
        except Exception:
            # Never hard-fail a report download; return readable text bytes.
            return self.to_json(report)

    @staticmethod
    def _reportlab_pdf(report: Dict[str, Any]) -> bytes:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                        TableStyle)
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("BelsTitle", parent=styles["Title"], textColor=colors.HexColor("#111111"))
        h2 = ParagraphStyle("BelsH2", parent=styles["Heading2"], textColor=colors.HexColor("#222222"))
        body = styles["BodyText"]
        flow = [Paragraph("TGIE — Blockchain Evidence Ledger System", title_style),
                Paragraph(report.get("report_type", "Forensic Report"), h2),
                Paragraph(f"Generated: {report.get('generated_at','')}", body),
                Spacer(1, 8)]

        def render(obj: Any, depth: int = 0) -> None:
            if isinstance(obj, dict):
                rows = []
                for k, v in obj.items():
                    if isinstance(v, (dict, list)):
                        flow.append(Paragraph(str(k).replace("_", " ").title(), h2))
                        render(v, depth + 1)
                    else:
                        rows.append([str(k), str(v)])
                if rows:
                    t = Table(rows, colWidths=[55 * mm, 110 * mm])
                    t.setStyle(TableStyle([
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#555555")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
                    ]))
                    flow.append(t)
                    flow.append(Spacer(1, 6))
            elif isinstance(obj, list):
                for i, item in enumerate(obj[:50]):
                    flow.append(Paragraph(f"• Item {i+1}", body))
                    render(item, depth + 1)

        render({k: v for k, v in report.items() if k not in ("report_type", "generated_at")})
        doc.build(flow)
        return buf.getvalue()

    def save(self, report: Dict[str, Any], name: str, fmt: str) -> str:
        ext = {"json": "json", "csv": "csv", "pdf": "pdf"}[fmt]
        data = {"json": self.to_json, "csv": self.to_csv, "pdf": self.to_pdf}[fmt](report)
        path = config.REPORTS_DIR / f"{name}.{ext}"
        path.write_bytes(data)
        return str(path)


reporter = ForensicReporter()
