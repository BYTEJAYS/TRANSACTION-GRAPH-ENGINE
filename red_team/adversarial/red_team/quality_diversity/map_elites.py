"""
MAP-Elites Red Team — quality-diversity search over the attack space.

The scalar GA converges to the single highest-fitness genome, which here is always
the cross_component_split recipe (mode collapse: see audit §2.3 / the genealogy
showing it in every winning family). MAP-Elites instead *illuminates* the space:
it discretises a behaviour-descriptor space into cells and keeps the best-quality
attack in each cell, so genuinely different evasion strategies are preserved side
by side instead of out-competed by the one cheapest recipe.

Behaviour descriptors (the diversity axes):
  * fragmentation — how many components the attack splits into (partition strategy)
  * distortion    — how much the graph was changed (a stealth/cost axis)
Quality (what competes *within* a cell):
  * pure evasion + stealth. Distortion is a descriptor, not a penalty, so we
    illuminate "what is the strongest evasion achievable at THIS distortion and
    THIS fragmentation" across the whole grid.

It reuses EvolutionaryRedTeam for evaluation (inheriting the Phase-A expectation
eval over agent randomness + the genome cache) and for the variation operators,
so QD and the GA are directly comparable on the same primitives.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from ...config import EvolutionConfig, FitnessWeights, QDConfig
from ..base import random_genome
from ..evolutionary_engine.engine import EvolutionaryRedTeam, Individual


def _agent_family(ind: Individual) -> str:
    return "+".join(sorted({m.agent for m in ind.genome})) or "(identity)"


@dataclass
class QDStats:
    evaluations: int
    cells_total: int
    cells_filled: int
    cells_evading: int
    coverage: float
    qd_score: float
    families: int            # distinct technique signatures among evading elites


class MapElitesRedTeam:
    def __init__(self, oracle, base, qd: QDConfig | None = None) -> None:
        self.qd = qd or QDConfig()
        # inner GA reused purely for evaluate() + operators. High mutation so QD
        # variation actually explores; its scalar fitness is unused (we recompute
        # quality from the Individual's measured fields).
        inner = EvolutionConfig(
            eval_samples=self.qd.eval_samples, success_quorum=self.qd.success_quorum,
            seed=self.qd.seed, mutation_rate=0.9, crossover_rate=0.6,
            weights=FitnessWeights())
        self._ev = EvolutionaryRedTeam(oracle, base, inner)
        self.rng = self._ev.rng
        self.archive: dict[tuple[int, int], Individual] = {}
        self.curiosity: dict[tuple[int, int], float] = {}
        self._evals = 0

    # ── descriptor + quality ──────────────────────────────────────────────────
    def _frag_bin(self, num_components: int) -> int:
        for i, hi in enumerate((1, 3, 7, 15)):
            if num_components <= hi:
                return i
        return self.qd.frag_bins - 1

    def _dist_bin(self, distortion: float) -> int:
        d = max(0.0, min(0.999, distortion))
        return min(self.qd.distortion_bins - 1, int(d * self.qd.distortion_bins))

    def _quality(self, ind: Individual) -> float:
        return self.qd.evasion * (1.0 - ind.detection_score) + self.qd.stealth * ind.stealth

    # ── archive ops ───────────────────────────────────────────────────────────
    def _decay(self, key: tuple[int, int]) -> None:
        self.curiosity[key] = max(0.1, self.curiosity.get(key, 1.0) * 0.9)

    def _add(self, genome, parent_key) -> bool:
        self._evals += 1
        ind = self._ev.evaluate(genome)
        if not ind.objective_ok:                      # infeasible never enters the map
            if parent_key is not None:
                self._decay(parent_key)
            return False
        key = (self._frag_bin(ind.num_components), self._dist_bin(ind.distortion))
        incumbent = self.archive.get(key)
        if incumbent is None or self._quality(ind) > self._quality(incumbent):
            self.archive[key] = ind
            self.curiosity.setdefault(key, 1.0)
            if parent_key is not None:                # reward the cell that produced it
                self.curiosity[parent_key] = self.curiosity.get(parent_key, 1.0) + 1.0
            return True
        if parent_key is not None:
            self._decay(parent_key)
        return False

    def _select_cell(self) -> tuple[int, int]:
        keys = list(self.archive)
        if self.rng.random() < self.qd.curiosity:     # curiosity-biased selection
            scores = [self.curiosity[k] for k in keys]
            total = sum(scores)
            r = self.rng.uniform(0, total)
            acc = 0.0
            for k, s in zip(keys, scores):
                acc += s
                if acc >= r:
                    return k
        return self.rng.choice(keys)                  # otherwise uniform

    # ── main loop ─────────────────────────────────────────────────────────────
    def illuminate(self, verbose: bool = False) -> dict[tuple[int, int], Individual]:
        ev = self._ev
        for g in ev._seed_genomes():                  # structured warm-start building blocks
            self._add(g, None)
        while self._evals < self.qd.init_batch:        # random init to seed cells
            self._add(random_genome(self.rng, 1, ev.cfg.max_genome_len), None)

        while self._evals < self.qd.evaluations:
            pk1 = self._select_cell()
            pk2 = self._select_cell()
            child = ev._mutate(ev._crossover(self.archive[pk1].genome,
                                             self.archive[pk2].genome))
            self._add(child, pk1)
            if verbose and self._evals % 500 == 0:
                s = self.stats()
                print(f"  eval {self._evals:5d}  filled={s.cells_filled:2d}/{s.cells_total} "
                      f"evading={s.cells_evading:2d}  families={s.families}  "
                      f"qd_score={s.qd_score:.2f}")
        return self.archive

    # ── reporting ─────────────────────────────────────────────────────────────
    def stats(self) -> QDStats:
        total = self.qd.frag_bins * self.qd.distortion_bins
        evading = [e for e in self.archive.values() if e.evaded]
        return QDStats(
            evaluations=self._evals, cells_total=total, cells_filled=len(self.archive),
            cells_evading=len(evading), coverage=round(len(self.archive) / total, 3),
            qd_score=round(sum(self._quality(e) for e in self.archive.values()), 3),
            families=len({_agent_family(e) for e in evading}))

    def evading_elites(self) -> list[Individual]:
        return sorted((e for e in self.archive.values() if e.evaded),
                      key=lambda e: e.distortion)

    def render_map(self) -> str:
        """ASCII illumination grid: rows = fragmentation, cols = distortion.

        '#' an evading elite, 'o' a filled-but-detected cell, '·' empty.
        """
        frag_labels = ["1", "2-3", "4-7", "8-15", "16+"][: self.qd.frag_bins]
        out = ["      distortion →  " + "".join(f"{i:>3}" for i in range(self.qd.distortion_bins)),
               "  frag ↓"]
        for f in range(self.qd.frag_bins):
            row = []
            for d in range(self.qd.distortion_bins):
                e = self.archive.get((f, d))
                row.append("  #" if (e and e.evaded) else ("  o" if e else "  ·"))
            out.append(f"  {frag_labels[f]:>5} {''.join(row)}")
        return "\n".join(out)
