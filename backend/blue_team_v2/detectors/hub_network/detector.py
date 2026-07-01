"""
Hub network detector.

A single account acting as a high-degree exchange — large numbers of distinct
counterparties on BOTH the inbound and outbound side, with material throughput.
Unlike fan-in (collection) or fan-out (distribution) alone, a hub does both: the
central switchboard of a mule network.
"""
from __future__ import annotations

from ...types import Evidence

NAME = "hub_network"
MIN_DEGREE_EACH = 4
MIN_THROUGHPUT = 2_00_000


def detect(tg, metrics, meta) -> list[Evidence]:
    evidence: list[Evidence] = []
    for node in tg.nodes:
        in_deg = tg.G.in_degree(node)
        out_deg = tg.G.out_degree(node)
        if in_deg < MIN_DEGREE_EACH or out_deg < MIN_DEGREE_EACH:
            continue
        throughput = min(tg.in_volume(node), tg.out_volume(node))
        if throughput < MIN_THROUGHPUT:
            continue
        m = metrics.get(node)
        centrality = m.degree_centrality if m else 0.0
        sev = min(0.96, 0.64 + 0.03 * (min(in_deg, out_deg) - MIN_DEGREE_EACH) + 0.2 * centrality)
        preds = list(tg.G.predecessors(node))[:10]
        succ = list(tg.G.successors(node))[:10]
        evidence.append(Evidence(
            pattern=NAME,
            title=f"Hub account ({in_deg} in / {out_deg} out)",
            description=(
                f"Account {node} exchanges with {in_deg} distinct senders and {out_deg} distinct "
                f"recipients (₹{throughput:,.0f} throughput) — a high-degree hub sitting at the "
                f"centre of a network. Hubs concentrate and redistribute illicit flow and are "
                f"prime mule-network controllers."
            ),
            nodes=[node, *preds, *succ],
            severity=sev,
            confidence=0.83,
            data={"hub": node, "in_degree": in_deg, "out_degree": out_deg,
                  "throughput": round(throughput, 2), "degree_centrality": round(centrality, 3)},
        ))
    return evidence
