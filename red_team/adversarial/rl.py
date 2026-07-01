"""
PPO Red Team campaign — train one policy to evade the real Blue Team via
sequential edits, then evaluate it greedily and contrast with the scalar GA.

Where the GA searches whole genomes, the PPO agent makes one move at a time
conditioned on the Blue Team's current reaction (the MDP in
``red_team/rl_agent/spec.py``). It shares the exact action primitives and oracle,
so the two are directly comparable on ASR against the same confirmed-FRAUD graphs.

Run:  cd backend && .venv/bin/python -m adversarial.rl --updates 80
      python -m adversarial.rl --updates 120 --compare --surrogate
"""
from __future__ import annotations

import argparse

from .attack_memory import AttackMemory
from .common.oracle import BlueTeamOracle
from .config import EvolutionConfig
from .red_team.base import genome_repr
from .red_team.evolutionary_engine import EvolutionaryRedTeam
from .red_team.graph_generator import make_base_attacks
from .red_team.rl_agent import PPOConfig, PPORedTeam


def main() -> None:
    ap = argparse.ArgumentParser(description="TGiE PPO Red Team (sequential-edit evasion)")
    ap.add_argument("--updates", type=int, default=80, help="PPO update iterations")
    ap.add_argument("--rollout", type=int, default=256, help="transitions/env/update")
    ap.add_argument("--max-steps", type=int, default=12, help="edits per episode")
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--entropy", type=float, default=0.01)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--arsenal", choices=["cheap", "full"], default="cheap",
                    help="cheap = 7 fast structural agents (default); full = all 11 "
                         "(incl. volume_dilution/profile_mimicry, which build very large "
                         "graphs and are slow without the surrogate world-model)")
    ap.add_argument("--surrogate", action="store_true",
                    help="accelerate rollouts with a distilled differentiable V2 surrogate")
    ap.add_argument("--compare", action="store_true",
                    help="also run the scalar GA on a comparable budget")
    ap.add_argument("--remember", action="store_true",
                    help="store greedy evasions to attack memory")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    oracle = BlueTeamOracle(target="v2")

    surrogate = None
    if args.surrogate:
        from .red_team.graph_gan import VerdictSurrogate
        surrogate = VerdictSurrogate.distill(oracle, epochs=60, seed=args.seed, verbose=args.verbose)
        print(f"  surrogate distilled — fidelity to V2: "
              f"MAE={surrogate.fidelity['mae']:.3f}  verdict_acc={surrogate.fidelity['acc']:.2f}\n")

    CHEAP = ["amount_dither", "cross_component_split", "decoy_edges", "feature_mimicry",
             "relay_insertion", "sink_funnel", "temporal_spread"]
    arsenal = CHEAP if args.arsenal == "cheap" else None

    cfg = PPOConfig(rollout_steps=args.rollout, lr=args.lr,
                    entropy_coef=args.entropy, seed=args.seed)
    rt = PPORedTeam(target="v2", oracle=oracle, arsenal=arsenal, max_steps=args.max_steps,
                    surrogate=surrogate, ppo=cfg)

    print(f"\n{'='*78}\n TGiE PPO RED TEAM — sequential-edit evasion vs the real V2\n{'='*78}")
    print(f" archetypes={len(rt.envs)}  updates={args.updates}  rollout={args.rollout}  "
          f"max_steps={args.max_steps}  surrogate={'on' if surrogate else 'off'}")
    print(f" state_dim={rt.envs[0].state_dim}  actions={rt.envs[0].n_actions} "
          f"({len(rt.envs[0].names)} agents × 4 intensities)\n")

    asr_before = rt.asr()
    rt.train(updates=args.updates, verbose=args.verbose)
    results = rt.evaluate()
    asr_after = sum(1 for r in results if r.evaded) / max(1, len(results))

    print(f"{'-'*78}\n GREEDY POLICY EVALUATION (scored vs the REAL engine)\n{'-'*78}")
    for r in results:
        tag = "EVADE" if r.evaded else "caught"
        print(f"  {r.archetype:<16} {tag:<6} verdict={r.verdict:<10} det={r.detection_score:.2f} "
              f"steps={r.steps} comps={r.num_components}  ::  {genome_repr(r.genome)[:60]}")

    memory = AttackMemory() if args.remember else None
    if memory is not None:
        for r in results:
            if r.evaded:
                memory.remember(
                    attack_id=f"ppo_{r.archetype}", archetype=r.archetype,
                    target_engine=oracle.target, genome=r.genome,
                    baseline_verdict="FRAUD", final_verdict=r.verdict,
                    detection_score=r.detection_score, cluster_risk=0.0,
                    distortion=r.distortion, num_components=r.num_components,
                    residual_detectors=set(), objective_ok=True)

    print(f"\n  PPO ASR: {asr_before:.2f} (untrained) → {asr_after:.2f} (trained) "
          f"vs the real V2 engine")

    if args.compare:
        print(f"\n{'-'*78}\n SCALAR GA BASELINE (same confirmed-FRAUD graphs)\n{'-'*78}")
        bases = make_base_attacks(seed=42)
        ga_evaded = 0
        gens = max(5, args.updates)
        for base in bases:
            ga = EvolutionaryRedTeam(
                oracle, base, EvolutionConfig(population_size=40, generations=gens))
            best = ga.evolve()
            win = best.evaded and best.objective_ok
            ga_evaded += 1 if win else 0
            print(f"  {base.archetype:<16} {'EVADE' if win else 'caught':<6} "
                  f"verdict={best.worst_verdict:<10} det={best.detection_score:.2f}")
        print(f"\n  GA ASR: {ga_evaded/len(bases):.2f}   |   PPO ASR: {asr_after:.2f}")

    print()


if __name__ == "__main__":
    main()
