from __future__ import annotations
"""
Adaptive Difficulty — Easy … Impossible.

A difficulty level tunes how hard the generated scenarios are: graph size, the
fraction of legitimate-cover traffic, how aggressively timing is spread across
days, how often families are hybridised (crossover), behavioural realism, and how
many evolution generations the engine is allowed before giving up on a lineage.

`apply()` shapes a freshly-built family genome to the level WITHOUT changing the
locked transaction format (integer amounts, valid rails). Higher levels look more
human and bury fraud in more legitimate noise.
"""
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome

LEVELS = ["easy", "medium", "hard", "expert", "nation_state", "impossible"]


@dataclass(frozen=True)
class DifficultyProfile:
    level: str
    size_scale: float          # multiplier on width/depth
    legit_noise_ratio: float   # fraction of surrounding traffic that is legitimate
    multi_day_factor: float    # multiplier on inter-txn spacing (spread over time)
    hybridization_prob: float  # chance a new attack is a crossover of two families
    behavior_realism: float    # 0..1 — human-like timing/age/geo jitter
    max_generations: int       # evolution budget per lineage
    blend_legit_into_graph: bool  # inject legit edges into the graph V2 scores


PROFILES: dict[str, DifficultyProfile] = {
    "easy":         DifficultyProfile("easy", 0.8, 0.50, 1.0, 0.0, 0.1, 4, False),
    "medium":       DifficultyProfile("medium", 1.0, 0.80, 1.5, 0.2, 0.3, 6, False),
    "hard":         DifficultyProfile("hard", 1.3, 0.90, 3.0, 0.4, 0.6, 8, True),
    "expert":       DifficultyProfile("expert", 1.6, 0.95, 6.0, 0.6, 0.8, 12, True),
    "nation_state": DifficultyProfile("nation_state", 2.0, 0.97, 14.0, 0.8, 0.95, 16, True),
    "impossible":   DifficultyProfile("impossible", 2.5, 0.99, 30.0, 0.95, 1.0, 24, True),
}


def get_profile(level: str) -> DifficultyProfile:
    key = (level or "medium").strip().lower()
    if key not in PROFILES:
        raise KeyError(f"Unknown difficulty {level!r}. Valid: {LEVELS}")
    return PROFILES[key]


def apply(genome: "FraudGenome", profile: DifficultyProfile,
          rng: random.Random) -> "FraudGenome":
    """Shape a base genome to the difficulty level (in place, returns it)."""
    t = genome.topology
    t.width = max(1, int(round(t.width * profile.size_scale)))
    t.depth = max(1, int(round(t.depth * profile.size_scale)))

    # Spread transactions over more time at higher difficulty (multi-day attacks).
    genome.timing.spacing_days = [
        round(s * profile.multi_day_factor, 3) for s in genome.timing.spacing_days
    ]
    if profile.multi_day_factor >= 6.0:
        genome.timing.low_slow = True

    # Behavioural realism: jitter timing + age accounts + spread geography.
    if profile.behavior_realism > 0:
        b = profile.behavior_realism
        genome.timing.jitter = round(genome.timing.jitter + b * rng.uniform(0.1, 0.4), 3)
        genome.accounts.source_ages_days = [
            int(age + b * rng.uniform(50, 300)) for age in genome.accounts.source_ages_days
        ] or [int(200 + b * 200)]
        # Slow down velocity to look human.
        genome.accounts.velocity_ratio = round(
            max(0.02, genome.accounts.velocity_ratio * (1.0 - 0.5 * b)), 3
        )
        if b >= 0.6 and not genome.accounts.geographic_spread:
            genome.accounts.cross_city = True
            genome.accounts.geographic_spread = rng.sample(
                ["MH", "DL", "KA", "TN", "GJ", "WB"], k=min(3, max(2, int(b * 4)))
            )
    return genome
