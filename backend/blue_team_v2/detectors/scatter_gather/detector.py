"""
Scatter-gather detector.

The classic mule-network signature: funds are GATHERED from many sources into a
relay (fan-in) and then SCATTERED to many destinations (fan-out), with the relay
retaining little (high pass-through). Detecting the combined in→relay→out shape
in one node is stronger evidence than fan-in or fan-out alone.
"""
from __future__ import annotations

from ...types import Evidence

NAME = "scatter_gather"
MIN_SOURCES = 3
MIN_DESTS = 3
MIN_PASS_THROUGH = 0.5
MIN_VALUE = 1_00_000


def detect(tg, metrics, meta) -> list[Evidence]:
    evidence: list[Evidence] = []
    for node in tg.nodes:
        preds = list(tg.G.predecessors(node))
        succ = list(tg.G.successors(node))
        if len(preds) < MIN_SOURCES or len(succ) < MIN_DESTS:
            continue
        in_v, out_v = tg.in_volume(node), tg.out_volume(node)
        if min(in_v, out_v) < MIN_VALUE:
            continue
        m = metrics.get(node)
        ptr = m.pass_through_ratio if m else (min(in_v, out_v) / max(in_v, out_v) if max(in_v, out_v) else 0)
        if ptr < MIN_PASS_THROUGH:
            continue
        sev = min(0.97, 0.68 + 0.03 * (len(preds) + len(succ) - MIN_SOURCES - MIN_DESTS) + 0.15 * ptr)
        evidence.append(Evidence(
            pattern=NAME,
            title=f"Scatter-gather relay ({len(preds)}→1→{len(succ)})",
            description=(
                f"Relay {node} gathered ₹{in_v:,.0f} from {len(preds)} sources and scattered "
                f"₹{out_v:,.0f} to {len(succ)} destinations, retaining almost nothing "
                f"(pass-through {ptr:.0%}). Collect-then-disperse through a thin relay is the "
                f"core mechanic of a money-mule network."
            ),
            nodes=[node, *preds[:8], *succ[:8]],
            severity=sev,
            confidence=0.85,
            data={"relay": node, "sources": len(preds), "destinations": len(succ),
                  "in_volume": round(in_v, 2), "out_volume": round(out_v, 2),
                  "pass_through": round(ptr, 3)},
        ))
    return evidence
