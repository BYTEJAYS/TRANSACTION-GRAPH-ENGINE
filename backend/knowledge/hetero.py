"""
Heterogeneous graph builder (Phase 1 — ingestion).

The live engine ingests only Account→Transaction→Account. This builder lets a
caller assemble a HETEROGENEOUS financial graph — customers that OWN products,
accounts that HAS_DEVICE / HAS_PAN identities, transactions across products —
and emit it as the SAME component dict (`{graph_id, nodes, edges}`) the existing
analysis pipeline (cross_product_report, motif/case engines) already consumes.
So heterogeneous data flows through everything additively, no engine rewrite.

Edge kinds:
  * transaction edges — carry amount + payment_rail (+ device_id/timestamp)
  * structural edges  — carry a relationship_type only (OWNS, HAS_DEVICE,
    HAS_PHONE, HAS_PAN, BENEFICIARY_OF …); no money moves along them.
"""
from __future__ import annotations

from typing import Any

from .entities import EntityType, RelationshipType

# relationship types that move money (everything else is structural/identity)
TRANSACTION_RELS = {
    RelationshipType.TRANSFERRED.value, RelationshipType.PAID.value,
    RelationshipType.WITHDREW.value, RelationshipType.DEPOSITED.value,
}


def is_transaction_edge(edge: dict[str, Any]) -> bool:
    """A money-moving edge — has an amount/rail, or an explicit transaction rel."""
    rel = edge.get("relationship_type")
    if rel is not None:
        return rel in TRANSACTION_RELS
    return float(edge.get("amount", 0) or 0) > 0 or bool(edge.get("payment_rail"))


class HeteroGraph:
    """Accumulates typed entities + typed edges → standard component dict."""

    def __init__(self, graph_id: str = "GRAPH_001") -> None:
        self.graph_id = graph_id
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: list[dict[str, Any]] = []

    # ── entities ──
    def add_entity(self, node_id: str, entity_type: EntityType | str, **attrs: Any) -> str:
        et = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
        node = self._nodes.setdefault(node_id, {"id": node_id})
        node["entity_type"] = et
        node.update(attrs)
        return node_id

    def customer(self, cid: str, **attrs: Any) -> str:
        return self.add_entity(cid, EntityType.CUSTOMER, **attrs)

    def product(self, pid: str, entity_type: EntityType, owner: str | None = None, **attrs: Any) -> str:
        self.add_entity(pid, entity_type, **attrs)
        if owner:
            self.owns(owner, pid)
        return pid

    def identity(self, iid: str, entity_type: EntityType, **attrs: Any) -> str:
        return self.add_entity(iid, entity_type, **attrs)

    # ── structural edges ──
    def link(self, source: str, target: str, rel: RelationshipType, **attrs: Any) -> None:
        for nid in (source, target):
            self._nodes.setdefault(nid, {"id": nid})
        self._edges.append({"source": source, "target": target,
                            "relationship_type": rel.value, **attrs})

    def owns(self, customer_id: str, product_id: str) -> None:
        self.link(customer_id, product_id, RelationshipType.OWNS)

    def has_device(self, account_id: str, device_id: str) -> None:
        self.identity(device_id, EntityType.DEVICE)
        self.link(account_id, device_id, RelationshipType.HAS_DEVICE)

    def has_phone(self, owner_id: str, phone_id: str) -> None:
        self.identity(phone_id, EntityType.MOBILE)
        self.link(owner_id, phone_id, RelationshipType.HAS_PHONE)

    def has_pan(self, owner_id: str, pan_id: str) -> None:
        self.identity(pan_id, EntityType.PAN)
        self.link(owner_id, pan_id, RelationshipType.HAS_PAN)

    # ── transaction edges ──
    def transfer(self, source: str, target: str, amount: float, rail: str = "UPI",
                 timestamp: str = "", device_id: str = "", **attrs: Any) -> None:
        for nid in (source, target):
            self._nodes.setdefault(nid, {"id": nid})
        self._edges.append({
            "source": source, "target": target,
            "relationship_type": RelationshipType.TRANSFERRED.value,
            "amount": float(amount), "payment_rail": rail,
            "timestamp": timestamp, "device_id": device_id, **attrs,
        })

    # ── output ──
    def component(self) -> dict[str, Any]:
        """The standard component dict the existing analysis pipeline consumes."""
        return {
            "graph_id": self.graph_id,
            "node_ids": list(self._nodes),
            "nodes": list(self._nodes.values()),
            "edges": list(self._edges),
        }
