"""Fan-In detector — many accounts funnelling into one collector (smurf-in)."""
from __future__ import annotations

from ...types import Evidence

NAME = "fan_in"
THRESHOLD = 4
MIN_AVG_AMOUNT = 25_000
MIN_IN_VOLUME = 150_000


def detect(tg, metrics, meta) -> list[Evidence]:
    evidence: list[Evidence] = []
    for node in tg.nodes:
        pred = list(tg.G.predecessors(node))
        if len(pred) < THRESHOLD:
            continue
        in_v = tg.in_volume(node)
        out_v = tg.out_volume(node)
        avg = in_v / len(pred) if pred else 0
        # monetary significance gate
        if in_v < MIN_IN_VOLUME or avg < MIN_AVG_AMOUNT:
            continue
        forwards = out_v > 0.5 * in_v        # collector that re-forwards = stronger signal
        severity = min(0.96, 0.60 + 0.05 * (len(pred) - THRESHOLD) + (0.12 if forwards else 0))
        evidence.append(Evidence(
            pattern=NAME,
            title=f"Fan-in from {len(pred)} accounts",
            description=(
                f"Collector {node} aggregated ₹{in_v:,.0f} from {len(pred)} distinct "
                f"senders" + (f" and forwarded ₹{out_v:,.0f} onward — a classic "
                f"collection-then-layering node." if forwards else ", behaving as a sink/collector.")
            ),
            nodes=[node] + pred[:12],
            severity=severity,
            confidence=0.85,
            data={"collector": node, "senders": len(pred), "in_volume": round(in_v, 2),
                  "forwards": forwards},
        ))
    return evidence
