"""
Self-play campaign — run the closed Red ⇄ Blue arms race and report, per round,
the Attack Success Rate before/after hardening (robustness gain) and the benign
false-positive cost of the hardening.

Run:  cd backend && .venv/bin/python -m adversarial.self_play --rounds 4
      python -m adversarial.self_play --rounds 4 --population 40 --generations 20
"""
from __future__ import annotations

import argparse

from ..config import EvolutionConfig
from .loop import SelfPlayLoop


def main() -> None:
    ap = argparse.ArgumentParser(description="TGiE Red⇄Blue self-play")
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--population", type=int, default=30)
    ap.add_argument("--generations", type=int, default=15)
    ap.add_argument("--eval-samples", type=int, default=3)
    ap.add_argument("--fp-budget", type=float, default=0.05,
                    help="tolerated benign false-positive rate when hardening")
    args = ap.parse_args()

    print(f"\n{'='*78}\n TGiE SELF-PLAY — closed Red ⇄ Blue arms race (V2)\n{'='*78}")
    print(f" rounds={args.rounds}  population={args.population}  "
          f"generations={args.generations}  eval_samples={args.eval_samples}  "
          f"fp_budget={args.fp_budget:.0%}\n")

    loop = SelfPlayLoop(fp_budget=args.fp_budget)
    cfg = EvolutionConfig(population_size=args.population, generations=args.generations,
                          eval_samples=args.eval_samples)
    history = loop.run(rounds=args.rounds, cfg=cfg, verbose=True)

    print(f"\n{'-'*78}\n SELF-PLAY SUMMARY\n{'-'*78}")
    total_gain = sum(h.robustness_gain for h in history)
    print(f"  rounds                       {len(history)}")
    print(f"  ASR round 0 (before any harden) {history[0].attack_success_rate_before:.3f}")
    print(f"  ASR final (after hardening)     {history[-1].attack_success_rate_after:.3f}")
    print(f"  cumulative robustness gain      {total_gain:+.3f}")
    print(f"  final REVIEW threshold          {history[-1].blue_review:.3f}  (shipped 0.620)")
    print(f"  final benign false-positive     {history[-1].benign_fp_after:.1%}")
    print(f"  final curriculum level          L{history[-1].curriculum_level}")
    print()


if __name__ == "__main__":
    main()
