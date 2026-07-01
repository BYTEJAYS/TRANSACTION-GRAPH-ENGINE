from __future__ import annotations
"""
PBT Mutation Engine — Population-Based Training for fraud genome evolution.

Algorithm per generation:
1. Evaluate fitness for all genomes (ensemble disagreement × realism × novelty)
2. Exploit top 20%: copy their operators to bottom 20%
3. Explore remaining 80%: sample operator from weighted distribution, mutate
4. Apply hard_validate() — drop invalid genomes, reseed from survivors
5. Update operator weights from prophecy boosts (lineage hit rates)
6. Enforce population diversity — drop near-duplicates (novelty < 0.1)
7. Store new top genomes in novelty index and prophecy ledger

Runs 10,000 generations per nightly Celery job.
Population size: 500 genomes.
"""
import logging
import random
import time
import uuid
from copy import deepcopy
from typing import TYPE_CHECKING, Callable

from red_team.core.fingerprint import compute_embedding
from red_team.critics.novelty import NoveltyCritic
from red_team.critics.realism import RealismCritic
from red_team.mutation.fitness import evaluate_fitness
from red_team.mutation.operators import ALL_OPERATORS, DEFAULT_OPERATOR_WEIGHTS
from red_team.prophecy.ledger import ProphecyLedger

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome
    from red_team.sandbox.blue_clone import MockBlueTeam

logger = logging.getLogger(__name__)

POPULATION_SIZE = 500
TOP_PERCENT = 0.20  # exploit top 20%
BOTTOM_PERCENT = 0.20  # replace bottom 20%
MAX_RESEEDS = 3  # max reseed attempts when population shrinks below MIN_POPULATION
MIN_POPULATION = 50
GENERATIONS_PER_NIGHT = 10_000
DIVERSITY_NOVELTY_FLOOR = 0.10  # drop genomes below this novelty vs population
FITNESS_FLOOR = 0.0001  # genomes below this are culled


class MutationEngine:

    def __init__(
        self,
        blue_team: "MockBlueTeam",
        seed_genomes: list["FraudGenome"],
        ledger: ProphecyLedger | None = None,
        generations: int = GENERATIONS_PER_NIGHT,
    ) -> None:
        self.blue_team = blue_team
        self.generations = generations
        self.ledger = ledger or ProphecyLedger()
        self.realism = RealismCritic()
        self.novelty = NoveltyCritic()
        self._operator_weights = dict(DEFAULT_OPERATOR_WEIGHTS)
        self._population: list["FraudGenome"] = []
        self._fitness_cache: dict[str, float] = {}

        # Seed the population
        self._population = list(seed_genomes[:POPULATION_SIZE])
        # Register seeds in novelty index
        for g in self._population:
            self.novelty.add(g)
        logger.info("Engine initialized", population=len(self._population))

    # ── Operator selection ──────────────────────────────────────────────────

    def _sample_operator(self) -> Callable:
        ops = list(self._operator_weights.keys())
        weights = [self._operator_weights.get(op.__name__, 1.0) for op in ALL_OPERATORS if op.__name__ in self._operator_weights]
        # Rebuild from ALL_OPERATORS to keep alignment
        valid_ops = [op for op in ALL_OPERATORS if op.__name__ in self._operator_weights]
        valid_weights = [self._operator_weights[op.__name__] for op in valid_ops]
        if not valid_ops:
            return random.choice(ALL_OPERATORS)
        return random.choices(valid_ops, weights=valid_weights, k=1)[0]

    def _apply_operator(self, genome: "FraudGenome") -> tuple["FraudGenome", str]:
        """Returns (mutated_genome, operator_name). Falls back to original on exception."""
        op = self._sample_operator()
        try:
            mutated = op(deepcopy(genome))
            mutated.genome_id = str(uuid.uuid4())
            mutated.generation += 1
            mutated.parent_genome_id = genome.genome_id
            if op.__name__ not in mutated.mutation_history:
                mutated.mutation_history.append(op.__name__)
            return mutated, op.__name__
        except Exception as exc:
            logger.debug("Operator failed", op=op.__name__, error=str(exc))
            return deepcopy(genome), op.__name__

    # ── Fitness evaluation ──────────────────────────────────────────────────

    def _evaluate(self, genome: "FraudGenome") -> float:
        gid = genome.genome_id
        if gid in self._fitness_cache:
            return self._fitness_cache[gid]

        valid, _ = self.realism.hard_validate(genome)
        if not valid:
            self._fitness_cache[gid] = 0.0
            return 0.0

        realism_score = self.realism.soft_score(genome)
        novelty_score = self.novelty.score(genome)
        fitness = evaluate_fitness(genome, self.blue_team, realism_score, novelty_score)
        self._fitness_cache[gid] = fitness
        return fitness

    # ── PBT step ────────────────────────────────────────────────────────────

    def _pbt_step(self) -> None:
        pop = self._population
        n = len(pop)
        if n < 2:
            return

        # Evaluate all
        scored = [(g, self._evaluate(g)) for g in pop]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Exploit: copy top 20% operators/lineage onto bottom 20%
        top_n = max(1, int(n * TOP_PERCENT))
        bottom_n = max(1, int(n * BOTTOM_PERCENT))
        top_genomes = [g for g, _ in scored[:top_n]]
        bottom_indices = list(range(n - bottom_n, n))

        for idx in bottom_indices:
            donor = random.choice(top_genomes)
            child = deepcopy(donor)
            child.genome_id = str(uuid.uuid4())
            child.generation = scored[idx][0].generation + 1
            child.parent_genome_id = donor.genome_id
            child.flags = []
            scored[idx] = (child, self._evaluate(child))

        # Explore: mutate middle 60%
        explore_range = list(range(top_n, n - bottom_n))
        for idx in explore_range:
            genome, _ = scored[idx]
            mutated, op_name = self._apply_operator(genome)
            new_fitness = self._evaluate(mutated)
            if new_fitness > 0.0:
                scored[idx] = (mutated, new_fitness)

        # Cull below fitness floor
        scored = [(g, f) for g, f in scored if f > FITNESS_FLOOR]

        # Diversity enforcement
        survivors = []
        for genome, fitness in scored:
            ns = self.novelty.score(genome)
            if ns >= DIVERSITY_NOVELTY_FLOOR:
                survivors.append((genome, fitness))
            else:
                logger.debug("Diversity cull", genome_id=genome.genome_id[:8])

        if len(survivors) < MIN_POPULATION and scored:
            # Keep at least MIN_POPULATION even if below diversity floor
            survivors = scored[:MIN_POPULATION]

        self._population = [g for g, _ in survivors]

        # Trim cache to avoid unbounded growth
        if len(self._fitness_cache) > POPULATION_SIZE * 3:
            keep_ids = {g.genome_id for g in self._population}
            self._fitness_cache = {k: v for k, v in self._fitness_cache.items() if k in keep_ids}

    # ── Lineage weight update ────────────────────────────────────────────────

    def _update_operator_weights(self) -> None:
        boosts = self.ledger.get_operator_boosts()
        for op_name, boost in boosts.items():
            if op_name in self._operator_weights:
                # Blend new boost with existing weight (exponential moving average)
                self._operator_weights[op_name] = (
                    0.7 * self._operator_weights[op_name] + 0.3 * boost
                )

    # ── Prophecy ledger storage ──────────────────────────────────────────────

    def _store_top_predictions(self, top_n: int = 20) -> None:
        """Store top genomes in prophecy ledger for future real-world matching."""
        scored = [(g, self._evaluate(g)) for g in self._population]
        scored.sort(key=lambda x: x[1], reverse=True)
        for genome, fitness in scored[:top_n]:
            emb = compute_embedding(genome)
            lineage_id = f"{genome.parent_genome_id[:8] if genome.parent_genome_id else 'seed'}_{genome.mutation_history[-1] if genome.mutation_history else 'init'}"
            self.ledger.store_prediction(
                genome_id=genome.genome_id,
                embedding=emb,
                lineage_id=lineage_id,
                operators=list(genome.mutation_history),
                fitness=fitness,
                flags=list(genome.flags),
            )

    # ── Add to novelty index ─────────────────────────────────────────────────

    def _register_novel_survivors(self) -> None:
        for genome in self._population:
            ns = self.novelty.score(genome)
            if ns >= 0.5:
                self.novelty.add(genome)

    # ── Main loop ────────────────────────────────────────────────────────────

    def run(self, generations: int | None = None) -> dict:
        """
        Main PBT loop. Returns final population stats.
        Called by nightly Celery worker.
        """
        n_gens = generations or self.generations
        t_start = time.monotonic()
        weight_update_interval = 500  # update operator weights every 500 gens

        for gen in range(n_gens):
            self._pbt_step()

            if (gen + 1) % weight_update_interval == 0:
                self._update_operator_weights()
                self._store_top_predictions()
                logger.info(
                    "PBT checkpoint",
                    generation=gen + 1,
                    population=len(self._population),
                    elapsed_s=round(time.monotonic() - t_start, 1),
                )

        self._register_novel_survivors()
        self._store_top_predictions(top_n=50)

        scored = [(g, self._evaluate(g)) for g in self._population]
        scored.sort(key=lambda x: x[1], reverse=True)
        top_fitness = scored[0][1] if scored else 0.0

        return {
            "generations_run": n_gens,
            "final_population": len(self._population),
            "top_fitness": round(top_fitness, 6),
            "elapsed_s": round(time.monotonic() - t_start, 1),
            "ledger_stats": self.ledger.get_stats(),
        }

    def top_genomes(self, n: int = 10) -> list[tuple["FraudGenome", float]]:
        """Returns top-n genomes by fitness — used by human gate queue."""
        scored = [(g, self._evaluate(g)) for g in self._population]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:n]
