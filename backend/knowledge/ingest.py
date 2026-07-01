"""
Heterogeneous ingestion augmenter (live cross-product wiring).

The live session keeps a MONEY-ONLY transaction graph (so the rendered frontend
is unchanged). Optional product/ownership/identity context supplied at ingestion
is recorded separately in a per-session `entity_context`. This module merges that
context into a transaction component ON DEMAND — typing the nodes and appending
OWNS / HAS_DEVICE / HAS_PHONE / HAS_PAN structural edges — to produce the
heterogeneous component the XP detectors, customer-risk graph and investigation
report consume. Degrades gracefully: with no context, the component passes
through unchanged (id-prefix classification still applies).

entity_context shape (account-anchored, JSON-serialisable):
    {
      "types":  { node_id: entity_type },        # explicit type hints
      "owns":   { account_id: customer_id },      # account → owning customer
      "links":  [ [account_id, identity_id, rel] ]  # rel ∈ HAS_DEVICE/HAS_PHONE/HAS_PAN…
    }
"""
from __future__ import annotations

from typing import Any


def empty_context() -> dict[str, Any]:
    return {"types": {}, "owns": {}, "links": []}


def record_account(ctx: dict[str, Any], account: str, *, entity_type: str | None = None,
                   customer: str | None = None, phone: str | None = None,
                   pan: str | None = None, device: str | None = None,
                   bank: str | None = None) -> None:
    """Record optional cross-product context for one account (idempotent)."""
    if entity_type:
        ctx["types"][account] = entity_type
    if customer:
        ctx["owns"][account] = customer
        ctx["types"].setdefault(customer, "customer")
    if bank:
        ctx.setdefault("banks", {})[account] = bank  # cross-bank intelligence (additive key)
    links = ctx["links"]
    if device and [account, device, "HAS_DEVICE"] not in links:
        links.append([account, device, "HAS_DEVICE"])
        ctx["types"].setdefault(device, "device")
    if phone:
        pid = phone if str(phone).upper().startswith("PHONE") else f"PHONE_{phone}"
        if [account, pid, "HAS_PHONE"] not in links:
            links.append([account, pid, "HAS_PHONE"])
            ctx["types"].setdefault(pid, "mobile_number")
    if pan:
        pid = pan if str(pan).upper().startswith("PAN") else f"PAN_{pan}"
        if [account, pid, "HAS_PAN"] not in links:
            links.append([account, pid, "HAS_PAN"])
            ctx["types"].setdefault(pid, "pan")


def augment_component(component: dict, ctx: dict[str, Any] | None) -> dict:
    """
    Merge per-session entity context into a money-only transaction component,
    producing a heterogeneous component. Never mutates the input. With no
    context (or none relevant), returns an equivalent component unchanged.
    """
    if not ctx or (not ctx.get("types") and not ctx.get("owns") and not ctx.get("links")):
        return component

    nodes = [dict(n) for n in (component.get("nodes")
             or [{"id": n} for n in component.get("node_ids", [])])]
    present = {str(n.get("id")) for n in nodes}
    edges = [dict(e) for e in component.get("edges", [])]
    types = ctx.get("types", {})

    # type the existing transaction nodes
    for n in nodes:
        t = types.get(str(n.get("id")))
        if t:
            n["entity_type"] = t

    added = set(present)

    def ensure(nid: str) -> None:
        if nid not in added:
            node = {"id": nid}
            if nid in types:
                node["entity_type"] = types[nid]
            nodes.append(node)
            added.add(nid)

    # ownership: customer OWNS account (account must be in this component)
    for account, customer in ctx.get("owns", {}).items():
        if account in present:
            ensure(customer)
            edges.append({"source": customer, "target": account, "relationship_type": "OWNS"})

    # identity links: account HAS_* identity (anchored to a component account)
    for account, ident, rel in ctx.get("links", []):
        if account in present:
            ensure(ident)
            edges.append({"source": account, "target": ident, "relationship_type": rel})

    return {
        "graph_id": component.get("graph_id", "GRAPH_001"),
        "node_ids": [str(n["id"]) for n in nodes],
        "nodes": nodes,
        "edges": edges,
    }
