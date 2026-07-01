"""Fan-Out detector — one account distributing to many recipients (smurf-out)."""
from __future__ import annotations

from ...types import Evidence

NAME = "fan_out"
THRESHOLD = 4
MIN_AVG_AMOUNT = 25_000     # below this, fan-out looks like ordinary bill paying
MIN_OUT_VOLUME = 150_000    # total dispersed value must be material


def detect(tg, metrics, meta) -> list[Evidence]:
    evidence: list[Evidence] = []
    for node in tg.nodes:
        succ = list(tg.G.successors(node))
        if len(succ) < THRESHOLD:
            continue
        out_v = tg.out_volume(node)
        amts = [tg.G[node][s]["amount"] for s in succ]
        avg = out_v / len(succ) if succ else 0
        # monetary significance gate — benign multi-payee activity is not fraud
        if out_v < MIN_OUT_VOLUME or avg < MIN_AVG_AMOUNT:
            continue
        uniformity = 1.0 - (max(amts) - min(amts)) / max(amts) if amts and max(amts) > 0 else 0
        severity = min(0.97, 0.62 + 0.05 * (len(succ) - THRESHOLD) + 0.15 * uniformity)
        evidence.append(Evidence(
            pattern=NAME,
            title=f"Fan-out to {len(succ)} accounts",
            description=(
                f"Account {node} pushed ₹{out_v:,.0f} out to {len(succ)} distinct "
                f"recipients (avg ₹{avg:,.0f}). High split-uniformity ({uniformity:.0%}) "
                f"indicates deliberate distribution to mules rather than organic payments."
            ),
            nodes=[node] + succ[:12],
            severity=severity,
            confidence=0.86,
            data={"hub": node, "recipients": len(succ), "out_volume": round(out_v, 2),
                  "uniformity": round(uniformity, 3)},
        ))
    return evidence
