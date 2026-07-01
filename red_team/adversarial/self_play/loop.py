"""
Self-Play loop — the engine that turns adversarial pressure into robustness.

    for each round:
        Red Team evolves attacks against the CURRENT Blue config   (red phase)
        successful attacks → Attack Memory                         (collect)
        Hardener proposes a tightened Blue config that re-flags     (blue phase)
            those evasions, validated against a benign corpus
        measure ASR before/after + benign false-positive cost       (evaluate)
        adopt the hardened config; promote curriculum on mastery     (advance)

This loop is now *closed*: the Blue config actually changes between rounds, so Red
must re-discover evasions against a moving target — the arms race the program is
built around.

How hardening works (and why it is exact, not heuristic). V2's verdict is a
threshold over a *cluster risk* that is itself threshold-invariant. An operation
evades iff the maximum risk across its components stays below ``review``. So:

  * lowering ``review`` re-flags exactly those evasions whose max-component risk
    is ≥ the new threshold — computable in closed form from stored risks;
  * the benign false-positive rate at any candidate threshold is just the fraction
    of benign components whose risk is ≥ it — one pass over the benign corpus.

The hardener therefore sweeps ``review`` downward and picks the largest tightening
that re-flags the most evasions subject to a benign-FP budget. No retraining, no
gradient, no mutation of shipped constants — the tightened values live in a
``BlueConfig`` the oracle is built from.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..common.blue_config import BlueConfig
from ..common.oracle import BlueTeamOracle
from ..config import EvolutionConfig
from ..attack_memory import AttackMemory
from ..curriculum import level as curriculum_level
from ..red_team.evolutionary_engine import EvolutionaryRedTeam
from ..red_team.graph_generator import make_base_attacks, make_benign_corpus


@dataclass
class Evasion:
    """One successful attack from a round, with the quantity hardening keys on."""
    archetype: str
    max_risk: float        # max risk across the attack's components (threshold-invariant)
    objective_ok: bool = True


@dataclass
class HardeningProposal:
    config: BlueConfig
    review_before: float
    review_after: float
    projected_reflag_rate: float    # fraction of this round's evasions re-flagged
    projected_benign_fp: float      # benign false-positive rate at the new threshold
    n_evasions: int
    note: str = ""

    def summary(self) -> dict:
        return {
            "review_before": round(self.review_before, 4),
            "review_after": round(self.review_after, 4),
            "projected_reflag_rate": round(self.projected_reflag_rate, 4),
            "projected_benign_fp": round(self.projected_benign_fp, 4),
            "n_evasions": self.n_evasions,
        }


class BlueTeamHardener(Protocol):
    """Strategy that proposes a more robust Blue config from a round's evasions."""
    def harden(self, evasions: list[Evasion], benign_risks: list[float],
               current: BlueConfig) -> HardeningProposal: ...


@dataclass
class ThresholdHardener:
    """
    Lower the REVIEW threshold to re-flag near-threshold evasions, bounded by a
    benign false-positive budget. Exact: re-flag and FP rates are closed-form over
    stored risks (see module docstring), so this measures real robustness gain
    rather than gesturing at one.
    """
    max_review_drop: float = 0.15     # never drop review by more than this in total
    fp_budget: float = 0.05           # tolerated benign false-positive rate
    step: float = 0.005

    def harden(self, evasions: list[Evasion], benign_risks: list[float],
               current: BlueConfig) -> HardeningProposal:
        review0 = current.review_threshold
        ev_risks = [e.max_risk for e in evasions]
        n = len(ev_risks)

        def reflag(thr: float) -> float:
            return sum(1 for r in ev_risks if r >= thr) / n if n else 0.0

        def fp(thr: float) -> float:
            return (sum(1 for r in benign_risks if r >= thr) / len(benign_risks)
                    if benign_risks else 0.0)

        if n == 0:
            return HardeningProposal(current, review0, review0, 0.0, fp(review0), 0,
                                     note="no evasions to harden against")

        floor = max(current.log_threshold, review0 - self.max_review_drop)
        # sweep candidate thresholds downward; keep the best feasible one
        best_thr, best_reflag = review0, reflag(review0)
        thr = review0
        while thr >= floor - 1e-9:
            if fp(thr) <= self.fp_budget:
                r = reflag(thr)
                # prefer more re-flagged; tie-break toward the *least* intrusive
                # (highest) threshold so we don't over-tighten for free
                if r > best_reflag + 1e-9:
                    best_reflag, best_thr = r, thr
            thr = round(thr - self.step, 4)

        new_cfg = current.with_review(best_thr)
        return HardeningProposal(
            config=new_cfg, review_before=review0, review_after=new_cfg.review_threshold,
            projected_reflag_rate=best_reflag, projected_benign_fp=fp(new_cfg.review_threshold),
            n_evasions=n,
            note=f"review {review0:.3f}→{new_cfg.review_threshold:.3f} "
                 f"re-flags {best_reflag:.0%} of evasions at "
                 f"{fp(new_cfg.review_threshold):.1%} benign FP")


@dataclass
class SelfPlayRound:
    round: int
    curriculum_level: int
    blue_review: float
    attack_success_rate_before: float
    attack_success_rate_after: float
    robustness_gain: float
    benign_fp_before: float
    benign_fp_after: float
    new_hard_examples: int
    hardening: dict = field(default_factory=dict)


class SelfPlayLoop:
    def __init__(self, memory: AttackMemory | None = None,
                 hardener: BlueTeamHardener | None = None,
                 fp_budget: float = 0.05) -> None:
        self.memory = memory or AttackMemory()
        self.hardener = hardener or ThresholdHardener(fp_budget=fp_budget)
        self.blue_config = BlueConfig()           # starts at shipped thresholds
        self.history: list[SelfPlayRound] = []
        self._benign_risks: list[float] | None = None

    # benign risks are threshold-invariant → compute once, reuse every round
    def _benign(self) -> list[float]:
        if self._benign_risks is None:
            probe = BlueTeamOracle(target="v2")    # default config; risk is config-free
            corpus = make_benign_corpus()
            self._benign_risks = [probe.detect_component(c).cluster_risk for c in corpus]
        return self._benign_risks

    def run(self, rounds: int = 4, cfg: EvolutionConfig | None = None,
            mastery_asr: float = 0.34, verbose: bool = False) -> list[SelfPlayRound]:
        cfg = cfg or EvolutionConfig(population_size=40, generations=20)
        bases = make_base_attacks(seed=42)
        benign = self._benign()
        level = 6

        for rnd in range(rounds):
            oracle = BlueTeamOracle(target="v2", blue_config=self.blue_config)
            review_before = self.blue_config.review_threshold
            fp_before = (sum(1 for r in benign if r >= review_before) / len(benign)
                         if benign else 0.0)

            # ── red phase ──
            evasions: list[Evasion] = []
            for base in bases:
                rt = EvolutionaryRedTeam(oracle, base, cfg)
                best = rt.evolve()
                if best.evaded and best.objective_ok:
                    evasions.append(Evasion(base.archetype, best.max_cluster_risk, True))
                    self.memory.remember(
                        attack_id=f"sp{rnd}_{base.archetype}",
                        archetype=base.archetype, target_engine=oracle.target,
                        genome=best.genome, baseline_verdict="FRAUD",
                        final_verdict=best.worst_verdict,
                        detection_score=best.detection_score,
                        cluster_risk=best.max_cluster_risk, distortion=best.distortion,
                        num_components=best.num_components,
                        residual_detectors=best.evidence, objective_ok=True,
                        generation=rnd)
            asr_before = len(evasions) / len(bases)

            # ── blue phase ──
            proposal = self.hardener.harden(evasions, benign, self.blue_config)
            review_after = proposal.config.review_threshold
            # closed-form re-evaluation of THIS round's evasions vs the hardened Blue:
            # an evasion survives iff its max-component risk is still below review.
            still_evaded = [e for e in evasions if e.max_risk < review_after]
            asr_after = len(still_evaded) / len(bases)
            fp_after = proposal.projected_benign_fp

            self.blue_config = proposal.config      # adopt the hardened config

            # ── advance ──
            if asr_after <= mastery_asr:
                level = min(10, level + 1)
            self.history.append(SelfPlayRound(
                round=rnd, curriculum_level=level, blue_review=review_after,
                attack_success_rate_before=round(asr_before, 4),
                attack_success_rate_after=round(asr_after, 4),
                robustness_gain=round(asr_before - asr_after, 4),
                benign_fp_before=round(fp_before, 4), benign_fp_after=round(fp_after, 4),
                new_hard_examples=len(evasions), hardening=proposal.summary()))
            if verbose:
                h = self.history[-1]
                print(f"round {rnd}: L{h.curriculum_level} "
                      f"review {review_before:.3f}→{review_after:.3f}  "
                      f"ASR {h.attack_success_rate_before:.2f}→{h.attack_success_rate_after:.2f} "
                      f"(gain {h.robustness_gain:+.2f})  "
                      f"benign_FP {h.benign_fp_before:.1%}→{h.benign_fp_after:.1%}  "
                      f"[{curriculum_level(level).name}]")
        return self.history
