"""
Velocity / Burst-Transaction detector.

Flags accounts (and the whole cluster) moving large value in a very short
window, and nodes whose inter-arrival pattern is highly bursty.
"""
from __future__ import annotations

from ...types import Evidence

NAME = "velocity"


def detect(tg, metrics, meta) -> list[Evidence]:
    evidence: list[Evidence] = []

    # ── per-node high velocity ──
    for node, m in metrics.items():
        if m.transaction_velocity >= 0.5 and (m.incoming_volume + m.outgoing_volume) >= 200_000:
            evidence.append(Evidence(
                pattern=NAME,
                title=f"High-velocity throughput: {node}",
                description=(
                    f"Account {node} moved ₹{m.incoming_volume + m.outgoing_volume:,.0f} at a "
                    f"compressed throughput (velocity index {m.transaction_velocity:.2f}). "
                    f"Rapid in-and-out movement is a strong layering/mule indicator."
                ),
                nodes=[node],
                severity=min(0.9, 0.5 + 0.4 * m.transaction_velocity),
                confidence=0.8,
                data={"velocity_index": m.transaction_velocity},
            ))

    # ── per-node burst ──
    for node, m in metrics.items():
        if m.burst_activity >= 0.7 and m.transaction_frequency >= 4:
            evidence.append(Evidence(
                pattern=NAME,
                title=f"Burst activity: {node}",
                description=(
                    f"Account {node} shows highly clustered transaction timing "
                    f"(burstiness {m.burst_activity:.2f} over {m.transaction_frequency} txns) — "
                    f"consistent with an automated dispersal event."
                ),
                nodes=[node],
                severity=min(0.85, 0.45 + 0.4 * m.burst_activity),
                confidence=0.74,
                data={"burstiness": m.burst_activity, "txns": m.transaction_frequency},
            ))

    # ── whole-cluster velocity gate ──
    times = tg.all_timestamps()
    if len(times) >= 3:
        span = (times[-1] - times[0]).total_seconds()
        total = sum(d["amount"] for _, _, d in tg.G.edges(data=True))
        if 0 < span <= 600 and total >= 500_000:
            evidence.append(Evidence(
                pattern=NAME,
                title="Cluster-wide burst dispersal",
                description=(
                    f"The entire cluster moved ₹{total:,.0f} within {span/60:.1f} minutes — "
                    f"an orchestrated rapid-dispersal event across multiple accounts."
                ),
                nodes=tg.nodes[:20],
                severity=0.82,
                confidence=0.86,
                data={"window_seconds": span, "total_volume": round(total, 2)},
            ))
    return evidence
