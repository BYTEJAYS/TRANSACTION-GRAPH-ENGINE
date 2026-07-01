"""
Graph repository — reads the Neo4j knowledge graph and projects bounded
subgraphs into NetworkX for viz/detectors (the preserved fast path).

db mode: query Neo4j around a seed account (n-hop neighbourhood), cache in Redis.
json mode: returns None so callers keep using the legacy in-memory graph_manager.
"""
from __future__ import annotations

from typing import Any, Optional

from core.settings import data_settings


async def neighbourhood(account_id: str, hops: int = 2, limit: int = 500) -> Optional[dict]:
    """Return {nodes, edges} around an account, or None in json mode."""
    if not data_settings.db_mode:
        return None
    from core.db import neo4j
    if not neo4j.available():
        return None
    hops = max(1, min(hops, 4))
    rows = neo4j.client().read(
        f"MATCH p=(a:Account {{id:$id}})-[:TRANSFERRED_TO*1..{hops}]-(b:Account) "
        "WITH nodes(p) AS ns, relationships(p) AS rs LIMIT $lim "
        "UNWIND ns AS n WITH collect(DISTINCT n) AS nodes, rs "
        "UNWIND rs AS r RETURN nodes, collect(DISTINCT r) AS rels",
        {"id": account_id, "lim": limit},
    )
    if not rows:
        return {"nodes": [], "edges": []}
    rec = rows[0]
    nodes = [{"id": n.get("id"), **{k: v for k, v in n.items()}} for n in rec.get("nodes", [])]
    edges = [{"source": r.get("source"), "target": r.get("target")} for r in rec.get("rels", [])]
    return {"nodes": nodes, "edges": edges}


def project_to_networkx(subgraph: dict) -> Any:
    """Build an nx.DiGraph from a {nodes,edges} dict so detectors run unchanged."""
    import networkx as nx
    g = nx.DiGraph()
    for n in subgraph.get("nodes", []):
        g.add_node(n["id"], **n)
    for e in subgraph.get("edges", []):
        if e.get("source") and e.get("target"):
            g.add_edge(e["source"], e["target"])
    return g
