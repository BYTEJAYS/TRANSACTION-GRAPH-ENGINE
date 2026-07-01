"""
Mule Account / Mule-Network detector.

A money mule receives funds and rapidly forwards most of them onward, retaining
little. We flag individual mules and, when several chain together, the mule
network they form.
"""
from __future__ import annotations

from ...types import Evidence, ClusterRole

NAME = "mule_accounts"


def detect(tg, metrics, meta) -> list[Evidence]:
    MIN_MULE_VOLUME = 50_000  # mules move material value, not pocket change
    mules: list[str] = []
    for node, m in metrics.items():
        if m.fan_in_count >= 1 and m.fan_out_count >= 1 and m.pass_through_ratio >= 0.6:
            in_v = m.incoming_volume
            out_v = m.outgoing_volume
            # forwards the bulk of received funds, and moves material value
            if in_v >= MIN_MULE_VOLUME and out_v >= 0.6 * in_v:
                mules.append(node)

    if not mules:
        return []

    evidence: list[Evidence] = []
    # connected mule chains
    mule_set = set(mules)
    visited: set[str] = set()
    networks: list[list[str]] = []
    for mn in mules:
        if mn in visited:
            continue
        stack, comp = [mn], []
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            comp.append(cur)
            for nb in list(tg.G.successors(cur)) + list(tg.G.predecessors(cur)):
                if nb in mule_set and nb not in visited:
                    stack.append(nb)
        networks.append(comp)

    for comp in networks:
        if len(comp) >= 2:
            value = sum(metrics[n].incoming_volume for n in comp)
            evidence.append(Evidence(
                pattern=NAME,
                title=f"Mule network of {len(comp)} accounts",
                description=(
                    f"{len(comp)} accounts each forward ≥60% of received funds onward, "
                    f"chaining into a mule network that relayed ₹{value:,.0f}. "
                    f"Such chains exist to break the link between source and cash-out."
                ),
                nodes=comp,
                severity=min(0.95, 0.7 + 0.05 * len(comp)),
                confidence=0.88,
                data={"mules": comp, "relayed_volume": round(value, 2)},
            ))
        else:
            n = comp[0]
            evidence.append(Evidence(
                pattern=NAME,
                title=f"Money mule: {n}",
                description=(
                    f"Account {n} received ₹{metrics[n].incoming_volume:,.0f} and forwarded "
                    f"{metrics[n].pass_through_ratio:.0%} of it onward almost immediately — "
                    f"behaviour consistent with a single money mule."
                ),
                nodes=[n] + list(tg.G.successors(n))[:5],
                severity=0.66,
                confidence=0.8,
                data={"mule": n, "pass_through": metrics[n].pass_through_ratio},
            ))
    return evidence
