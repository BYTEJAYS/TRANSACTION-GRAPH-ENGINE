"""
Layering / Multi-Hop laundering detector.

Detects long forwarding chains where value passes through a series of
pass-through accounts, each retaining little, to distance funds from origin.
"""
from __future__ import annotations

from ...types import Evidence

NAME = "layering"
MIN_DEPTH = 4
MIN_HOP_AMOUNT = 25_000   # layering moves material value down the chain


def detect(tg, metrics, meta) -> list[Evidence]:
    chain = meta.get("chain") or tg.longest_chain()
    if len(chain) < MIN_DEPTH:
        return []

    # monetary gate: the chain must carry material value at each hop
    hop_amounts = [tg.G[chain[i]][chain[i + 1]]["amount"]
                   for i in range(len(chain) - 1) if tg.G.has_edge(chain[i], chain[i + 1])]
    if not hop_amounts or (sum(hop_amounts) / len(hop_amounts)) < MIN_HOP_AMOUNT:
        return []

    # count how many chain interior nodes are pass-through relays
    relays = 0
    for node in chain[1:-1]:
        m = metrics.get(node)
        if m and m.pass_through_ratio >= 0.5 and m.fan_in_count >= 1 and m.fan_out_count >= 1:
            relays += 1

    depth = len(chain)
    if relays < max(1, (depth - 2) // 2):
        # long path but not really relaying value — weaker / skip
        if relays == 0:
            return []

    severity = min(0.97, 0.66 + 0.04 * (depth - MIN_DEPTH) + 0.03 * relays)
    return [Evidence(
        pattern=NAME,
        title=f"Layering chain depth {depth}",
        description=(
            f"A {depth}-hop forwarding chain moves funds through {relays} pass-through "
            f"relay accounts before settling — each hop strips the audit trail. "
            f"Chain: {' → '.join(chain[:8])}{' → …' if depth > 8 else ''}."
        ),
        nodes=list(chain),
        severity=severity,
        confidence=0.88,
        data={"chain": chain, "depth": depth, "relay_nodes": relays},
    )]
