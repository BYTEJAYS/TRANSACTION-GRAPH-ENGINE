"""
EntityContext — bridges the Phase 2 entity graph (shared device/PAN/IP/…) into
the detector contract, WITHOUT changing the detector signature.

It is attached to `meta["entity_ctx"]` by the engine when the persistent graph
is available (TGIE_PERSIST=db + Neo4j up). On today's data it is None, so the
Wave-2 identity-ring detectors that depend on it return [] (graceful no-op).

This module defines the contract now (Phase 4) so Wave-2 detectors can be
written against a stable shape; the live builder is wired in Phase 4 Wave 2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EntityContext:
    """Shared-identity adjacency for the accounts in the current component.

    `shared[basis]` maps an account id → the set of *other* account ids that
    collide with it on that identity basis (device/ip/phone/email/address/pan/
    aadhaar/employer). Built from the SHARES_*/SAME_* derived edges (Phase 2 §5).
    """
    shared: dict[str, dict[str, set[str]]] = field(default_factory=dict)
    # account_id → {"customer_id":..., "kyc_level":..., "declared_income":..., "occupation":...}
    profiles: dict[str, dict] = field(default_factory=dict)

    def collisions(self, account_id: str, basis: str) -> set[str]:
        return self.shared.get(account_id, {}).get(basis, set())

    def any_collisions(self, account_id: str) -> dict[str, set[str]]:
        return self.shared.get(account_id, {})


def build_entity_context(component_node_ids: list[str]) -> Optional[EntityContext]:
    """Return an EntityContext from Neo4j for the given accounts, or None if the
    persistent graph isn't available (json mode / Neo4j down) — callers no-op."""
    try:
        from core.settings import data_settings
        if not data_settings.db_mode:
            return None
        from core.db import neo4j
        if not neo4j.available():
            return None
    except Exception:
        return None

    BASES = {
        "device": "SHARES_DEVICE", "ip": "SHARES_IP", "phone": "SHARES_PHONE",
        "email": "SHARES_EMAIL", "address": "SHARES_ADDRESS", "pan": "SAME_PAN",
        "aadhaar": "SAME_AADHAAR", "employer": "SAME_EMPLOYER",
    }
    from core.db import neo4j
    client = neo4j.client()
    shared: dict[str, dict[str, set[str]]] = {}
    for basis, rel in BASES.items():
        rows = client.read(
            f"MATCH (a:Account)-[:{rel}]-(b:Account) "
            "WHERE a.id IN $ids RETURN a.id AS a, b.id AS b",
            {"ids": component_node_ids},
        )
        for r in rows:
            shared.setdefault(r["a"], {}).setdefault(basis, set()).add(r["b"])
    return EntityContext(shared=shared)
