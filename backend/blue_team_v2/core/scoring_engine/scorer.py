"""
Scoring Engine — converts the 18 measured factors into a single independent
risk score per node, together with a normalized contribution breakdown that
the AI explanation engine renders as "why".

Design goals:
  * Every node scores independently — no cluster-wide blanket value.
  * The dominant cluster role sets a structural *base*; factors push up/down
    from there, so an origin and a peripheral node start far apart.
  * Contributions always sum to ~1.0 of the *earned* risk so explanations are
    faithful (a contributor's % is its real share of the score).
"""
from __future__ import annotations

import math

from ...types import NodeMetrics
from ..cluster_engine.roles import ROLE_BASE_RISK


def _sat(value: float, scale: float) -> float:
    if value <= 0:
        return 0.0
    return 1.0 - math.exp(-value / scale)


# Each entry: factor key → (weight, human label, value extractor → 0..1 signal)
def _factor_signals(m: NodeMetrics) -> dict[str, tuple[float, str, float]]:
    fan_out_sig = _sat(max(0, m.fan_out_count - 1), 4.0)
    fan_in_sig = _sat(max(0, m.fan_in_count - 1), 4.0)
    velocity_sig = m.transaction_velocity
    freq_sig = _sat(m.transaction_frequency, 12.0)
    volume_sig = _sat(m.incoming_volume + m.outgoing_volume, 1_000_000.0)
    betweenness_sig = min(1.0, m.betweenness_centrality * 2.0)
    bridge_sig = min(1.0, m.bridge_importance * 2.0)
    # closer to a fraud origin → higher (0 hops = 1.0, decays)
    if m.fraud_distance >= 999:
        proximity_sig = 0.0
    else:
        proximity_sig = math.exp(-m.fraud_distance / 2.0)
    layer_sig = _sat(m.layer_distance, 3.0)
    circular_sig = 1.0 if m.circular_participation else 0.0
    burst_sig = m.burst_activity
    history_sig = m.historical_behavior
    inherit_sig = m.risk_inheritance
    pattern_sig = _sat(m.pattern_participation, 2.0)
    passthrough_sig = m.pass_through_ratio if (m.fan_in_count and m.fan_out_count) else 0.0
    dormancy_sig = m.dormancy_reactivation

    # Evidence-driven weighting. Amount-gated detector participation, fraud
    # proximity, and temporal anomalies are the PRIMARY drivers. Raw topology
    # (centrality, bare fan degree, the circular flag) saturates on small benign
    # clusters, so it is demoted to a minor tie-breaker — this is what keeps
    # legitimate clusters clean while still differentiating nodes within a ring.
    return {
        # key: (weight, label, signal)
        "pattern_participation":  (0.22, "Pattern Participation", pattern_sig),
        "fraud_proximity":        (0.15, "Fraud Proximity", proximity_sig),
        "velocity_anomaly":       (0.12, "Velocity Anomaly", velocity_sig),
        "risk_inheritance":       (0.08, "Inherited Risk", inherit_sig),
        "burst_activity":         (0.07, "Burst Activity", burst_sig),
        "volume":                 (0.06, "Transaction Volume", volume_sig),
        "pass_through":           (0.05, "Pass-Through Relay", passthrough_sig),
        "dormancy_reactivation":  (0.05, "Dormant Reactivation", dormancy_sig),
        "layering":               (0.04, "Layering Depth", layer_sig),
        "historical_behavior":    (0.04, "Historical Behaviour", history_sig),
        "bridge_activity":        (0.03, "Bridge Activity", bridge_sig),
        "circular_flow":          (0.03, "Circular Flow", circular_sig),
        "fan_out":                (0.025, "Fan-Out Distribution", fan_out_sig),
        "fan_in":                 (0.025, "Fan-In Collection", fan_in_sig),
        "betweenness":            (0.02, "Path Centrality", betweenness_sig),
        "frequency":              (0.02, "Transaction Frequency", freq_sig),
    }


class ScoringEngine:
    def score_node(self, m: NodeMetrics) -> NodeMetrics:
        signals = _factor_signals(m)
        base = ROLE_BASE_RISK.get(m.cluster_role, 0.05)

        # weighted earned risk from factors
        earned = 0.0
        raw_contrib: dict[str, float] = {}
        for key, (w, label, sig) in signals.items():
            c = w * sig
            earned += c
            if c > 0:
                raw_contrib[label] = c

        # Combine structural base with earned factor risk.  Base provides the
        # floor (role), factors lift it toward 1.0 without exceeding it.
        score = base + (1.0 - base) * min(1.0, earned * 1.6)
        score = max(0.0, min(0.999, score))

        # confidence: more corroborating signals + clearer separation → higher
        active = [c for c in raw_contrib.values() if c > 0.005]
        evidence_breadth = min(1.0, len(active) / 6.0)
        signal_strength = min(1.0, earned * 2.0)
        confidence = 0.35 + 0.4 * evidence_breadth + 0.25 * signal_strength
        confidence = max(0.0, min(0.99, confidence))

        # normalize contributions to shares of the score (faithful "why")
        total = sum(raw_contrib.values())
        contributions: dict[str, float] = {}
        if total > 0:
            for label, c in sorted(raw_contrib.items(), key=lambda x: x[1], reverse=True):
                share = c / total
                if share >= 0.02:
                    contributions[label] = round(share, 4)

        m.risk_score = round(score, 4)
        m.confidence = round(confidence, 4)
        m.contributions = contributions
        return m

    def score_all(self, metrics: dict[str, NodeMetrics]) -> None:
        for m in metrics.values():
            self.score_node(m)
