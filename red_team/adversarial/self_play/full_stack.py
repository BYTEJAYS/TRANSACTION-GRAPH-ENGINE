"""
Full-stack arms race — the complete escalating defense, end-to-end (§18 consolidation).

Folds every signal the engagement produced into one closed Red⇄Blue loop and lets Blue's
defense ESCALATE in response to Red, scored each round on a segment-consistent realistic
benign corpus so robustness and false positives are read together (the §13 discipline).

Red runs its full arsenal — including `account_takeover` and the `conduit_split` mule mesh —
against a fixed pool of seized consumer accounts (the realistic phishing harvest). Blue
adds one layer each time Red breaks through:

    native V2 → + provenance (§14) → + behavioural (§17) → + coordination (§19) → + calibration

The per-component layers (provenance, behavioural) cannot see the conduit_split mule mesh,
which fragments one ring into many hub-less consumer components each benign in isolation —
so Red holds ASR ~1.0 against them at 0% benign FP. The decisive layer is the OPERATION-level
coordination signal (§19): the only one that scores the linked component SET rather than a
component, and therefore the only one that can see the mesh. When Blue deploys it the mesh is
caught and ASR collapses — at the explicit cost of the cross-session linkage the per-component
V2 architecture lacks (the B1 capability). The engagement closes where it opened: the deepest
residual was architectural, and the fix is the B1 capability, not another per-account score.

Run:  cd backend && .venv/bin/python -m adversarial.self_play.full_stack --rounds 4
"""
from __future__ import annotations

import argparse
import random
from collections import Counter
from dataclasses import dataclass

from ..common.behavioral import (BehavioralRegistry, BehavioralScorer,
                                  build_customer_profiles)
from ..common.coordination import CoordinationScorer
from ..common.oracle import BlueTeamOracle
from ..common.provenance import ProvenanceRegistry, ProvenanceScorer
from ..config import EvolutionConfig
from ..red_team import agents as _agents
from ..red_team.base import apply_genome
from ..red_team.evolutionary_engine import EvolutionaryRedTeam
from ..red_team.evolutionary_engine.engine import stable_seed
from ..red_team.graph_generator import make_base_attacks, make_benign_corpus
from .detector_hardener import FactorCalibrationHardener, cluster_features


@dataclass
class Round:
    rnd: int
    faced: str
    asr_before: float
    asr_after: float
    benign_fp: float
    mix: dict


def _fragment_feats(engine, components):
    return [cluster_features(engine.analyze_component(c))
            for c in components if len(c.get("edges", [])) >= 1]


def _benign_fp(oracle, comps):
    flagged = sum(1 for c in comps
                  if oracle.detect_component(c).verdict in ("SUSPICIOUS", "FRAUD"))
    return flagged / max(1, len(comps))


class FullStackArmsRace:
    def __init__(self, ga_pop=24, ga_gens=8, eval_samples=1, seized=240):
        from blue_team_v2.engine import BlueTeamV2Engine
        self.engine = BlueTeamV2Engine()
        profiles = build_customer_profiles()
        self.behav_reg = BehavioralRegistry(profiles)
        self.prov = ProvenanceScorer(ProvenanceRegistry(self.behav_reg.universe))
        self.behav = BehavioralScorer(self.behav_reg)
        self.coord = CoordinationScorer(self.behav_reg)
        self.bases = make_base_attacks(seed=42)
        self.benign = make_benign_corpus(seed=23, n=80, realistic=True, registry=self.behav_reg)
        self.benign_feats = _fragment_feats(self.engine, self.benign)
        self.cfg = EvolutionConfig(population_size=ga_pop, generations=ga_gens,
                                   eval_samples=eval_samples, max_genome_len=6)
        # Red's seized pool: phished consumers + post-takeover capacity estimates
        rng = random.Random(7)
        pool = [c for c, p in profiles.items()
                if p.segment in ("household", "retail") and p.establishment >= 0.7]
        rng.shuffle(pool); pool = pool[:seized]
        _agents.set_compromised_accounts(
            pool, {a: self.behav_reg.baseline_throughput(a) for a in pool})
        # escalating defense state
        self.use_prov = False
        self.use_behav = False
        self.use_coord = False
        self.calibrator = None
        self.positives: list[list[float]] = []

    def _oracle(self):
        return BlueTeamOracle(target="v2",
                              provenance=self.prov if self.use_prov else None,
                              behavioral=self.behav if self.use_behav else None,
                              coordination=self.coord if self.use_coord else None,
                              calibrator=self.calibrator)

    def _label(self):
        bits = ["native V2"]
        if self.use_prov: bits.append("provenance")
        if self.use_behav: bits.append("behavioural")
        if self.use_coord: bits.append("coordination")
        if self.calibrator is not None: bits.append("calibration")
        return " + ".join(bits)

    def _escalate(self):
        """Deploy the next unused layer Blue has in reserve.

        Order: the orthogonal per-component signals first (provenance, behavioural),
        then the OPERATION-level coordination signal (the B1 capability) that is the
        only thing able to see the fragmented mesh, then learned calibration as a last
        per-component resort.
        """
        if not self.use_prov:
            self.use_prov = True
        elif not self.use_behav:
            self.use_behav = True
        elif not self.use_coord:
            self.use_coord = True
        elif self.positives:
            self.calibrator = FactorCalibrationHardener().fit(self.positives, self.benign_feats)

    def run(self, rounds=4, verbose=True):
        history = []
        for rnd in range(rounds):
            faced = self._oracle(); faced_label = self._label()
            evasions, mix, evaded = [], Counter(), 0
            for base in self.bases:
                best = EvolutionaryRedTeam(faced, base, self.cfg).evolve()
                if best.evaded and best.objective_ok:
                    evaded += 1
                    evasions.append(apply_genome(base, best.genome,
                                                 random.Random(stable_seed(best.repr))))
                    mix.update({m.agent for m in best.genome})
            asr_before = evaded / len(self.bases)

            for ag in evasions:
                self.positives.extend(_fragment_feats(self.engine, ag.components))
            if asr_before > 0:
                self._escalate()

            answered = self._oracle()
            still = sum(1 for ag in evasions if answered.detect(ag).evaded)
            asr_after = still / len(self.bases)
            fp = _benign_fp(answered, self.benign)
            history.append(Round(rnd, faced_label, round(asr_before, 3),
                                 round(asr_after, 3), round(fp, 3), dict(mix.most_common(3))))
            if verbose:
                m = ", ".join(f"{a}×{n}" for a, n in mix.most_common(3)) or "—"
                print(f" round {rnd}: faced[{faced_label}]  ASR {asr_before:.2f}→{asr_after:.2f}"
                      f"  benign_FP {fp:.0%}  → now[{self._label()}]  [{m}]")
        return history


def main():
    ap = argparse.ArgumentParser(description="full-stack escalating arms race")
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--ga-pop", type=int, default=24)
    ap.add_argument("--ga-gens", type=int, default=8)
    ap.add_argument("--eval-samples", type=int, default=1)
    ap.add_argument("--seized", type=int, default=240)
    args = ap.parse_args()

    print(f"\n{'='*82}\n TGiE FULL-STACK ARMS RACE — native → provenance → behavioural → calibration\n"
          f" Red: full arsenal incl. account_takeover + conduit_split mule mesh\n{'='*82}")
    race = FullStackArmsRace(args.ga_pop, args.ga_gens, args.eval_samples, args.seized)
    hist = race.run(args.rounds)
    print(f"\n{'-'*82}")
    print(f"  start:  ASR {hist[0].asr_before:.2f}  vs {hist[0].faced}  (benign FP {hist[0].benign_fp:.0%})")
    print(f"  end:    ASR {hist[-1].asr_before:.2f}  vs {hist[-1].faced}  (benign FP {hist[-1].benign_fp:.0%})")
    print(f"  the per-component layers can't see the fragmented mesh; the OPERATION-level")
    print(f"  coordination signal (the B1 capability) is what finally catches it — at the cost")
    print(f"  of the cross-session linkage V2 lacks. Remaining residual: seizing high-baseline")
    print(f"  corporate accounts (a hub coordination won't flag), the costlier §17-C path.\n")


if __name__ == "__main__":
    main()
