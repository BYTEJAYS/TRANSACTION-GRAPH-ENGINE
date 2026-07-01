"""
Account-takeover probe — the honest residual provenance (§14) left armed.

Provenance blocks the entire standard arsenal at 0% benign FP by flooring the risk
of value moving between fresh / unverified accounts; its docstring names the one
scheme it cannot stop — laundering routed *through real customer accounts the
attacker has seized*. This runner realises that probe as a controlled experiment and
measures whether it actually breaks the provenance defense.

The experiment isolates exactly the takeover capability: the Blue defense, the Red
search, the base graphs and the full agent set are held identical across two runs —
only the attacker's pool of compromised verified accounts changes:

    run A  pool = ∅       → account_takeover is a no-op → "provenance vs the standard
                            arsenal" (cross_component_split / volume_dilution /
                            profile_mimicry / …) — the §14 result, reproduced.
    run B  pool = seized  → account_takeover may route the high-value path through
                            verified victim identities.

A rise A→B is caused by takeover and nothing else. We also report the provenance
unverified-value ratio before/after a takeover to show the mechanism directly.

Run:  cd backend && .venv/bin/python -m adversarial.self_play.account_takeover
"""
from __future__ import annotations

import argparse
import random
from collections import Counter

from ..common.oracle import BlueTeamOracle
from ..common.provenance import (ProvenanceRegistry, ProvenanceScorer,
                                  build_customer_universe)
from ..config import EvolutionConfig
from ..red_team import agents as _agents
from ..red_team.base import apply_genome
from ..red_team.evolutionary_engine import EvolutionaryRedTeam
from ..red_team.evolutionary_engine.engine import stable_seed
from ..red_team.graph_generator import make_base_attacks


def seize_established(registry: ProvenanceRegistry, k: int, min_est: float = 0.7,
                      seed: int = 99) -> list[str]:
    """The attacker targets WELL-ESTABLISHED customers (those whose verified history
    actually vouches for value). Returns k such account ids the attacker controls."""
    candidates = [cid for cid, est in registry.universe.items() if est >= min_est]
    rng = random.Random(seed)
    rng.shuffle(candidates)
    return candidates[:k]


def _run_red(oracle: BlueTeamOracle, bases, cfg) -> tuple[float, Counter]:
    evaded, mix = 0, Counter()
    for base in bases:
        best = EvolutionaryRedTeam(oracle, base, cfg).evolve()
        if best.evaded and best.objective_ok:
            evaded += 1
            mix.update({m.agent for m in best.genome})
    return evaded / len(bases), mix


def _mechanism(registry: ProvenanceRegistry, scorer: ProvenanceScorer,
               pool: list[str]) -> None:
    """Show the unverified-value ratio collapse on one concrete sink component."""
    from ..red_team.base import Move
    _agents.set_compromised_accounts(pool)
    base = next(b for b in make_base_attacks(seed=42, archetypes=["cashout_network"]))
    rng = random.Random(stable_seed("mech"))
    before = apply_genome(base, [], rng)
    after = apply_genome(base, [Move("account_takeover", 0.9)], random.Random(stable_seed("mech")))

    def worst(ag):
        u = max((scorer.unverified_value_ratio(c) for c in ag.components), default=1.0)
        risk = max((scorer.adjust(c, 1.0) for c in ag.components), default=0.0)
        return u, risk

    bu, brisk = worst(before)
    au, arisk = worst(after)
    print(f"  mechanism (cashout_network, native risk forced to 1.0):")
    print(f"    unverified-value ratio  {bu:.2f} → {au:.2f}")
    print(f"    provenance-adjusted risk {brisk:.2f} → {arisk:.2f}  "
          f"(threshold REVIEW 0.62 / HIGH 0.83)")


def main() -> None:
    ap = argparse.ArgumentParser(description="account-takeover vs provenance")
    ap.add_argument("--ga-pop", type=int, default=30)
    ap.add_argument("--ga-gens", type=int, default=12)
    ap.add_argument("--eval-samples", type=int, default=1)
    ap.add_argument("--seized", type=int, default=120,
                    help="number of verified customer accounts the attacker controls")
    args = ap.parse_args()

    registry = ProvenanceRegistry(build_customer_universe())
    scorer = ProvenanceScorer(registry)
    oracle = BlueTeamOracle(target="v2", provenance=scorer)   # provenance-hardened Blue
    bases = make_base_attacks(seed=42)
    # arsenal pinned to exclude conduit_split: this probe isolates account_takeover (§16);
    # the mule-mesh split is the separate §18 probe.
    cfg = EvolutionConfig(
        population_size=args.ga_pop, generations=args.ga_gens,
        eval_samples=args.eval_samples, max_genome_len=5,
        allowed_agents=('feature_mimicry', 'amount_dither', 'decoy_edges', 'relay_insertion',
                        'temporal_spread', 'sink_funnel', 'cross_component_split',
                        'volume_dilution', 'profile_mimicry', 'account_takeover'))
    pool = seize_established(registry, args.seized)

    print(f"\n{'='*78}\n ACCOUNT-TAKEOVER PROBE vs the PROVENANCE-hardened Blue Team\n{'='*78}")
    print(f" Blue: native V2 + provenance   Red: full arsenal, GA {args.ga_pop}x{args.ga_gens}")
    print(f" seized verified accounts available to Red: {len(pool)}\n")

    # sweep over seizure budget: how many verified accounts must the attacker own?
    # budget 0 ≡ account_takeover is a no-op (the §14 "provenance vs standard arsenal"
    # control). The curve shows takeover's COST — bigger breaches need more seized
    # identities (more exposure), so an ASR=1.0 at a huge budget is not a free win.
    budgets = sorted({0, 8, 24, len(pool)})
    print(f" seizure-budget sweep (ASR vs provenance, full Red arsenal):")
    asr_at = {}
    for b in budgets:
        _agents.set_compromised_accounts(pool[:b])
        asr, mix = _run_red(oracle, bases, cfg)
        asr_at[b] = asr
        tag = "  (no takeover — control)" if b == 0 else ""
        print(f"   seized={b:>4}   ASR = {asr:.2f}   "
              f"[{', '.join(f'{a}x{n}' for a, n in mix.most_common(2)) or '—'}]{tag}")

    print(f"\n{'-'*78}")
    print(f" takeover effect: ASR {asr_at[0]:.2f} (no capacity) → {asr_at[len(pool)]:.2f} "
          f"({len(pool)} seized)")
    _mechanism(registry, scorer, pool)
    print(f"{'-'*78}")
    if asr_at[len(pool)] > asr_at[0]:
        print(" → account-takeover breaches provenance: routing the high-value path through")
        print("   seized verified identities collapses the unverified-value ratio. This is")
        print("   the documented residual, now realised. Blue's next signal must detect")
        print("   verified accounts behaving anomalously (pass-through velocity / dormancy")
        print("   break vs their own history), not just whether they are established.\n")
    else:
        print(" → provenance held even against takeover at this budget.\n")


if __name__ == "__main__":
    main()
