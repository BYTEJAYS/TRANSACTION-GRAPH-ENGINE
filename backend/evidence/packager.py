"""
Server-side evidence packager (Phase 8).

Assembles a deterministic, regulator-grade evidence package for a case from the
case_management enrich payload (which already bakes in graph_snapshot, roles,
graph_metrics, raw transactions, recovery, fraud_dna, notes, timeline) plus the
risk assessment and detector findings. The CANONICAL JSON of the package core is
hashed (SHA-256) — re-building the same case yields the same hash, so the PDF is
just a rendering and never affects integrity.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

_STORAGE = os.getenv(
    "TGIE_EVIDENCE_STORAGE",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "evidence_storage"),
)


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def canonical_hash(core: dict) -> str:
    return hashlib.sha256(_canonical(core)).hexdigest()


# ── section assembly ──────────────────────────────────────────────────────────
def _suspicious_accounts(case: dict) -> list[dict]:
    roles = case.get("account_roles") or case.get("roles") or {}
    out = []
    for acc in (case.get("accounts") or []):
        aid = acc.get("account_id") if isinstance(acc, dict) else acc
        if not aid:
            continue
        flagged = isinstance(acc, dict) and (acc.get("is_flagged") or acc.get("risk_score", 0) >= 0.6)
        out.append({
            "account": aid,
            "role": roles.get(aid) if isinstance(roles, dict) else None,
            "risk_score": acc.get("risk_score") if isinstance(acc, dict) else None,
            "flagged": bool(flagged),
        })
    return out


def _path_analysis(case: dict) -> dict:
    snap = case.get("graph_snapshot") or case.get("raw_graph_json") or {}
    edges = snap.get("edges") or snap.get("links") or []
    adj: dict[str, list[str]] = {}
    for e in edges:
        s = e.get("source"); t = e.get("target")
        if isinstance(s, dict): s = s.get("id")
        if isinstance(t, dict): t = t.get("id")
        if s and t:
            adj.setdefault(str(s), []).append(str(t))
    # greedy longest forward walk (bounded) — illustrative fund path
    best: list[str] = []
    for start in list(adj.keys())[:200]:
        path, cur, seen = [start], start, {start}
        for _ in range(12):
            nxts = [n for n in adj.get(cur, []) if n not in seen]
            if not nxts:
                break
            cur = nxts[0]; path.append(cur); seen.add(cur)
        if len(path) > len(best):
            best = path
    return {"longest_fund_path": best, "hops": max(0, len(best) - 1), "edge_count": len(edges)}


def build_package(case_id: str, actor: str = "system") -> Optional[dict]:
    from case_management.store import store
    case = store.get(case_id)
    if not case:
        return None

    sections = {
        "1_case_summary": {
            k: case.get(k) for k in
            ("case_id", "title", "category", "status", "priority", "disposition",
             "assigned_to", "assigned_name", "department", "created_at", "updated_at")
        },
        "2_timeline": case.get("timeline") or [],
        "3_graph_snapshot": case.get("graph_snapshot") or case.get("raw_graph_json") or {},
        "4_suspicious_accounts": _suspicious_accounts(case),
        "5_transactions": case.get("raw_transaction_json") or case.get("transactions") or [],
        "6_risk_score": {"risk_score": case.get("risk_score"),
                         "assessment": case.get("risk_assessment") or {}},
        "7_fraud_pattern": {"category": case.get("category"),
                            "detection_key": case.get("detection_key"),
                            "fraud_dna": case.get("fraud_dna") or {}},
        "8_reason": case.get("detection_reason") or "",
        "9_confidence": case.get("fraud_confidence"),
        "10_supporting_rules": (case.get("risk_assessment") or {}).get("factors")
                               or (case.get("roles") or {}),
        "11_ml_explanation": (case.get("risk_assessment") or {}).get("ml")
                             or {"note": "ML ensemble explanation attaches when the model "
                                          "is scored for this case (Phase 5 wiring)."},
        "12_graph_metrics": case.get("graph_metrics") or {},
        "13_path_analysis": _path_analysis(case),
        "14_investigator_notes": {"notes": case.get("notes") or [],
                                  "comments": case.get("comments") or []},
    }
    # regulatory summary added by fiu.py to avoid a cycle here
    from .fiu import regulatory_summary
    sections["15_regulatory_summary"] = regulatory_summary(case, sections)

    core = {"case_id": case_id, "sections": sections}
    sha = canonical_hash(core)
    package = {
        "package_id": f"EVP-{case_id}-{sha[:10]}",
        "case_id": case_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": actor,
        "sections": sections,
        "integrity": {"sha256": sha, "algorithm": "SHA-256", "anchor": {"status": "pending"}},
    }
    return package


# ── rendering ─────────────────────────────────────────────────────────────────
def _ensure_storage() -> str:
    os.makedirs(_STORAGE, exist_ok=True)
    return _STORAGE


def render_json(package: dict) -> str:
    path = os.path.join(_ensure_storage(), f"{package['package_id']}.json")
    with open(path, "w") as f:
        json.dump(package, f, indent=2, default=str)
    return path


def render_pdf(package: dict) -> Optional[str]:
    """Compact, generic reportlab renderer over the 15 sections. Returns the path,
    or None if reportlab is unavailable (JSON is always written regardless)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    except Exception:
        return None

    path = os.path.join(_ensure_storage(), f"{package['package_id']}.pdf")
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(path, pagesize=A4, title=f"Evidence {package['package_id']}")
    flow = [Paragraph("TGIE — Financial Crime Evidence Package", styles["Title"]),
            Paragraph(f"Package {package['package_id']} · Case {package['case_id']}", styles["Normal"]),
            Paragraph(f"SHA-256: {package['integrity']['sha256']}", styles["Code"]),
            Spacer(1, 8 * mm)]
    for key in sorted(package["sections"].keys()):
        title = key.split("_", 1)[1].replace("_", " ").title()
        flow.append(Paragraph(title, styles["Heading2"]))
        body = json.dumps(package["sections"][key], indent=1, default=str)
        # keep the PDF bounded
        if len(body) > 4000:
            body = body[:4000] + "\n… (truncated; see JSON package)"
        for line in body.splitlines():
            flow.append(Paragraph(line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
                                  styles["Code"]))
        flow.append(Spacer(1, 4 * mm))
    try:
        doc.build(flow)
        return path
    except Exception:
        return None
