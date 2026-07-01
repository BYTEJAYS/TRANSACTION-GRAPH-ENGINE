"""
Curriculum ladder (L1–L10).

Each level widens the Red Team's allowed action space and search budget, so the
Blue Team is exposed to progressively harder attacks. The agent allow-lists map
directly onto the white-box vulnerability classes: features → edges →
communities/degree → temporal → multi-stage → search-driven (evolution/RL) →
meta (the full arsenal). Self-play promotes the Red Team up the ladder only once
the Blue Team has been hardened against the current level.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CurriculumLevel:
    level: int
    name: str
    description: str
    agents: tuple[str, ...]              # agents unlocked at/below this level
    search: str                         # "random" | "evolutionary" | "rl" | "meta"
    population: int = 30
    generations: int = 15


# Cumulative agent unlocks up the ladder.
_FEATURE = ("feature_mimicry", "amount_dither")
_EDGE = _FEATURE + ("decoy_edges",)
_COMMUNITY = _EDGE + ("relay_insertion",)
_TEMPORAL = _COMMUNITY + ("temporal_spread",)
_MULTISTAGE = _TEMPORAL + ("sink_funnel", "cross_component_split",
                           "volume_dilution", "profile_mimicry",
                           "account_takeover", "conduit_split")

LADDER: tuple[CurriculumLevel, ...] = (
    CurriculumLevel(1, "random_anomalies",
                    "Random perturbations; baseline noise floor.",
                    _FEATURE, "random", 20, 8),
    CurriculumLevel(2, "feature_attacks",
                    "Node-feature mimicry + amount masking (B8, smurfing).",
                    _FEATURE, "evolutionary", 24, 12),
    CurriculumLevel(3, "edge_attacks",
                    "Decoy edges to dilute density / break uniformity.",
                    _EDGE, "evolutionary", 28, 14),
    CurriculumLevel(4, "community_attacks",
                    "Degree-throttling relay trees vs fan/role gates.",
                    _COMMUNITY, "evolutionary", 32, 16),
    CurriculumLevel(5, "temporal_attacks",
                    "Time spreading vs velocity/burst/dormancy gates.",
                    _TEMPORAL, "evolutionary", 36, 18),
    CurriculumLevel(6, "multistage_attacks",
                    "Sink funnels + cross-component partition (B1) combined.",
                    _MULTISTAGE, "evolutionary", 48, 24),
    CurriculumLevel(7, "adaptive_attacks",
                    "Full arsenal, larger evolutionary budget, warm-started.",
                    _MULTISTAGE, "evolutionary", 60, 30),
    CurriculumLevel(8, "evolutionary_attacks",
                    "Long-horizon evolution with attack-memory recombination.",
                    _MULTISTAGE, "evolutionary", 80, 50),
    CurriculumLevel(9, "rl_attacks",
                    "PPO policy over the same action space (sequential credit).",
                    _MULTISTAGE, "rl", 0, 0),
    CurriculumLevel(10, "meta_attacks",
                    "Population of RL+evolution attackers; GraphGAN equilibrium.",
                    _MULTISTAGE, "meta", 0, 0),
)


def level(n: int) -> CurriculumLevel:
    return LADDER[max(1, min(10, n)) - 1]


def allowed_agents(n: int) -> tuple[str, ...]:
    return level(n).agents
