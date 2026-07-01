from __future__ import annotations
"""
Fitness function: Ensemble Disagreement × Realism × Novelty.

Using a single model to measure evasion produces adversarial examples — patterns
that fool THIS model but no real criminal would use. Ensemble disagreement finds
genuine soft spots where Blue Team collectively doesn't know what to do.
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome
    from red_team.sandbox.blue_clone import MockBlueTeam

logger = logging.getLogger(__name__)


def evaluate_fitness(
    genome: "FraudGenome",
    blue_team: "MockBlueTeam",
    realism_score: float,
    novelty_score: float,
) -> float:
    """
    Returns fitness in [0.0, 1.0].
    Zero if Blue Team catches it on average (mean score > 0.5).
    Zero if realism < 0.5 (physically impossible — not useful to humans).
    """
    scores = blue_team.score(genome)
    if not scores:
        return 0.0

    mean_score = sum(scores) / len(scores)

    # Must actually evade — if Blue Team catches it on average, no value
    if mean_score > 0.5:
        return 0.0

    # Ensemble disagreement: how much do the models disagree?
    # High disagreement = soft underbelly of the detection ensemble
    variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
    disagreement = min(variance * 4.0, 1.0)  # scale so range is 0-1

    # Realism filter
    if realism_score < 0.5:
        return 0.0

    # Novelty filter
    if novelty_score < 0.1:
        return 0.0

    fitness = disagreement * realism_score * novelty_score

    logger.debug(
        "Fitness evaluated",
        genome_id=genome.genome_id[:8],
        mean_score=round(mean_score, 3),
        disagreement=round(disagreement, 3),
        realism=round(realism_score, 3),
        novelty=round(novelty_score, 3),
        fitness=round(fitness, 4),
    )
    return round(fitness, 6)


def evasion_score(genome: "FraudGenome", blue_team: "MockBlueTeam") -> float:
    """
    Simple evasion score: 1.0 - champion_score.
    High = evading well. Used for filtering before full fitness eval.
    """
    scores = blue_team.score(genome)
    if not scores:
        return 0.0
    return round(1.0 - scores[0], 4)
