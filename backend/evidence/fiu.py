"""
Regulatory / FIU output (Phase 8).

`regulatory_summary` produces a concise summary embedded in the package; `build_str`
renders a FIU-IND Suspicious Transaction Report (STR) — DEMO template structured
for real FIU-IND mapping later (account, suspicion grounds, amounts, period).
"""
from __future__ import annotations

from typing import Any


def regulatory_summary(case: dict, sections: dict) -> dict:
    accts = sections.get("4_suspicious_accounts", [])
    txns = sections.get("5_transactions", []) or []
    total = 0.0
    for t in txns:
        try:
            total += float(t.get("amount", 0) if isinstance(t, dict) else 0)
        except Exception:
            pass
    return {
        "suspicion_grounds": case.get("detection_reason") or case.get("category") or "anomalous activity",
        "risk_score": case.get("risk_score"),
        "confidence": case.get("fraud_confidence"),
        "accounts_involved": len(accts),
        "flagged_accounts": [a["account"] for a in accts if a.get("flagged")][:50],
        "transaction_count": len(txns),
        "total_amount": round(total, 2),
        "recommended_action": "File STR with FIU-IND" if (case.get("risk_score") or 0) >= 60
                              else "Continue monitoring",
    }


def build_str(package: dict) -> dict:
    """FIU-IND STR (DEMO) document derived from a built package."""
    case = package["sections"]["1_case_summary"]
    reg = package["sections"].get("15_regulatory_summary", {})
    return {
        "report_type": "STR",
        "regulator": "FIU-IND (DEMO)",
        "report_format_version": "STR-2.0-demo",
        "reporting_entity": {"name": "TGIE Demo Bank", "category": "Scheduled Commercial Bank"},
        "case_reference": case.get("case_id"),
        "ground_of_suspicion": reg.get("suspicion_grounds"),
        "risk_assessment": {"score": reg.get("risk_score"), "confidence": reg.get("confidence")},
        "subjects": reg.get("flagged_accounts", []),
        "transactions": {"count": reg.get("transaction_count"), "total_amount_inr": reg.get("total_amount")},
        "action_recommended": reg.get("recommended_action"),
        "integrity": {"package_id": package["package_id"], "sha256": package["integrity"]["sha256"]},
        "disclaimer": "DEMO STR — structure illustrative; not a filed regulatory report.",
    }
