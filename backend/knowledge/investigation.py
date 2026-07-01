"""
Single-customer investigation report (Phase 8).

When an investigator opens a customer, this assembles ONE unified ecosystem view
instead of an account-by-account picture: profile, owned + connected products,
device & identity intelligence, merchant relationships, cross-product flows,
money trails, community membership, fraud motifs, triggered XP rules, timeline,
recommendations, recovery actions and a plain-language narrative.

It is an assembler — every section reuses an existing engine (case intelligence,
analytics, timeline, motifs, community intelligence, cross-product, customer
risk). No detection logic is duplicated here.
"""
from __future__ import annotations

from typing import Any

from .entities import classify_entity, entity_category, EntityType
from .knowledge_base import cross_product_report
from .customer_risk import compute_customer_risk


def _structure(edges: list[dict]) -> tuple[dict[str, list[str]], dict[str, str], dict[str, list[str]]]:
    """OWNS (customer→products), owned_by (product→customer), identities (owner→ids)."""
    owns: dict[str, list[str]] = {}
    owned_by: dict[str, str] = {}
    identities: dict[str, list[str]] = {}
    for e in edges:
        rel = e.get("relationship_type")
        s, t = str(e.get("source")), str(e.get("target"))
        if rel == "OWNS":
            owns.setdefault(s, []).append(t)
            owned_by[t] = s
        elif rel in ("HAS_DEVICE", "HAS_PHONE", "HAS_PAN", "HAS_EMAIL", "HAS_AADHAAR"):
            identities.setdefault(s, []).append(t)
    return owns, owned_by, identities


def build_customer_investigation(component: dict, customer_id: str) -> dict[str, Any]:
    """Unified investigation report centred on one customer (or account)."""
    # heavy engines imported lazily so `import knowledge` stays light
    from graph_engine.analytics import narrate_flows
    from graph_engine.timeline import summarize_timeline
    from graph_engine.community_intelligence import analyze_communities
    from rule_engine import extract_motifs

    nodes = component.get("nodes", []) or [{"id": n} for n in component.get("node_ids", [])]
    edges = component.get("edges", [])
    etype = {str(n.get("id")): classify_entity(n) for n in nodes}

    def et(nid: str) -> EntityType:
        return etype.get(str(nid), EntityType.ACCOUNT)

    owns, owned_by, identities = _structure(edges)

    # resolve focus: if an account/product id was given, pivot to its owner
    focus = customer_id
    if customer_id in owned_by:
        focus = owned_by[customer_id]
    owned = owns.get(focus, [])
    if not owned:  # no ownership data — treat the given id as the focus account
        owned = [customer_id]

    owned_set = set(owned) | {focus}
    txn_edges = [e for e in edges if not e.get("relationship_type") or
                 e.get("relationship_type") == "TRANSFERRED" or e.get("amount")]

    # connected products: transaction counterparties of the customer's products
    connected: set[str] = set()
    for e in txn_edges:
        s, t = str(e.get("source")), str(e.get("target"))
        if s in owned_set:
            connected.add(t)
        if t in owned_set:
            connected.add(s)
    connected -= owned_set

    # device / identity / merchant intelligence
    own_identities: list[str] = list(identities.get(focus, []))
    for p in owned:
        own_identities += identities.get(p, [])
    devices = sorted({i for i in own_identities if et(i) == EntityType.DEVICE})
    id_docs = sorted({i for i in own_identities if entity_category(et(i)).value == "identity"})
    merchants = sorted({c for c in connected if et(c) == EntityType.MERCHANT})

    # reuse the cross-product + customer-risk + structural engines
    cp = cross_product_report(component)
    cr = compute_customer_risk(component)
    cust_risk = next((c for c in cr["customers"] if c["entity"] == focus), None)
    motifs = extract_motifs(component)
    flows = narrate_flows(nodes, edges)
    timeline = summarize_timeline([e for e in edges if e.get("amount")])
    communities = analyze_communities(nodes, edges, top=5, deep=False).get("communities", [])
    community_of = next((c["community_id"] for c in communities
                         if focus in c.get("members", [])), None)

    def _product_view(pid: str) -> dict[str, Any]:
        e_t = et(pid)
        risk = next((p for p in cr["products"] if p["entity"] == pid), None)
        return {"product": pid, "type": e_t.value, "category": entity_category(e_t).value,
                "risk_level": risk["risk_level"] if risk else "LOW",
                "risk_pct": risk["risk_pct"] if risk else 0,
                "triggered_rules": risk["triggered_rules"] if risk else []}

    # narrative
    xp_names = [s["name"] for s in cp["xp_signals"]]
    bits = [f"Customer {focus} holds {len(owned)} product(s): {', '.join(sorted(owned))}."]
    if cp["is_cross_product"]:
        bits.append(f"Activity spans products across {', '.join(cp['product_categories'])}.")
    if xp_names:
        bits.append(f"Cross-product rules triggered: {', '.join(xp_names)}.")
    if devices:
        bits.append(f"{len(devices)} device(s) linked.")
    if cust_risk:
        bits.append(f"Overall customer risk: {cust_risk['risk_level']} ({cust_risk['risk_pct']}%).")
    if flows.get("summary_narrative"):
        bits.append(flows["summary_narrative"])
    narrative = " ".join(bits)

    return {
        "graph_id": component.get("graph_id", "GRAPH_001"),
        "customer": focus,
        "profile": {
            "entity_type": et(focus).value,
            "product_count": len(owned),
            "device_count": len(devices),
            "identity_doc_count": len(id_docs),
            "community": community_of,
        },
        "products_owned": [_product_view(p) for p in sorted(owned)],
        "connected_products": [_product_view(p) for p in sorted(connected)
                               if et(p) not in (EntityType.CASH_ENDPOINT,)],
        "device_intelligence": [d for d in cr["devices"] if d["entity"] in devices] or
                               [{"entity": d, "risk_level": "LOW"} for d in devices],
        "identity_intelligence": [i for i in cr["identities"] if i["entity"] in id_docs] or
                                 [{"entity": i, "risk_level": "LOW"} for i in id_docs],
        "merchant_relationships": [m for m in cr["merchants"] if m["entity"] in merchants] or
                                  [{"entity": m, "risk_level": "LOW"} for m in merchants],
        "cross_product": {
            "is_cross_product": cp["is_cross_product"],
            "product_categories": cp["product_categories"],
            "xp_rules": [{"xp_id": s["xp_id"], "name": s["name"], "severity": s["severity"]}
                         for s in cp["xp_signals"]],
            "matched_typologies": [t["label"] for t in cp["matched_typologies"]],
        },
        "money_trails": {
            "summary": flows.get("summary_narrative"),
            "most_layered": flows.get("most_layered"),
            "cashout_routes": flows.get("cashout_routes", []),
        },
        "fraud_motifs": [{"pattern": m["pattern"], "label": m["label"], "severity": m["severity"]}
                         for m in motifs[:8]],
        "timeline": timeline,
        "community_membership": community_of,
        "customer_risk": cust_risk,
        "recommendations": cp["recovery_actions"],
        "regulatory_hooks": cp["regulatory_hooks"],
        "narrative": narrative,
    }
