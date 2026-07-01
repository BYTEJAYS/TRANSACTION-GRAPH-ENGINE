"""Circular Flow detector — funds that return to an earlier account (cycles)."""
from __future__ import annotations

from ...types import Evidence

NAME = "circular_flow"


def detect(tg, metrics, meta) -> list[Evidence]:
    MIN_LOOP_VALUE = 50_000  # a meaningful loop, not two friends settling lunch
    cycles = [c for c in tg.cycles() if len(c) >= 2]
    if not cycles:
        return []
    evidence: list[Evidence] = []
    for cyc in cycles[:8]:
        # recover the looped value along the cycle edges
        looped = 0.0
        for i in range(len(cyc)):
            a, b = cyc[i], cyc[(i + 1) % len(cyc)]
            if tg.G.has_edge(a, b):
                looped += tg.G[a][b]["amount"]
        if looped < MIN_LOOP_VALUE:
            continue
        evidence.append(Evidence(
            pattern=NAME,
            title=f"Circular fund flow ({len(cyc)} hops)",
            description=(
                f"Funds traverse a closed loop of {len(cyc)} accounts and return "
                f"to the origin — a hallmark of layering used to obscure the audit "
                f"trail. ₹{looped:,.0f} cycled through the loop."
            ),
            nodes=list(cyc),
            severity=min(0.99, 0.80 + 0.04 * len(cyc)),
            confidence=0.93,
            data={"cycle": list(cyc), "length": len(cyc), "looped_amount": round(looped, 2)},
        ))
    return evidence
