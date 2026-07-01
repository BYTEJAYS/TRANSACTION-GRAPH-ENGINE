from __future__ import annotations
"""
Realism Critic — two layers:
1. hard_validate(): rail physics + regulatory constraints → bool (drop if fails)
2. soft_score(): economic rationality → float 0-1 (ranks, never drops)

A genome that fails hard validation is physically impossible and will confuse
human investigators. It's worse than useless — it trains reviewers to distrust
the system. Never send impossible patterns to humans.
"""
import logging
from typing import TYPE_CHECKING

from red_team.core.rail_constraints import validate_genome

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome

logger = logging.getLogger(__name__)

# Cost estimate per mule account (recruiting, aging, maintaining cover)
MULE_COST_PER_ACCOUNT = 500  # ₹500 per mule (conservative)
MAX_ACCEPTABLE_COST_RATIO = 0.30  # Cost > 30% of gain = uneconomic


class RealismCritic:

    def hard_validate(self, genome: "FraudGenome") -> tuple[bool, list[str]]:
        """
        Returns (is_valid, violations).
        Uses rail_constraints.validate_genome — same rules as production.
        Failures are logged but the genome is silently dropped (not sent to human gate).
        """
        valid, violations = validate_genome(genome)
        if not valid:
            logger.debug(
                "Genome failed hard validation",
                genome_id=genome.genome_id[:8],
                violations=violations,
            )
        return valid, violations

    def soft_score(self, genome: "FraudGenome") -> float:
        """
        Economic rationality score in [0, 1].
        A rational criminal weighs cost vs benefit. Patterns with irrational
        cost-to-gain ratios are unlikely to occur in the real world — deprioritize them.
        """
        score = 1.0
        total_gain = genome.amounts.total
        mule_count = genome.topology.width + genome.topology.collector_count
        mule_cost = mule_count * MULE_COST_PER_ACCOUNT

        # Economically irrational: cost > 30% of gain
        if total_gain > 0 and mule_cost / total_gain > MAX_ACCEPTABLE_COST_RATIO:
            score *= 0.5
            genome.flags.append("possibly_uneconomic")
            logger.debug(
                "Soft score penalty: uneconomic",
                cost=mule_cost,
                gain=total_gain,
                ratio=round(mule_cost / total_gain, 3),
            )

        # Complex chain for trivially small gain
        if genome.topology.depth > 5 and total_gain < 100_000:
            score *= 0.6
            genome.flags.append("complex_chain_low_gain")

        # Festival timing is smart — real criminals use it
        if genome.timing.festival_timing:
            score = min(1.0, score * 1.2)

        # Recognized pattern mimicry is dangerous (could be real) but adds scrutiny
        if genome.topology.mimics_legitimate:
            score *= 0.8
            if "REQUIRES_SENIOR_REVIEW" not in genome.flags:
                genome.flags.append("REQUIRES_SENIOR_REVIEW")

        # Geographic spread across 4+ cities adds plausibility
        if len(genome.accounts.geographic_spread) >= 4:
            score = min(1.0, score * 1.1)

        return round(min(1.0, max(0.0, score)), 4)


# Module-level singleton
realism_critic = RealismCritic()
