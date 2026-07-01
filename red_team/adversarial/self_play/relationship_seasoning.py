"""
Relationship-seasoning probe + maturity counter — the §20 residual, and where it ends (§21).

§20 closed the corporate-seizure path with a counterparty-history signal: value between verified
accounts with no shared history is flagged. Its named residual: an attacker patient enough to
SEASON genuine-looking history between the accounts it controls — prior small transfers among its
mules — manufactures the shared history the signal trusts.

This realises that probe and its counter, and shows the round ends in the attacker's economics:

  Red  — `season()` injects learned relationships among the seized cohort (as if the bank had
         observed prior traffic), defeating the §20 BINARY relationship detector (any shared
         history counts).
  Blue — a MATURITY-weighted relationship detector trusts a relationship only up to the value its
         observed history can vouch for (depth × age × cumulative value), so cheap/recent seasoning
         covers almost nothing of a large laundering flow.
  Red  — defeating maturity requires DEEP seasoning (many aged, high-value prior transfers), i.e.
         pre-moving legitimately a value comparable to the laundering itself — and the seasoning
         footprint required dwarfs the laundered amount. The cure costs far more than the disease.

Conditions (seize a corporate cohort, takeover arsenal; benign = circle-coherent):
  [A] BINARY detector,   no seasoning      → §20 result (closed)
  [B] BINARY detector,   cheap seasoning   → probe defeats §20
  [C] MATURITY detector, cheap seasoning   → counter closes it again
  [D] MATURITY detector, deep seasoning    → defeats maturity, at a quantified, absurd cost

Run:  cd backend && .venv/bin/python -m adversarial.self_play.relationship_seasoning
"""
from __future__ import annotations

import argparse
import random
from collections import Counter

from ..common.behavioral import (BehavioralRegistry, BehavioralScorer,
                                  build_customer_profiles)
from ..common.coordination import CoordinationScorer
from ..common.oracle import BlueTeamOracle
from ..common.provenance import ProvenanceRegistry, ProvenanceScorer
from ..common.relationships import (RelationshipRegistry, RelationshipScorer,
                                    build_relationship_circles, make_circle_benign_corpus, season)
from ..config import EvolutionConfig
from ..red_team import agents as _agents
from ..red_team.evolutionary_engine import EvolutionaryRedTeam
from ..red_team.graph_generator import make_base_attacks

TAKEOVER = ('feature_mimicry', 'amount_dither', 'decoy_edges', 'relay_insertion',
            'temporal_spread', 'sink_funnel', 'cross_component_split',
            'volume_dilution', 'profile_mimicry', 'account_takeover')


def _run_red(oracle, bases, cfg):
    ev, mix = 0, Counter()
    for b in bases:
        best = EvolutionaryRedTeam(oracle, b, cfg).evolve()
        if best.evaded and best.objective_ok:
            ev += 1
            mix.update({m.agent for m in best.genome})
    return ev / len(bases), mix


def _op_fp(oracle, comps):
    from ..common.attack_graph import AttackGraph, AttackObjective
    return sum(1 for c in comps
               if oracle.detect(AttackGraph([c], AttackObjective(set(), set(), 0.0))).flagged) / max(1, len(comps))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ga-pop", type=int, default=24)
    ap.add_argument("--ga-gens", type=int, default=8)
    ap.add_argument("--eval-samples", type=int, default=1)
    ap.add_argument("--cohort", type=int, default=40)
    args = ap.parse_args()

    prof = build_customer_profiles()
    breg = BehavioralRegistry(prof)
    circles = build_relationship_circles(prof)
    prov = ProvenanceScorer(ProvenanceRegistry(breg.universe))
    behav = BehavioralScorer(breg)
    coord = CoordinationScorer(breg)
    bases = make_base_attacks(seed=42)
    laundering = sum(b.objective.target_value for b in bases) / len(bases)

    rng = random.Random(7)
    corp = breg.segment_ids("corporate", "sme"); rng.shuffle(corp); corp = corp[:args.cohort]
    n_pairs = args.cohort * (args.cohort - 1) // 2
    cfg = EvolutionConfig(population_size=args.ga_pop, generations=args.ga_gens,
                          eval_samples=args.eval_samples, max_genome_len=5, allowed_agents=TAKEOVER)
    benign = make_circle_benign_corpus(breg, RelationshipRegistry(circles, prof), n=80, seed=23)

    def reg(maturity, season_spec):
        r = RelationshipRegistry(dict(circles), prof, {})
        if season_spec:
            season(r, corp, **season_spec)
        return RelationshipScorer(r, maturity=maturity)

    def oracle(rel):
        return BlueTeamOracle("v2", provenance=prov, behavioral=behav, coordination=coord, relationship=rel)

    cheap = dict(count=5, value_per_pair=10_000, age_days=14)
    deep = dict(count=50, value_per_pair=200_000, age_days=400)
    _agents.set_compromised_accounts(corp)

    print(f"\n{'='*84}\n RELATIONSHIP-SEASONING PROBE + MATURITY COUNTER  (§21)\n{'='*84}")
    print(f" cohort {args.cohort} corporate accounts → {n_pairs} seasonable pairs; "
          f"avg laundering ≈ ₹{laundering:,.0f}\n")

    rel_bin_clean = reg(False, None)
    print(" benign FP (circle-coherent corpus, operation level):")
    print(f"   binary relationship    FP = {_op_fp(oracle(rel_bin_clean), benign):.0%}")
    print(f"   maturity relationship  FP = {_op_fp(oracle(reg(True, None)), benign):.0%}\n")

    asr_a, _ = _run_red(oracle(reg(False, None)), bases, cfg)
    asr_b, _ = _run_red(oracle(reg(False, cheap)), bases, cfg)
    asr_c, _ = _run_red(oracle(reg(True, cheap)), bases, cfg)
    asr_d, _ = _run_red(oracle(reg(True, deep)), bases, cfg)

    print(" attack success rate (ASR):")
    print(f"   [A] BINARY detector,   no seasoning     ASR = {asr_a:.2f}   (§20 result)")
    print(f"   [B] BINARY detector,   CHEAP seasoning  ASR = {asr_b:.2f}   (probe defeats §20)")
    print(f"   [C] MATURITY detector, CHEAP seasoning  ASR = {asr_c:.2f}   (counter closes it)")
    print(f"   [D] MATURITY detector, DEEP seasoning   ASR = {asr_d:.2f}   (defeats maturity — at what cost?)\n")

    cheap_cost = n_pairs * cheap["count"] * cheap["value_per_pair"]
    deep_cost = n_pairs * deep["count"] * deep["value_per_pair"]
    print(f"{'-'*84}")
    print(f" SEASONING COST (value the attacker must pre-move as legit traffic to launder ₹{laundering:,.0f}):")
    print(f"   cheap seasoning footprint ≈ ₹{cheap_cost:,.0f}  ({cheap_cost/laundering:,.0f}× the laundered amount) — and still caught by maturity")
    print(f"   deep  seasoning footprint ≈ ₹{deep_cost:,.0f}  ({deep_cost/laundering:,.0f}× the laundered amount) over ~1 year")
    print(f"{'-'*84}")
    print(" → seasoning defeats a BINARY history check cheaply, but a MATURITY-weighted one forces")
    print("   the attacker to manufacture deep, aged, high-value history — i.e. to legitimately move")
    print("   far more money than it launders, over a year, before it starts. The arms race ends not")
    print("   in a perfect detector but in ECONOMICS: the defender has made laundering cost more than")
    print("   it yields. That is the realistic win condition — and it required the temporal/history")
    print("   dimension V2's snapshot never had.\n")


if __name__ == "__main__":
    main()
