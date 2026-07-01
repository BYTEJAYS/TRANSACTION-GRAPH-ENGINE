"""
Knowledge Base facade (Phase 10 + cross-product assembly).

A single object (`KB`) the other engines consult for Union Bank banking
knowledge, plus `cross_product_report` — the unified cross-product intelligence
for one component: which products/channels/identities it spans, the XP rules it
trips, the named typologies it matches, the product-aware recovery actions to
take, and the regulatory hooks to cite. Reuses the existing motif/analytics
engines elsewhere; this layer adds only the cross-product correlation on top.
"""
from __future__ import annotations

from typing import Any

from . import catalogue, playbooks
from .entities import classify_node, classify_edge, involved_categories, ProductCategory, classify_entity, entity_category
from .xp_rules import XP_RULES, detect_xp_signals


class KnowledgeBase:
    """Read-only facade over the Union Bank knowledge layers."""

    products = catalogue.PRODUCTS
    channels = catalogue.CHANNELS
    typologies = catalogue.TYPOLOGIES
    regulatory = catalogue.REGULATORY
    xp_rules = XP_RULES

    def product(self, name: str) -> dict[str, Any]:
        return catalogue.product(name)

    def recovery_levers(self, product_name: str) -> list[str]:
        return catalogue.recovery_levers(product_name)

    def recovery_action(self, lever: str, confidence: float = 1.0) -> dict[str, Any] | None:
        return playbooks.action_for(lever, confidence)

    def regulatory_for(self, key: str) -> dict[str, Any]:
        return catalogue.REGULATORY.get(key, {})

    def summary(self) -> dict[str, Any]:
        """Inventory of the knowledge base (for the /api/knowledge endpoint)."""
        return {
            "products": list(catalogue.PRODUCTS),
            "channels": list(catalogue.CHANNELS),
            "typologies": {k: v["label"] for k, v in catalogue.TYPOLOGIES.items()},
            "xp_rules": {k: v["name"] for k, v in XP_RULES.items()},
            "regulatory_frameworks": sorted({v["framework"] for v in catalogue.REGULATORY.values()}),
            "counts": {
                "products": len(catalogue.PRODUCTS), "channels": len(catalogue.CHANNELS),
                "typologies": len(catalogue.TYPOLOGIES), "xp_rules": len(XP_RULES),
            },
        }


KB = KnowledgeBase()


def _regulatory_hooks(categories: set[str], xp_ids: set[str]) -> list[dict[str, Any]]:
    hooks = []
    if "cash" in categories or "external" in categories:
        hooks.append({"key": "cash_intensive", **catalogue.REGULATORY["cash_intensive"]})
    if {"XP009", "XP010", "XP011"} & xp_ids:
        hooks.append({"key": "identity", **catalogue.REGULATORY["identity"]})
    if "XP012" in xp_ids:
        hooks.append({"key": "structuring", **catalogue.REGULATORY["structuring"]})
    if "external" in categories:
        hooks.append({"key": "cross_border", **catalogue.REGULATORY["cross_border"]})
    # de-dup by key, preserve order
    seen, out = set(), []
    for h in hooks:
        if h["key"] not in seen:
            seen.add(h["key"]); out.append(h)
    return out


def cross_product_report(component: dict) -> dict[str, Any]:
    """
    Unified cross-product intelligence for one component. Additive: built from
    entity classification + XP detection + the knowledge catalogue, leaving the
    existing per-account motif/case engines untouched.
    """
    nodes = component.get("nodes", []) or [{"id": n} for n in component.get("node_ids", [])]
    edges = component.get("edges", [])
    graph_id = component.get("graph_id", "GRAPH_001")

    categories = involved_categories(nodes, edges)
    product_cats = {entity_category(classify_entity(n)).value for n in nodes}
    spans = {c for c in product_cats if c not in ("unknown",)}
    xp_signals = detect_xp_signals(component)
    xp_ids = {s["xp_id"] for s in xp_signals}
    matched = catalogue.match_typologies(categories)

    # product-aware recovery actions, scaled by the strongest XP confidence
    conf = max((s["confidence"] for s in xp_signals), default=0.6)
    levers: list[str] = []
    for s in xp_signals:
        levers.extend(s["recovery_recommendation"])
    seen, actions = set(), []
    for lever in levers:
        if lever in seen:
            continue
        seen.add(lever)
        act = playbooks.action_for(lever, conf)
        if act:
            actions.append(act)
    actions.sort(key=lambda a: a["risk_reduction"] * a["confidence"], reverse=True)

    # Genuinely cross-product = spans ≥2 PRODUCT-HOLDING categories (paying a
    # merchant is ubiquitous, so "payment" is excluded), OR an XP signal fired.
    is_cross_product = len(spans & {
        "retail", "corporate", "loan", "deposit", "card", "digital",
    }) >= 2 or bool(xp_signals)

    return {
        "graph_id": graph_id,
        "is_cross_product": is_cross_product,
        "product_categories": sorted(spans),
        "channels": sorted(c for c in categories if c in catalogue.CHANNELS),
        "entities": {str(n.get("id")): classify_node(n) for n in nodes},
        "xp_signals": xp_signals,
        "xp_rule_count": len(xp_signals),
        "matched_typologies": [
            {"typology": m["typology"], "label": m["label"], "narrative": m["narrative"],
             "products": m["products"], "overlap": m["overlap"]}
            for m in matched[:5]
        ],
        "recovery_actions": actions,
        "regulatory_hooks": _regulatory_hooks(categories, xp_ids),
    }
