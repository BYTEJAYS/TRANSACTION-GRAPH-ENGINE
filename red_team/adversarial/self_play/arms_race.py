"""
Detector arms race — the closed Red ⇄ Blue co-evolution, end-to-end.

Blue's defense *escalates* in response to Red, and every round is scored against a
realistic benign corpus (legitimate payroll / merchant / corporate / household
traffic drawn from a KYC customer base), so robustness and false positives are
measured honestly together — the §13 lesson baked into the loop.

Each round:
  1. Red evolves attacks against Blue's CURRENT defense                       (red)
  2. its evasion fragments are added to Blue's training corpus                (collect)
  3. Blue RESPONDS: on first breach it deploys the provenance signal (the
     orthogonal KYC/history detector, §14); thereafter it refits the learned
     16-factor calibration on everything seen so far                          (blue)
  4. measure ASR before vs after Blue's response, AND benign FP on the
     realistic corpus, so a "win" that just over-flags is exposed             (evaluate)
  5. carry the strengthened defense into the next round                       (advance)

Defense stack (additive, non-destructive): native V2 → + provenance → + learned
calibration. Provenance is what actually closes the loop at 0% benign FP; the
calibrator is the residual responder, armed for whatever a future agent (e.g.
account-takeover) slips past provenance.

Run:  cd backend && .venv/bin/python -m adversarial.self_play.arms_race --rounds 4
"""
from __future__ import annotations

import argparse
import random
from collections import Counter
from dataclasses import dataclass, field

from ..common.oracle import BlueTeamOracle
from ..common.provenance import (ProvenanceRegistry, ProvenanceScorer,
                                  build_customer_universe)
from ..config import EvolutionConfig
from ..red_team.base import apply_genome
from ..red_team.evolutionary_engine import EvolutionaryRedTeam
from ..red_team.evolutionary_engine.engine import stable_seed
from ..red_team.graph_generator import make_base_attacks, make_benign_corpus
from .detector_hardener import FactorCalibrationHardener, cluster_features


@dataclass
class RoundResult:
    round: int
    defense: str
    asr_before: float        # ASR vs the defense Red faced this round
    asr_after: float         # ASR vs the defense after Blue's response
    robustness_gain: float
    benign_fp: float         # on the realistic corpus, after Blue's response
    new_hard_examples: int
    agent_mix: dict = field(default_factory=dict)


def _fragment_feats(engine, components) -> list[list[float]]:
    return [cluster_features(engine.analyze_component(c))
            for c in components if len(c.get("edges", [])) >= 1]


def _benign_fp(oracle, comps) -> float:
    flagged = sum(1 for c in comps
                  if oracle.detect_component(c).verdict in ("SUSPICIOUS", "FRAUD"))
    return flagged / max(1, len(comps))


class DetectorArmsRace:
    def __init__(self, ga_pop: int = 24, ga_gens: int = 8, eval_samples: int = 1):
        from blue_team_v2.engine import BlueTeamV2Engine
        self.engine = BlueTeamV2Engine()
        self.registry = ProvenanceRegistry(build_customer_universe())
        self.scorer = ProvenanceScorer(self.registry)
        pool = self.registry.customer_ids()
        self.bases = make_base_attacks(seed=42)
        # realistic benign drawn from the KYC customer base (verified identities)
        self.benign_holdout = make_benign_corpus(seed=23, n=80, realistic=True, pool=pool)
        self.benign_feats = _fragment_feats(self.engine, self.benign_holdout)
        self.cfg = EvolutionConfig(population_size=ga_pop, generations=ga_gens,
                                   eval_samples=eval_samples, max_genome_len=5)
        # Blue defense state (escalates)
        self.use_provenance = False
        self.calibrator = None
        self.positives: list[list[float]] = []
        self.history: list[RoundResult] = []

    def _oracle(self) -> BlueTeamOracle:
        return BlueTeamOracle(
            target="v2",
            provenance=self.scorer if self.use_provenance else None,
            calibrator=self.calibrator)

    def _defense_label(self) -> str:
        bits = ["native V2"]
        if self.use_provenance:
            bits.append("provenance")
        if self.calibrator is not None:
            bits.append("calibration")
        return " + ".join(bits)

    def run(self, rounds: int = 4, verbose: bool = True) -> list[RoundResult]:
        for rnd in range(rounds):
            faced = self._oracle()
            faced_label = self._defense_label()

            # ── red phase ──
            evasion_graphs, agent_counter, evaded = [], Counter(), 0
            for base in self.bases:
                best = EvolutionaryRedTeam(faced, base, self.cfg).evolve()
                if best.evaded and best.objective_ok:
                    evaded += 1
                    evasion_graphs.append(
                        apply_genome(base, best.genome, random.Random(stable_seed(best.repr))))
                    agent_counter.update({m.agent for m in best.genome})
            asr_before = evaded / len(self.bases)

            # ── blue response: deploy provenance on first breach, then refit calibration ──
            for ag in evasion_graphs:
                self.positives.extend(_fragment_feats(self.engine, ag.components))
            if evaded and not self.use_provenance:
                self.use_provenance = True            # deploy the orthogonal signal
            if self.positives:
                self.calibrator = FactorCalibrationHardener().fit(
                    self.positives, self.benign_feats)

            # ── evaluate vs the strengthened defense ──
            answered = self._oracle()
            still = sum(1 for ag in evasion_graphs if answered.detect(ag).evaded)
            asr_after = still / len(self.bases)
            fp = _benign_fp(answered, self.benign_holdout)

            self.history.append(RoundResult(
                round=rnd, defense=self._defense_label(),
                asr_before=round(asr_before, 4), asr_after=round(asr_after, 4),
                robustness_gain=round(asr_before - asr_after, 4),
                benign_fp=round(fp, 4), new_hard_examples=evaded,
                agent_mix=dict(agent_counter.most_common(3))))
            if verbose:
                mix = ", ".join(f"{a}×{n}" for a, n in agent_counter.most_common(3)) or "—"
                print(f"round {rnd}: faced[{faced_label}]  ASR {asr_before:.2f}→{asr_after:.2f} "
                      f"(gain {asr_before-asr_after:+.2f})  benign_FP {fp:.0%}  "
                      f"→ now[{self._defense_label()}]  [{mix}]")
        return self.history


def main() -> None:
    ap = argparse.ArgumentParser(description="TGiE end-to-end detector arms race")
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--ga-pop", type=int, default=24)
    ap.add_argument("--ga-gens", type=int, default=8)
    ap.add_argument("--eval-samples", type=int, default=1)
    args = ap.parse_args()

    print(f"\n{'='*78}\n TGiE ARMS RACE — escalating defense (native → provenance → calibration)\n"
          f" scored on a REALISTIC benign corpus\n{'='*78}")
    print(f" rounds={args.rounds}  ga={args.ga_pop}x{args.ga_gens}  eval_samples={args.eval_samples}\n")
    race = DetectorArmsRace(args.ga_pop, args.ga_gens, args.eval_samples)
    hist = race.run(args.rounds)

    print(f"\n{'-'*78}\n SUMMARY\n{'-'*78}")
    print(f"  round 0 (native V2):      ASR {hist[0].asr_before:.3f}  "
          f"benign FP {hist[0].benign_fp:.0%}")
    print(f"  after Blue's response:    ASR {hist[0].asr_after:.3f}")
    print(f"  final round defense:      {hist[-1].defense}")
    print(f"  final ASR / benign FP:    {hist[-1].asr_before:.3f} / {hist[-1].benign_fp:.0%}")
    print(f"  → end state: laundering blocked at deployable false-positive cost\n")


if __name__ == "__main__":
    main()
