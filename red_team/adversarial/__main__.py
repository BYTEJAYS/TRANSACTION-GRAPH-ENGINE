"""
Adversarial campaign demo.

For every confirmed-FRAUD archetype:
  1. confirm the Blue Team's baseline verdict,
  2. evolve an attack genome against the real Blue Team,
  3. report whether the laundering objective survived while the verdict collapsed.

Validity instrumentation (Phase A):
  * each genome is scored as an EXPECTATION over agent randomness (--eval-samples);
  * a success must evade in every sampled realization (robust, not a lucky draw);
  * ASR is reported under both the permissive and the strict on-graph objective;
  * --trials runs the whole campaign over multiple seeds and reports mean ± 95% CI.

Run:  cd backend && .venv/bin/python -m adversarial      (or set PYTHONPATH)
      python -m adversarial --generations 20 --population 40 --trials 5
"""
from __future__ import annotations

import argparse
import math
import random

from .attack_memory import AttackMemory
from .common.oracle import BlueTeamOracle
from .config import EvolutionConfig
from .evaluation.metrics import CampaignResult, evaluate_baseline, summarize_campaign
from .red_team.base import apply_genome
from .red_team.evolutionary_engine import EvolutionaryRedTeam
from .red_team.evolutionary_engine.engine import stable_seed
from .red_team.graph_generator import make_base_attacks


def run_once(generations: int, population: int, eval_samples: int,
             graph_seed: int, ga_seed: int, *, verbose: bool, quiet: bool,
             memory: AttackMemory | None) -> dict:
    """One full campaign at a fixed (graph_seed, ga_seed). Returns the summary."""
    oracle = BlueTeamOracle(target="v2")
    bases = make_base_attacks(seed=graph_seed)
    cfg = EvolutionConfig(population_size=population, generations=generations,
                          eval_samples=eval_samples, seed=ga_seed)

    results: list[CampaignResult] = []
    for base in bases:
        baseline = evaluate_baseline(oracle, base)
        calls0 = oracle.calls
        rt = EvolutionaryRedTeam(oracle, base, cfg)
        best = rt.evolve(verbose=verbose)

        # strict check: re-realize the best genome and test the on-graph objective.
        ag0 = apply_genome(base, best.genome, random.Random(stable_seed(best.repr)))
        strict_ok = base.objective.on_graph_satisfied(ag0.components)

        results.append(CampaignResult(
            archetype=base.archetype,
            baseline_verdict=baseline.worst_verdict,
            baseline_risk=baseline.max_cluster_risk,
            baseline_detectors=baseline.evidence_patterns,
            best_verdict=best.worst_verdict,
            best_risk=best.max_cluster_risk,
            best_detection=best.detection_score,
            best_distortion=best.distortion,
            evaded=best.evaded,
            objective_ok=best.objective_ok,
            residual_detectors=best.evidence,
            genome=best.repr,
            num_components=best.num_components,
            oracle_calls=oracle.calls - calls0,
            strict_objective_ok=strict_ok,
            evasion_rate=best.evasion_rate,
            detection_std=best.detection_std,
        ))
        if best.evaded and best.objective_ok and memory is not None:
            memory.remember(
                attack_id=f"g{graph_seed}_{base.archetype}",
                archetype=base.archetype, target_engine=oracle.target,
                genome=best.genome, baseline_verdict=baseline.worst_verdict,
                final_verdict=best.worst_verdict, detection_score=best.detection_score,
                cluster_risk=best.max_cluster_risk, distortion=best.distortion,
                num_components=best.num_components, residual_detectors=best.evidence,
                objective_ok=True)
        if not quiet:
            mark = "✓ EVADED" if (best.evaded and best.objective_ok) else "· held"
            strict = "" if strict_ok else "  ⚠ partition-dependent"
            print(f"  {base.archetype:<16} {baseline.worst_verdict:>10} → "
                  f"{best.worst_verdict:<10} risk {baseline.max_cluster_risk:.2f}→"
                  f"{best.max_cluster_risk:.2f}  dist={best.distortion:.2f}  "
                  f"comps={best.num_components}  evade_rate={best.evasion_rate:.2f}  "
                  f"{mark}{strict}")
            if verbose:
                print(f"     genome: {best.repr}")
    return summarize_campaign(results)


def _ci95(xs: list[float]) -> tuple[float, float]:
    """Mean and half-width of a 95% confidence interval (normal approx)."""
    n = len(xs)
    m = sum(xs) / n
    if n < 2:
        return m, 0.0
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return m, 1.96 * sd / math.sqrt(n)


def run(generations: int, population: int, eval_samples: int, trials: int,
        verbose: bool) -> None:
    print(f"\n{'='*78}\n TGiE ADVERSARIAL CAMPAIGN — Red Team (evolutionary) vs Blue Team V2\n{'='*78}")
    print(f" population={population}  generations={generations}  "
          f"eval_samples={eval_samples}  trials={trials}\n")

    memory = AttackMemory() if trials == 1 else None
    summaries: list[dict] = []
    for t in range(trials):
        if trials > 1:
            print(f"── trial {t+1}/{trials}  (graph_seed={42+t}, ga_seed={1234+t}) ──")
        summary = run_once(
            generations, population, eval_samples,
            graph_seed=42 + t, ga_seed=1234 + t,
            verbose=verbose, quiet=(trials > 1 and not verbose), memory=memory)
        summaries.append(summary)
        if trials > 1:
            print(f"   ASR={summary['attack_success_rate']}  "
                  f"strict={summary['attack_success_rate_strict']}  "
                  f"partition-dependent={summary['partition_dependent_evasions']}")

    print(f"\n{'-'*78}\n CAMPAIGN SUMMARY\n{'-'*78}")
    if trials == 1:
        for k, v in summaries[0].items():
            print(f"  {k:32} {v}")
        if memory is not None:
            geneal = memory.genealogy()
            if geneal:
                print(f"\n{'-'*78}\n ATTACK GENEALOGY (families that defeated the Blue Team)\n{'-'*78}")
                for fam, info in list(geneal.items())[:10]:
                    print(f"  [{info['best_verdict']:<8} d={info['cheapest_distortion']:.2f}] "
                          f"{'+'.join(info['agents'])}  →  {', '.join(info['defeats_archetypes'])}")
    else:
        asr = [s["attack_success_rate"] for s in summaries]
        asr_s = [s["attack_success_rate_strict"] for s in summaries]
        m, h = _ci95(asr)
        ms, hs = _ci95(asr_s)
        print(f"  trials                            {trials}")
        print(f"  attack_success_rate (permissive)  {m:.3f} ± {h:.3f}  (95% CI)  "
              f"range [{min(asr):.3f}, {max(asr):.3f}]")
        print(f"  attack_success_rate (strict)      {ms:.3f} ± {hs:.3f}  (95% CI)  "
              f"range [{min(asr_s):.3f}, {max(asr_s):.3f}]")
        print(f"  mean partition-dependent evasions "
              f"{sum(s['partition_dependent_evasions'] for s in summaries)/trials:.2f}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description="TGiE adversarial campaign")
    ap.add_argument("--generations", type=int, default=18)
    ap.add_argument("--population", type=int, default=36)
    ap.add_argument("--eval-samples", type=int, default=3,
                    help="realizations per genome (expectation over agent RNG)")
    ap.add_argument("--trials", type=int, default=1,
                    help="repeat the campaign over N seeds; report ASR mean ± 95%% CI")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    run(args.generations, args.population, args.eval_samples, args.trials, args.verbose)


if __name__ == "__main__":
    main()
