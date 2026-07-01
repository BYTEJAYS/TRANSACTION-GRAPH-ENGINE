"""
Precompute job — moves expensive graph metrics OFF the request thread.

Computes centrality + community for a component and returns them keyed by node
(in the live flow these are written back as node properties so requests READ
precomputed values instead of recomputing O(V·E) each time). Reuses the V2
graph builder. Registered as a task so it can run inline or via Celery.
"""
from __future__ import annotations

from typing import Any

from core.tasks import task


@task("precompute_centrality")
def precompute_centrality(component: dict) -> dict[str, dict[str, float]]:
    from blue_team_v2.core.graph_engine.builder import TransactionGraph
    tg = TransactionGraph(component)
    return tg.centralities()


@task("precompute_community")
def precompute_community(component: dict) -> dict[str, int]:
    import networkx as nx
    from blue_team_v2.core.graph_engine.builder import TransactionGraph
    tg = TransactionGraph(component)
    ug = tg.G.to_undirected()
    try:
        comms = nx.community.greedy_modularity_communities(ug)
    except Exception:
        comms = [set(ug.nodes())]
    out: dict[str, int] = {}
    for cid, members in enumerate(comms):
        for n in members:
            out[n] = cid
    return out
