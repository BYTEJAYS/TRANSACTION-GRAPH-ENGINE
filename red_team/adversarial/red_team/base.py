"""
Attack genome representation and application.

A *genome* is an ordered list of Moves; each Move applies one agent at a chosen
intensity. The base fraud graph is transformed by replaying the genome, then the
result is re-split into real connected components so any severed connectivity
(from cross_component_split / relay_insertion) is physically realised.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from ..common.attack_graph import AttackGraph
from . import agents as _agents

AGENTS: dict[str, callable] = _agents.registry()
AGENT_NAMES: list[str] = sorted(AGENTS.keys())


@dataclass
class Move:
    agent: str
    intensity: float  # [0,1]

    def __repr__(self) -> str:
        return f"{self.agent}@{self.intensity:.2f}"


Genome = list[Move]


def random_move(rng: random.Random) -> Move:
    return Move(agent=rng.choice(AGENT_NAMES), intensity=round(rng.random(), 3))


def random_genome(rng: random.Random, min_len: int = 1, max_len: int = 8) -> Genome:
    n = rng.randint(min_len, max_len)
    return [random_move(rng) for _ in range(n)]


def genome_repr(genome: Genome) -> str:
    return " → ".join(repr(m) for m in genome) if genome else "(identity)"


def apply_genome(base: AttackGraph, genome: Genome, rng: random.Random) -> AttackGraph:
    """Clone the base fraud graph, replay the genome, realise components."""
    from .graph_generator import resplit_components

    ag = base.clone()
    for mv in genome:
        fn = AGENTS.get(mv.agent)
        if fn is None:
            continue
        try:
            fn(ag, rng, max(0.0, min(1.0, mv.intensity)))
        except Exception:
            # an agent must never crash the search; skip a bad move
            continue
    ag = resplit_components(ag)
    ag.genome_repr = genome_repr(genome)
    return ag
