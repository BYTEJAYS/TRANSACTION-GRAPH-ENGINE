"""
Evolutionary Red Team.

A genetic algorithm over attack genomes. Each genome is evaluated against the
real Blue Team via the oracle; fitness rewards evasion + stealth and penalises
graph distortion + genome complexity, with infeasible (objective-breaking)
attacks driven to the bottom. Mutation and crossover combine successful attacks
into increasingly sophisticated ones, generation after generation.

Fitness is made deterministic per genome (the apply-rng is seeded from the genome
hash) so identical genomes cache, which keeps oracle calls bounded.
"""
from __future__ import annotations

import hashlib
import random
import statistics
from dataclasses import dataclass, field

from ...common.attack_graph import AttackGraph, distortion
from ...common.oracle import (BlueTeamOracle, OperationDetection, VERDICT_SCORE)
from ...config import EvolutionConfig
from ..base import AGENT_NAMES, Genome, Move, apply_genome, genome_repr


def stable_seed(key: str) -> int:
    """Process-independent 32-bit seed from a genome string.

    The builtin ``hash`` is salted per process (PYTHONHASHSEED), so seeding the
    per-genome apply-rng from it makes "deterministic" fitness silently vary run
    to run. blake2b is stable across processes, restoring real reproducibility.
    """
    return int.from_bytes(
        hashlib.blake2b(key.encode("utf-8"), digest_size=4).digest(), "big")


@dataclass
class Individual:
    genome: Genome
    fitness: float = -1e9
    detection_score: float = 1.0
    stealth: float = 0.0
    distortion: float = 1.0
    complexity: float = 0.0
    objective_ok: bool = False
    evaded: bool = False
    worst_verdict: str = "FRAUD"
    max_cluster_risk: float = 1.0
    num_components: int = 1
    evidence: set[str] = field(default_factory=set)
    # expectation/variance over agent randomness (eval_samples realizations)
    evasion_rate: float = 0.0       # fraction of realizations that evaded
    obj_ok_rate: float = 0.0        # fraction with the objective intact
    detection_std: float = 0.0      # std of detection score across realizations
    n_samples: int = 1

    @property
    def repr(self) -> str:
        return genome_repr(self.genome)


class EvolutionaryRedTeam:
    def __init__(self, oracle: BlueTeamOracle, base: AttackGraph,
                 cfg: EvolutionConfig | None = None) -> None:
        self.oracle = oracle
        self.base = base
        self.cfg = cfg or EvolutionConfig()
        # the arsenal this search may use (default = every registered agent)
        self.names = list(self.cfg.allowed_agents) if self.cfg.allowed_agents else list(AGENT_NAMES)
        self.rng = random.Random(self.cfg.seed)
        self._cache: dict[str, Individual] = {}
        self.history: list[dict] = []
        self.best: Individual | None = None

    # ── fitness ───────────────────────────────────────────────────────────────
    def evaluate(self, genome: Genome) -> Individual:
        """Fitness as an EXPECTATION over agent randomness.

        Stochastic agents (amount_dither, decoy_edges, temporal_spread, relay/sink
        node ids) make a single realization an unreliable estimate: a genome may
        "evade" only under one lucky draw. We therefore evaluate ``eval_samples``
        independent realizations (seeded deterministically from the genome) and
        aggregate. An attack counts as a success only if it evades in at least a
        ``success_quorum`` fraction of realizations — a robust, reproducible
        attack, not a one-off fluke.
        """
        key = genome_repr(genome)
        if key in self._cache:
            return self._cache[key]

        W = self.cfg.weights
        complexity = len(genome) / max(1, self.cfg.max_genome_len)
        base_seed = stable_seed(key)
        samples = max(1, self.cfg.eval_samples)

        det_scores: list[float] = []
        fits: list[float] = []
        stealths: list[float] = []
        dists: list[float] = []
        risks: list[float] = []
        comps: list[int] = []
        verdicts: list[str] = []
        obj_oks: list[bool] = []
        evades: list[bool] = []
        evidence: set[str] = set()

        for i in range(samples):
            ag = apply_genome(self.base, genome, random.Random(base_seed + i))
            obj_ok = ag.objective_satisfied()
            obj_oks.append(obj_ok)
            comps.append(ag.num_components())
            if not obj_ok:
                det_scores.append(1.0); stealths.append(0.0); dists.append(1.0)
                risks.append(1.0); verdicts.append("FRAUD"); evades.append(False)
                fits.append(-W.infeasible_penalty - 0.01 * complexity)
                continue
            det: OperationDetection = self.oracle.detect(ag)
            dist = distortion(self.base, ag)
            stealth = max(0.0, 1.0 - det.max_cluster_risk)
            det_scores.append(det.detection_score); stealths.append(stealth)
            dists.append(dist); risks.append(det.max_cluster_risk)
            verdicts.append(det.worst_verdict); evades.append(det.evaded)
            evidence.update(det.evidence_patterns)
            fits.append(W.evasion * (1.0 - det.detection_score) + W.stealth * stealth
                        - W.distortion * dist - W.complexity * complexity)

        mean = lambda xs: sum(xs) / len(xs)
        quorum = self.cfg.success_quorum
        obj_ok_rate = mean([1.0 if o else 0.0 for o in obj_oks])
        evasion_rate = mean([1.0 if e else 0.0 for e in evades])
        objective_ok = obj_ok_rate >= quorum
        evaded = objective_ok and evasion_rate >= quorum

        ind = Individual(
            genome=genome, fitness=mean(fits), detection_score=mean(det_scores),
            stealth=mean(stealths), distortion=mean(dists), complexity=complexity,
            objective_ok=objective_ok, evaded=evaded,
            # report the WORST verdict/risk seen across realizations (conservative)
            worst_verdict=max(verdicts, key=lambda v: VERDICT_SCORE.get(v, 1.0)),
            max_cluster_risk=max(risks), num_components=max(comps),
            evidence=evidence, evasion_rate=evasion_rate, obj_ok_rate=obj_ok_rate,
            detection_std=statistics.pstdev(det_scores) if len(det_scores) > 1 else 0.0,
            n_samples=samples,
        )
        self._cache[key] = ind
        return ind

    # ── genetic operators ───────────────────────────────────────────────────────
    def _tournament(self, pop: list[Individual]) -> Individual:
        return max(self.rng.sample(pop, min(self.cfg.tournament_k, len(pop))),
                   key=lambda i: i.fitness)

    def _crossover(self, a: Genome, b: Genome) -> Genome:
        if not a or not b or self.rng.random() > self.cfg.crossover_rate:
            return list(a) if self.rng.random() < 0.5 else list(b)
        ca = self.rng.randint(0, len(a))
        cb = self.rng.randint(0, len(b))
        child = a[:ca] + b[cb:]
        return self._clip_len(child)

    def _rand_move(self) -> Move:
        return Move(agent=self.rng.choice(self.names), intensity=round(self.rng.random(), 3))

    def _rand_genome(self) -> Genome:
        n = self.rng.randint(self.cfg.min_genome_len, self.cfg.max_genome_len)
        return [self._rand_move() for _ in range(n)]

    def _mutate(self, g: Genome) -> Genome:
        if self.rng.random() > self.cfg.mutation_rate:
            return g
        g = list(g)
        op = self.rng.choice(["add", "remove", "tune", "swap", "reorder"])
        if op == "add" and len(g) < self.cfg.max_genome_len:
            g.insert(self.rng.randint(0, len(g)), self._rand_move())
        elif op == "remove" and len(g) > self.cfg.min_genome_len:
            g.pop(self.rng.randint(0, len(g) - 1))
        elif op == "tune" and g:
            i = self.rng.randint(0, len(g) - 1)
            delta = self.rng.uniform(-0.3, 0.3)
            g[i] = Move(g[i].agent, max(0.0, min(1.0, round(g[i].intensity + delta, 3))))
        elif op == "swap" and g:
            i = self.rng.randint(0, len(g) - 1)
            g[i] = Move(self.rng.choice(self.names), g[i].intensity)
        elif op == "reorder" and len(g) > 1:
            self.rng.shuffle(g)
        return self._clip_len(g)

    def _clip_len(self, g: Genome) -> Genome:
        if len(g) > self.cfg.max_genome_len:
            g = g[:self.cfg.max_genome_len]
        if not g:
            g = [self._rand_move()]
        return g

    # ── main loop ───────────────────────────────────────────────────────────────
    def _seed_genomes(self) -> list[Genome]:
        """Warm-start the GA with structured building blocks it can recombine.

        Random genomes rarely contain the 4–5 specific agents a strong evasion
        needs simultaneously, so we seed each single agent plus a few curated
        combinations. Evolution still does the work of tuning intensities,
        ordering, and discovering archetype-specific recipes.
        """
        single = [[Move(name, 0.75)] for name in self.names]
        combos = [
            [Move("feature_mimicry", 0.9), Move("amount_dither", 0.7),
             Move("relay_insertion", 0.7)],
            [Move("feature_mimicry", 0.9), Move("relay_insertion", 0.7),
             Move("cross_component_split", 0.9)],
            [Move("feature_mimicry", 0.9), Move("amount_dither", 0.7),
             Move("relay_insertion", 0.7), Move("temporal_spread", 0.7),
             Move("cross_component_split", 0.9)],
            [Move("feature_mimicry", 0.9), Move("amount_dither", 0.7),
             Move("relay_insertion", 0.7), Move("sink_funnel", 0.8),
             Move("temporal_spread", 0.7), Move("cross_component_split", 0.9)],
            # margin-aware: dilute the volume tell, then partition
            [Move("feature_mimicry", 0.9), Move("volume_dilution", 0.8),
             Move("cross_component_split", 0.9)],
            [Move("feature_mimicry", 0.9), Move("amount_dither", 0.7),
             Move("relay_insertion", 0.7), Move("temporal_spread", 0.7),
             Move("volume_dilution", 0.8), Move("cross_component_split", 0.9)],
            # full multi-factor mimicry vs a margin detector
            [Move("profile_mimicry", 0.9), Move("relay_insertion", 0.8),
             Move("volume_dilution", 0.9), Move("cross_component_split", 0.9)],
            # account-takeover: route the high-value path through seized verified
            # identities to collapse the provenance unverified-value ratio
            [Move("account_takeover", 0.9), Move("cross_component_split", 0.9)],
            [Move("account_takeover", 0.9), Move("relay_insertion", 0.7),
             Move("profile_mimicry", 0.8), Move("cross_component_split", 0.9)],
            # conduit-split: spread cash-out across many seized mules (each in-profile)
            # to beat the behavioural detector, then throttle the resulting fan
            [Move("conduit_split", 0.9), Move("relay_insertion", 0.8),
             Move("cross_component_split", 0.9)],
            [Move("conduit_split", 0.9), Move("relay_insertion", 0.8),
             Move("temporal_spread", 0.7), Move("cross_component_split", 0.9)],
        ]
        allowed = set(self.names)
        combos = [c for c in combos if all(m.agent in allowed for m in c)]
        return [[]] + single + combos

    def evolve(self, verbose: bool = False) -> Individual:
        cfg = self.cfg
        # seed population: identity + per-agent + curated combos, then random
        pop: list[Individual] = [self.evaluate(g) for g in self._seed_genomes()]
        while len(pop) < cfg.population_size:
            pop.append(self.evaluate(self._rand_genome()))

        n_elite = max(1, int(cfg.population_size * cfg.elite_fraction))
        for gen in range(cfg.generations):
            pop.sort(key=lambda i: i.fitness, reverse=True)
            self.best = pop[0]
            self.history.append({
                "generation": gen,
                "best_fitness": round(pop[0].fitness, 4),
                "best_detection": round(pop[0].detection_score, 4),
                "best_verdict": pop[0].worst_verdict,
                "best_distortion": round(pop[0].distortion, 4),
                "evaded": pop[0].evaded,
                "oracle_calls": self.oracle.calls,
            })
            if verbose:
                b = pop[0]
                print(f"  gen {gen:02d}  fit={b.fitness:+.3f}  verdict={b.worst_verdict:<10} "
                      f"det={b.detection_score:.2f} risk={b.max_cluster_risk:.2f} "
                      f"dist={b.distortion:.2f} comps={b.num_components} :: {b.repr[:70]}")

            elites = pop[:n_elite]
            children: list[Individual] = list(elites)
            while len(children) < cfg.population_size:
                p1 = self._tournament(pop)
                p2 = self._tournament(pop)
                child_genome = self._mutate(self._crossover(p1.genome, p2.genome))
                children.append(self.evaluate(child_genome))
            pop = children

        pop.sort(key=lambda i: i.fitness, reverse=True)
        self.best = pop[0]
        return self.best
