from __future__ import annotations
"""
Failure Analysis — "What made me detectable?"

When Blue Team V2 catches a pattern, this turns the verdict into an actionable
diagnosis: which detectors fired, the likely structural/behavioural cause, and
the specific mutation operators most likely to evade each one on the next
generation. The evolution engine biases its operator sampling toward these.

This is the adversarial learning signal — it replaces blind random mutation with
*directed* mutation against the exact detector that fired. It does NOT change Blue
Team; it only changes how Red mutates.

Operator names below are the real registry from red_team.mutation.operators
(ALL_OPERATORS / DEFAULT_OPERATOR_WEIGHTS).
"""
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from red_team.evolution.blue_target import BlueVerdict

# Detector (V2 evidence pattern) → human cause + counter-mutation operators.
# Each operator is a valid key in DEFAULT_OPERATOR_WEIGHTS.
_DETECTOR_COUNTER = {
    "fan_in": {
        "cause": "Many sources converging on one collector (high in-degree).",
        "operators": ["create_bipartite_split", "layered_mixing", "mule_hub_creator",
                      "add_hop", "channel_hop"],
    },
    "fan_out": {
        "cause": "One source spraying to many destinations (high out-degree).",
        "operators": ["fan_out_collector", "add_hop", "layered_mixing", "time_dilation"],
    },
    "smurfing": {
        "cause": "Amounts clustered just under reporting thresholds / uniform splits.",
        "operators": ["amount_noise", "pyramid_amounts", "threshold_fragmenter",
                      "just_under_threshold"],
    },
    "mule_accounts": {
        "cause": "Pass-through accounts: rapid receive-then-forward, low retention.",
        "operators": ["insert_abandoned_node", "time_dilation", "add_dormancy_period",
                      "age_the_accounts", "reduce_velocity"],
    },
    "bridge_accounts": {
        "cause": "Single cut-point relaying between clusters (high betweenness).",
        "operators": ["ghost_node_injector", "add_hop", "layered_mixing",
                      "fan_out_collector"],
    },
    "dormant_accounts": {
        "cause": "Old/inactive accounts suddenly reactivated and forwarding.",
        "operators": ["dormant_activator", "age_the_accounts", "reduce_velocity",
                      "recognized_pattern_verification"],
    },
    "circular_flow": {
        "cause": "Funds return to origin (graph cycle).",
        "operators": ["cycle_extender", "add_hop", "layered_mixing"],
    },
    "layering": {
        "cause": "Deep multi-hop chains with conserved value (classic layering).",
        "operators": ["channel_hop", "amount_noise", "recognized_pattern_verification",
                      "insert_merchant_node"],
    },
    "cashout": {
        "cause": "Fast consolidation then exit (cash/crypto/ATM).",
        "operators": ["cash_out_disguise", "time_dilation", "channel_hop",
                      "add_dormancy_period"],
    },
    "velocity": {
        "cause": "Too many transactions in too short a window.",
        "operators": ["reduce_velocity", "time_dilation", "jitter_timing",
                      "add_dormancy_period"],
    },
    "synthetic_networks": {
        "cause": "Accounts look freshly minted / coordinated (synthetic identity ring).",
        "operators": ["age_the_accounts", "geographic_spread", "upi_app_diversity",
                      "recognized_pattern_verification", "insert_merchant_node"],
    },
    "hybrid_network": {
        "cause": "Multiple fraud structures co-occur — the combination itself is the tell.",
        "operators": ["recognized_pattern_verification", "insert_merchant_node",
                      "layered_mixing", "geographic_spread", "age_the_accounts"],
    },
}

# Fallback when a fired pattern isn't in the map.
_GENERIC_OPERATORS = ["layered_mixing", "amount_noise", "time_dilation",
                      "recognized_pattern_verification", "channel_hop"]


@dataclass
class FailureReport:
    detected: bool
    verdict: str
    risk: float
    confidence: float
    triggered_detectors: list[str]
    causes: list[str] = field(default_factory=list)
    recommended_operators: list[str] = field(default_factory=list)
    operator_weights: dict[str, float] = field(default_factory=dict)
    flagged_node_count: int = 0

    def to_dict(self) -> dict:
        return {
            "detected": self.detected,
            "verdict": self.verdict,
            "risk": round(self.risk, 4),
            "confidence": round(self.confidence, 4),
            "triggered_detectors": self.triggered_detectors,
            "causes": self.causes,
            "recommended_operators": self.recommended_operators,
            "flagged_node_count": self.flagged_node_count,
        }


def analyze(verdict: "BlueVerdict") -> FailureReport:
    """Diagnose a Blue verdict and recommend the next generation's mutations.

    Recommended operators are ordered and weighted by how many fired detectors
    they counter, so the engine can sample the highest-leverage mutation first.
    """
    detectors = list(verdict.evidence_patterns)
    causes: list[str] = []
    weights: dict[str, float] = {}

    for det in detectors:
        entry = _DETECTOR_COUNTER.get(det)
        if entry is None:
            continue
        causes.append(f"{det}: {entry['cause']}")
        for op in entry["operators"]:
            weights[op] = weights.get(op, 0.0) + 1.0

    if not weights:
        # Detected but no recognised pattern (or risk-only) → generic evasions.
        for op in _GENERIC_OPERATORS:
            weights[op] = weights.get(op, 0.0) + 1.0
        if not causes and verdict.detected:
            causes.append("High aggregate risk with no single dominant pattern.")

    ordered = sorted(weights, key=lambda o: weights[o], reverse=True)
    return FailureReport(
        detected=verdict.detected,
        verdict=verdict.verdict,
        risk=verdict.risk,
        confidence=verdict.confidence,
        triggered_detectors=detectors,
        causes=causes,
        recommended_operators=ordered,
        operator_weights=weights,
        flagged_node_count=len(verdict.flagged_nodes),
    )
