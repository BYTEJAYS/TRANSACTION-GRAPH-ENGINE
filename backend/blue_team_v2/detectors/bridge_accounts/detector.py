"""
Bridge Account / Bridge-Network detector.

A bridge is an articulation point: remove it and the cluster splits. Launderers
use bridges to connect a collection sub-network to a distribution/cash-out
sub-network while keeping a single controllable choke point.
"""
from __future__ import annotations

import networkx as nx

from ...types import Evidence

NAME = "bridge_accounts"
MIN_THROUGH = 100_000   # a laundering bridge funnels material value
MAX_CANDIDATES = 40     # bound the expensive fragmentation analysis on big graphs


def detect(tg, metrics, meta) -> list[Evidence]:
    if tg.num_nodes() < 4:
        return []
    cut_points = tg.articulation_points()
    if not cut_points:
        return []

    # Cheap pre-filter FIRST: a real bridge has in+out flow and material value.
    # This collapses thousands of trivial cut points (common on sparse graphs)
    # down to a handful before any graph copy, keeping the detector O(candidates).
    candidates = []
    for node in cut_points:
        m = metrics.get(node)
        if not m or m.fan_in_count == 0 or m.fan_out_count == 0:
            continue
        if m.incoming_volume < MIN_THROUGH:
            continue
        candidates.append(node)
    if not candidates:
        return []
    # examine the strongest first, capped
    candidates.sort(key=lambda x: metrics[x].betweenness_centrality, reverse=True)
    candidates = candidates[:MAX_CANDIDATES]

    evidence: list[Evidence] = []
    UG = tg.G.to_undirected()
    for node in candidates:
        m = metrics[node]
        # how badly does removing it fragment the cluster?
        H = UG.copy()
        H.remove_node(node)
        frags = nx.number_connected_components(H) if H.number_of_nodes() else 1
        if frags < 2:
            continue
        sizes = sorted((len(c) for c in nx.connected_components(H)), reverse=True)
        through = m.incoming_volume
        severity = min(0.95, 0.55 + 0.08 * frags + 0.2 * min(1.0, m.betweenness_centrality * 2))
        evidence.append(Evidence(
            pattern=NAME,
            title=f"Bridge account splitting cluster into {frags}",
            description=(
                f"Account {node} is the sole link between {frags} sub-networks "
                f"(sizes {sizes[:4]}). ₹{through:,.0f} of value funnels through this single "
                f"choke point — controlling it controls the whole laundering pipeline."
            ),
            nodes=[node],
            severity=severity,
            confidence=0.84,
            data={"bridge": node, "fragments": frags, "fragment_sizes": sizes,
                  "betweenness": m.betweenness_centrality},
        ))
    return evidence
