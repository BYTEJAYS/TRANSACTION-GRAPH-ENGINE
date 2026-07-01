"""
Pattern Engine — runs the full detector library against a component, collects
evidence, and writes pattern participation back into the node metrics so the
scoring engine can reward nodes that appear in multiple independent patterns.

It also synthesises a "hybrid fraud network" finding when several distinct
pattern families co-occur in the same cluster — the signature of a professional
laundering operation rather than a one-off.
"""
from __future__ import annotations

from ...detectors.bridge_accounts import detector as bridge
from ...detectors.cashout import detector as cashout
from ...detectors.circular_flow import detector as circular
from ...detectors.dormant_accounts import detector as dormant
from ...detectors.fan_in import detector as fan_in
from ...detectors.fan_out import detector as fan_out
from ...detectors.layering import detector as layering
from ...detectors.mule_accounts import detector as mule
from ...detectors.smurfing import detector as smurfing
from ...detectors.synthetic_networks import detector as synthetic
from ...detectors.velocity import detector as velocity
# ── Phase 4 Wave 1 — topology detectors (operate on the transaction graph) ──
from ...detectors.diamond import detector as diamond
from ...detectors.nested_layering import detector as nested_layering
from ...detectors.round_tripping import detector as round_tripping
from ...detectors.hub_network import detector as hub_network
from ...detectors.scatter_gather import detector as scatter_gather
from ...detectors.structuring import detector as structuring
from ...detectors.cash_laundering import detector as cash_laundering
from ...detectors.night_activity import detector as night_activity
from ...detectors.weekend_activity import detector as weekend_activity
from ...detectors.temporal_spike import detector as temporal_spike
from ...detectors.uniform_amount import detector as uniform_amount
from ...types import Evidence, NodeMetrics

# Ordered registry — every detector module exposes NAME + detect()
DETECTORS = [
    circular, layering, smurfing, fan_out, fan_in,
    mule, bridge, velocity, cashout, dormant, synthetic,
    # Phase 4 Wave 1 additions:
    diamond, nested_layering, round_tripping, hub_network, scatter_gather,
    structuring, cash_laundering, night_activity, weekend_activity,
    temporal_spike, uniform_amount,
]


class PatternEngine:
    def run(self, tg, metrics: dict[str, NodeMetrics], meta: dict) -> list[Evidence]:
        evidence: list[Evidence] = []
        for det in DETECTORS:
            try:
                found = det.detect(tg, metrics, meta)
            except Exception as exc:  # a detector must never crash the pipeline
                import logging
                logging.getLogger(__name__).debug("detector %s failed: %s", det.NAME, exc)
                found = []
            evidence.extend(found)

        # write participation back into metrics
        per_node_patterns: dict[str, set[str]] = {n: set() for n in metrics}
        for ev in evidence:
            for node in ev.nodes:
                if node in per_node_patterns:
                    per_node_patterns[node].add(ev.pattern)
        for node, pats in per_node_patterns.items():
            metrics[node].pattern_participation = len(pats)
            metrics[node].patterns = sorted(pats)

        # ── hybrid meta-detector ──
        families = {ev.pattern for ev in evidence}
        if len(families) >= 3:
            involved = sorted({n for ev in evidence for n in ev.nodes})
            evidence.append(Evidence(
                pattern="hybrid_network",
                title=f"Hybrid laundering network ({len(families)} techniques)",
                description=(
                    "Multiple independent laundering techniques co-occur in this cluster — "
                    + ", ".join(sorted(families))
                    + ". Co-occurrence of this many distinct techniques is characteristic of "
                    "an organised, professionally operated laundering network."
                ),
                nodes=involved[:25],
                severity=min(0.98, 0.7 + 0.05 * len(families)),
                confidence=0.9,
                data={"techniques": sorted(families), "technique_count": len(families)},
            ))
        return evidence
