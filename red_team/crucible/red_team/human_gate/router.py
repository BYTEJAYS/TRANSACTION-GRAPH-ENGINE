from __future__ import annotations
"""
Counterfactual Repair Router — given an approved genome, decides whether
Blue Team should respond with a new hard gate or bounded model retraining.

Decision logic:
  new_gate   → topology has a clear structural invariant (cycles, bipartite density)
               that can be expressed as a deterministic rule
  bounded_retrain → pattern is statistical (amount distribution, timing spread)
                    → XGBoost challenger needs new training examples
  human_decision  → ambiguous; route to senior investigator

The router does NOT implement the gates — it generates a recommendation
with evidence that goes back to Blue Team via the review API.
"""
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome

logger = logging.getLogger(__name__)

# Structural features that suggest a deterministic gate is feasible
_GATE_INDICATORS = {
    "cycle": "confirmed_cycle_gate",
    "bipartite": "bipartite_core_gate",
    "layered": None,  # no single gate — retrain
}

_TIMING_EVASION_OPS = {"time_dilation", "add_dormancy_period", "jitter_timing"}
_AMOUNT_EVASION_OPS = {"just_under_threshold", "amount_noise", "pyramid_amounts"}
_STRUCTURAL_EVASION_OPS = {"layered_mixing", "cash_out_disguise", "recognized_pattern_verification"}


def counterfactual_repair_test(
    genome: "FraudGenome",
    fitness: float,
) -> dict[str, Any]:
    """
    Returns a recommendation dict:
    {
        "recommendation": "new_gate" | "bounded_retrain" | "human_decision",
        "gate_name": str | None,     # if new_gate
        "feature_set": list[str],    # features to add to retrain if bounded_retrain
        "evidence": dict,
        "confidence": float,
    }
    """
    lineage_ops = set(genome.mutation_history)
    topo_type = genome.topology.type

    evidence = {
        "topology_type": topo_type,
        "depth": genome.topology.depth,
        "width": genome.topology.width,
        "lineage_operators": genome.mutation_history,
        "fitness": round(fitness, 4),
        "flags": genome.flags,
    }

    # Case 1: topology-driven evasion → new gate
    if topo_type in _GATE_INDICATORS and _GATE_INDICATORS[topo_type]:
        return {
            "recommendation": "new_gate",
            "gate_name": _GATE_INDICATORS[topo_type],
            "feature_set": [],
            "evidence": evidence,
            "confidence": 0.85,
        }

    # Case 2: timing or amount evasion only → bounded retraining (statistical pattern)
    timing_used = lineage_ops & _TIMING_EVASION_OPS
    amount_used = lineage_ops & _AMOUNT_EVASION_OPS
    structural_used = lineage_ops & _STRUCTURAL_EVASION_OPS

    if (timing_used or amount_used) and not structural_used:
        features = list(timing_used | amount_used)
        return {
            "recommendation": "bounded_retrain",
            "gate_name": None,
            "feature_set": features,
            "evidence": evidence,
            "confidence": 0.75,
        }

    # Case 3: structural evasion (layered mixing, cash-out disguise) → usually retrain
    if structural_used and not timing_used:
        return {
            "recommendation": "bounded_retrain",
            "gate_name": None,
            "feature_set": list(structural_used),
            "evidence": evidence,
            "confidence": 0.65,
        }

    # Case 4: multi-operator evasion or ambiguous → human
    return {
        "recommendation": "human_decision",
        "gate_name": None,
        "feature_set": [],
        "evidence": evidence,
        "confidence": 0.40,
    }
