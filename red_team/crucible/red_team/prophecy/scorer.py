from __future__ import annotations
"""
LineageScorer — maps prophecy hit rates to PBT selection weights.

Hit rate tiers (empirically tuned for fraud Red Teaming):
  > 20%  → weight 2.0  (hot lineage: evolve more of this)
  10-20% → weight 1.5
   5-10% → weight 1.0  (baseline)
   1-5%  → weight 0.3  (cold)
   0-1%  → weight 0.1  (dead end — very rare hits could be noise)

Operators in hot lineages are promoted in DEFAULT_OPERATOR_WEIGHTS so the
next generation starts from a better distribution.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Tier boundaries and weights
_TIERS: list[tuple[float, float]] = [
    (0.20, 2.0),
    (0.10, 1.5),
    (0.05, 1.0),
    (0.01, 0.3),
    (0.00, 0.1),
]


def hit_rate_to_weight(hit_rate: float) -> float:
    """Convert a lineage's prophecy hit rate to a PBT selection weight multiplier."""
    for threshold, weight in _TIERS:
        if hit_rate >= threshold:
            return weight
    return 0.1


def compute_lineage_fitness_weights(
    lineage_stats: dict[str, dict[str, Any]],
) -> dict[str, float]:
    """
    Input: {lineage_id: {"predictions": int, "hits": int, "operators": list[str]}}
    Output: {lineage_id: weight}

    lineage_id convention: "{parent_genome_id[:8]}_{operator_name}"
    """
    weights: dict[str, float] = {}

    for lineage_id, stats in lineage_stats.items():
        predictions = stats.get("predictions", 0)
        hits = stats.get("hits", 0)

        if predictions == 0:
            # No history yet — start at baseline
            weights[lineage_id] = 1.0
            continue

        hit_rate = hits / predictions
        weight = hit_rate_to_weight(hit_rate)
        weights[lineage_id] = weight

        logger.debug(
            "Lineage weight computed",
            lineage=lineage_id,
            predictions=predictions,
            hits=hits,
            hit_rate=round(hit_rate, 4),
            weight=weight,
        )

    return weights


def compute_operator_boosts(
    lineage_stats: dict[str, dict[str, Any]],
) -> dict[str, float]:
    """
    Aggregate hit rates by operator name across all lineages.
    Returns {operator_name: weight_multiplier} for hot operators.
    Used to update mutation/operators/__init__.py DEFAULT_OPERATOR_WEIGHTS at runtime.
    """
    operator_hits: dict[str, int] = {}
    operator_predictions: dict[str, int] = {}

    for stats in lineage_stats.values():
        predictions = stats.get("predictions", 0)
        hits = stats.get("hits", 0)
        for op in stats.get("operators", []):
            operator_predictions[op] = operator_predictions.get(op, 0) + predictions
            operator_hits[op] = operator_hits.get(op, 0) + hits

    boosts: dict[str, float] = {}
    for op, preds in operator_predictions.items():
        if preds == 0:
            continue
        rate = operator_hits.get(op, 0) / preds
        boosts[op] = hit_rate_to_weight(rate)

    return boosts
