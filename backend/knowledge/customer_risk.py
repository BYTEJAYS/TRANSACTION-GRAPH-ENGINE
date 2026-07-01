"""
Unified customer risk graph (Phase 3).

Instead of scoring isolated accounts, this computes risk for every entity in a
heterogeneous component — customers, products, devices, merchants, identities and
channels — and PROPAGATES it: a risky product or a shared device/identity raises
the risk of the customer that owns / is linked to it. Every score is explainable
(why, evidence, related entities, propagation path, confidence, triggered XP
rules). Built on the XP signal layer + entity taxonomy; additive.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .entities import classify_entity, entity_category, EntityType
from .hetero import is_transaction_edge
from .xp_rules import detect_xp_signals


def _level(score: float) -> str:
    if score >= 0.75:
        return "CRITICAL"
    if score >= 0.55:
        return "HIGH"
    if score >= 0.35:
        return "MEDIUM"
    return "LOW"


def _entry(eid: str, et: EntityType, sigs: list[dict], path: list[str]) -> dict[str, Any]:
    score = max((s["severity_score"] * s["confidence"] for s in sigs), default=0.0)
    conf = max((s["confidence"] for s in sigs), default=0.0)
    related = sorted({x for s in sigs for x in s["entities"]} - {eid})
    why, seen = [], set()
    for s in sigs:
        if s["name"] not in seen:
            seen.add(s["name"]); why.append(s["name"])
    return {
        "entity": eid,
        "entity_type": et.value,
        "entity_category": entity_category(et).value,
        "risk_score": round(score, 3),
        "risk_pct": round(score * 100),
        "risk_level": _level(score),
        "why": why,
        "evidence": {s["xp_id"]: s["evidence"] for s in sigs},
        "related_entities": related[:10],
        "propagation_path": path,
        "triggered_rules": sorted({s["xp_id"] for s in sigs}),
        "confidence": round(conf, 3),
    }


def compute_customer_risk(component: dict) -> dict[str, Any]:
    """
    Per-entity risk + customer-level propagation for a heterogeneous component.
    Returns risk lists for customers / products / devices / merchants /
    identities / channels (strongest first) and the single highest-risk entity.
    Safe + empty-quiet on legitimate data.
    """
    nodes = component.get("nodes", []) or [{"id": n} for n in component.get("node_ids", [])]
    all_edges = component.get("edges", [])
    graph_id = component.get("graph_id", "GRAPH_001")

    etype = {str(n.get("id")): classify_entity(n) for n in nodes}

    def et(nid: str) -> EntityType:
        return etype.get(str(nid), EntityType.ACCOUNT)

    signals = detect_xp_signals(component)
    ent_sig: dict[str, list[dict]] = defaultdict(list)
    for s in signals:
        for e in s["entities"]:
            ent_sig[str(e)].append(s)

    # ownership + identity structure
    owns: dict[str, list[str]] = defaultdict(list)
    has_identity: dict[str, list[str]] = defaultdict(list)
    for e in all_edges:
        if is_transaction_edge(e):
            continue
        rel = e.get("relationship_type")
        s, t = str(e.get("source")), str(e.get("target"))
        if rel == "OWNS":
            owns[s].append(t)
        elif rel in ("HAS_DEVICE", "HAS_PHONE", "HAS_PAN", "HAS_EMAIL", "HAS_AADHAAR"):
            has_identity[s].append(t)

    # ── direct per-entity risk (anything an XP signal touches) ──
    products, devices, merchants, identities = [], [], [], []
    for eid, sigs in ent_sig.items():
        e_t = et(eid)
        cat = entity_category(e_t)
        if e_t == EntityType.CUSTOMER:
            continue  # customers handled via propagation below
        path = [f"{s['xp_id']} directly implicates {eid}" for s in sigs]
        entry = _entry(eid, e_t, sigs, path)
        if e_t == EntityType.DEVICE:
            devices.append(entry)
        elif e_t == EntityType.MERCHANT:
            merchants.append(entry)
        elif cat.value == "identity":
            identities.append(entry)
        else:
            products.append(entry)

    # ── customer-level propagation ──
    customers = []
    # a customer is any CUSTOMER node, or any owner that appears in OWNS edges
    customer_ids = {n for n, e_t in etype.items() if e_t == EntityType.CUSTOMER} | set(owns)
    for cust in sorted(customer_ids):
        contributing: list[dict] = []
        path: list[str] = []
        for s in ent_sig.get(cust, []):
            contributing.append(s); path.append(f"{s['xp_id']} directly on {cust}")
        for prod in owns.get(cust, []):
            for s in ent_sig.get(prod, []):
                contributing.append(s); path.append(f"{s['xp_id']} on owned product {prod}")
            for ident in has_identity.get(prod, []):
                for s in ent_sig.get(ident, []):
                    contributing.append(s)
                    path.append(f"{s['xp_id']} via {prod}'s shared identity {ident}")
        for ident in has_identity.get(cust, []):
            for s in ent_sig.get(ident, []):
                contributing.append(s); path.append(f"{s['xp_id']} via shared identity {ident}")
        if contributing:
            entry = _entry(cust, EntityType.CUSTOMER, contributing, path)
            entry["owned_products"] = sorted(owns.get(cust, []))
            customers.append(entry)

    # ── channel (rail) risk from the signals that cite rails ──
    channel_risk: dict[str, float] = defaultdict(float)
    channel_conf: dict[str, float] = defaultdict(float)
    for s in signals:
        for rail in s["evidence"].get("rails", []):
            r = rail.lower()
            channel_risk[r] = max(channel_risk[r], s["severity_score"] * s["confidence"])
            channel_conf[r] = max(channel_conf[r], s["confidence"])
    channels = [
        {"channel": r, "risk_score": round(v, 3), "risk_level": _level(v),
         "confidence": round(channel_conf[r], 3)}
        for r, v in channel_risk.items()
    ]

    for lst in (customers, products, devices, merchants, identities, channels):
        lst.sort(key=lambda x: x["risk_score"], reverse=True)

    everything = customers + products + devices + merchants + identities
    top = max(everything, key=lambda x: x["risk_score"], default=None)

    return {
        "graph_id": graph_id,
        "available": bool(signals),
        "customers": customers,
        "products": products,
        "devices": devices,
        "merchants": merchants,
        "identities": identities,
        "channels": channels,
        "top_risk_entity": top,
        "xp_signal_count": len(signals),
    }
