"""
Neo4j access for the service/repository layer.

Thin re-export of the Phase 2 client (graph/schema/client.py) so all DB access
imports live under core.db.* uniformly. `available()` mirrors the others.
"""
from __future__ import annotations

from graph.schema.client import get_client, Neo4jClient  # noqa: F401


def client() -> Neo4jClient:
    return get_client()


def available() -> bool:
    return get_client().available()
