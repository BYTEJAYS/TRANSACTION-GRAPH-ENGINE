"""
Cash-deposit laundering detector.

Cash enters the banking system (CASH_IN / CASH deposit) and is forwarded onward
almost immediately, breaking the link between physical cash and its destination.
Signature: a node with material cash-in inflow that it promptly pushes out via
electronic rails. (Withdrawal-side cash-out is handled by the `cashout` detector.)
"""
from __future__ import annotations

from ...types import Evidence

NAME = "cash_laundering"
CASH_IN_RAILS = ("CASH_IN", "CASH")
MIN_CASH_IN = 1_00_000
MIN_FORWARD_RATIO = 0.5   # at least half the cash-in is forwarded onward


def detect(tg, metrics, meta) -> list[Evidence]:
    evidence: list[Evidence] = []
    for node in tg.nodes:
        cash_in = 0.0
        cash_sources = []
        for p, _, d in tg.G.in_edges(node, data=True):
            if any(r in d.get("rails", []) for r in CASH_IN_RAILS):
                cash_in += d["amount"]
                cash_sources.append(p)
        if cash_in < MIN_CASH_IN:
            continue
        out_v = tg.out_volume(node)
        forward_ratio = out_v / cash_in if cash_in else 0.0
        if forward_ratio < MIN_FORWARD_RATIO:
            continue
        dests = list(tg.G.successors(node))[:10]
        sev = min(0.95, 0.66 + 0.2 * min(1.0, forward_ratio) + 0.0000005 * cash_in)
        evidence.append(Evidence(
            pattern=NAME,
            title=f"Cash-deposit laundering (₹{cash_in:,.0f} placed then forwarded)",
            description=(
                f"Account {node} received ₹{cash_in:,.0f} in cash deposits and promptly forwarded "
                f"{forward_ratio:.0%} of it onward electronically to {len(dests)} accounts. Placing "
                f"cash and immediately moving it severs the trail between physical cash and its "
                f"ultimate destination — the placement stage of laundering."
            ),
            nodes=[node, *dests],
            severity=min(0.95, sev),
            confidence=0.8,
            data={"node": node, "cash_in": round(cash_in, 2), "forwarded": round(out_v, 2),
                  "forward_ratio": round(forward_ratio, 3)},
        ))
    return evidence
