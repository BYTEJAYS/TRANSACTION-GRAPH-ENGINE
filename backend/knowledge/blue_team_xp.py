"""
Cross-product correlation for the live Blue Team path (Phase 5).

The Blue Team V2 engine scores one transaction component. This adds a thin,
defensive correlation layer that augments each component verdict with the
cross-product picture — which products/identities it spans, the XP rules it
trips, the named typologies, the highest customer risk and the product-aware
recovery actions — WITHOUT changing the V2 verdict or the existing schema. It is
purely additive: consumers that don't read `cross_product` are unaffected.
"""
from __future__ import annotations

from typing import Any

from .knowledge_base import cross_product_report
from .customer_risk import compute_customer_risk


def correlate(component: dict) -> dict[str, Any]:
    """Compact cross-product correlation summary for one component verdict.

    Safe by construction — returns a quiet, well-formed summary on any input and
    never raises, so it can sit in the live analysis loop without risk.
    """
    try:
        cp = cross_product_report(component)
        cr = compute_customer_risk(component)
    except Exception as exc:  # never break the live Blue Team path
        return {"available": False, "is_cross_product": False, "reason": str(exc)}

    top_customer = cr["customers"][0] if cr["customers"] else None
    return {
        "available": bool(cp["xp_signals"]) or cp["is_cross_product"],
        "is_cross_product": cp["is_cross_product"],
        "product_categories": cp["product_categories"],
        "channels": cp["channels"],
        "xp_rules": [
            {"xp_id": s["xp_id"], "name": s["name"], "severity": s["severity"],
             "confidence": s["confidence"]}
            for s in cp["xp_signals"]
        ],
        "matched_typologies": [t["label"] for t in cp["matched_typologies"]],
        "top_customer_risk": (
            {"customer": top_customer["entity"], "risk_level": top_customer["risk_level"],
             "risk_pct": top_customer["risk_pct"], "why": top_customer["why"]}
            if top_customer else None
        ),
        "recovery_actions": [a["action"] for a in cp["recovery_actions"][:5]],
        "regulatory_hooks": [h["key"] for h in cp["regulatory_hooks"]],
    }
