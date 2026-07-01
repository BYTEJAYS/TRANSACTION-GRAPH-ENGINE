"""
Evolution engine.

A small genetic-algorithm loop that improves synthetic scenarios *for realism
and diversity* over successive generations:

    seed population -> evaluate -> select -> crossover -> mutate -> repeat

ISOLATION: the fitness function is computed entirely from the synthetic dataset
itself (the same descriptive realism/diversity heuristics the research engine
uses). It never consults, queries, or adapts against the Blue Team detector.
The goal is a richer, more varied scenario library — not detector evasion.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from red_team.adversarial_research.strategy_explorer import StrategyExplorer, _SEARCH_SPACE
from red_team.core.config import RedTeamConfig, config as default_config
from red_team.core.models import ComplexityLevel, ScenarioSpec
from red_team.simulators.fraud_simulator import FraudSimulator


@dataclass
class ScenarioGenome:
    """A heritable parameter vector for a scenario."""

    parameters: Dict[str, int]
    fitness: float = 0.0
    generation: int = 0

    def clone(self) -> "ScenarioGenome":
        return ScenarioGenome(parameters=dict(self.parameters), generation=self.generation)


@dataclass
class EvolutionReport:
    base_scenario_id: str
    generations: int
    best_genome: Optional[ScenarioGenome] = None
    fitness_history: List[float] = field(default_factory=list)  # best fitness per generation

    def as_dict(self) -> Dict:
        return {
            "base_scenario_id": self.base_scenario_id,
            "generations": self.generations,
            "best_fitness": round(self.best_genome.fitness, 4) if self.best_genome else None,
            "best_parameters": self.best_genome.parameters if self.best_genome else None,
            "fitness_history": [round(f, 4) for f in self.fitness_history],
        }


class EvolutionEngine:
    """Evolves scenario parameter vectors toward higher realism + diversity."""

    def __init__(
        self,
        cfg: Optional[RedTeamConfig] = None,
        population_size: int = 12,
        elite: int = 3,
        mutation_rate: float = 0.3,
        seed: Optional[int] = None,
    ):
        self.cfg = cfg or default_config
        self.population_size = population_size
        self.elite = elite
        self.mutation_rate = mutation_rate
        self.seed = seed if seed is not None else self.cfg.seed
        self._rng = random.Random(self.seed)
        self._sim = FraudSimulator(cfg=self.cfg)
        self._explorer = StrategyExplorer(cfg=self.cfg, seed=self.seed)

    # ── GA operators ──────────────────────────────────────────────────────────

    def _seed_genome(self, base: Dict) -> ScenarioGenome:
        params = dict(base)
        for key in base:
            if key in _SEARCH_SPACE:
                lo, hi = _SEARCH_SPACE[key]
                params[key] = self._rng.randint(int(lo), int(hi))
        return ScenarioGenome(parameters=params)

    def _mutate(self, genome: ScenarioGenome) -> ScenarioGenome:
        child = genome.clone()
        for key in list(child.parameters):
            if key in _SEARCH_SPACE and self._rng.random() < self.mutation_rate:
                lo, hi = _SEARCH_SPACE[key]
                child.parameters[key] = self._rng.randint(int(lo), int(hi))
        return child

    def _crossover(self, a: ScenarioGenome, b: ScenarioGenome) -> ScenarioGenome:
        params = {}
        for key in a.parameters:
            source = a if self._rng.random() < 0.5 else b
            params[key] = source.parameters.get(key, a.parameters[key])
        return ScenarioGenome(parameters=params)

    def _fitness(self, spec: ScenarioSpec, genome: ScenarioGenome, gen: int) -> float:
        variant = spec.model_copy(update={"parameters": genome.parameters})
        scenario = self._sim.run(variant, seed=self.seed + gen)
        realism = self._explorer._realism(scenario)
        diversity = self._explorer._diversity(scenario)
        return round(0.6 * realism + 0.4 * diversity, 4)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def evolve(self, spec: ScenarioSpec, generations: int = 8) -> EvolutionReport:
        population = [self._seed_genome(spec.parameters) for _ in range(self.population_size)]
        report = EvolutionReport(base_scenario_id=spec.scenario_id, generations=generations)

        for gen in range(generations):
            for g in population:
                g.fitness = self._fitness(spec, g, gen)
                g.generation = gen
            population.sort(key=lambda g: g.fitness, reverse=True)
            report.fitness_history.append(population[0].fitness)

            survivors = population[: self.elite]
            children: List[ScenarioGenome] = list(survivors)
            while len(children) < self.population_size:
                parent_a = self._rng.choice(survivors)
                parent_b = self._rng.choice(population[: max(self.elite * 2, 4)])
                child = self._mutate(self._crossover(parent_a, parent_b))
                children.append(child)
            population = children

        for g in population:
            g.fitness = self._fitness(spec, g, generations)
        population.sort(key=lambda g: g.fitness, reverse=True)
        report.best_genome = population[0]
        return report

    def evolved_spec(self, spec: ScenarioSpec, report: EvolutionReport) -> ScenarioSpec:
        """Produce a new ScenarioSpec from the best evolved genome."""
        if report.best_genome is None:
            return spec
        new_id = f"{spec.scenario_id}-evo"
        return spec.model_copy(
            update={
                "scenario_id": new_id,
                "title": f"{spec.title} (evolved)",
                "complexity": ComplexityLevel.ADVANCED,
                "parameters": report.best_genome.parameters,
            }
        )
