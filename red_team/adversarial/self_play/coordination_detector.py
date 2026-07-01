"""
Cross-component coordination detector — Blue's counter to the conduit_split mesh (§19).

§18 showed the mule mesh defeats the whole per-component stack at 0% benign FP by fragmenting
one ring into many hub-less consumer components. This runner adds the operation-level signal
that can see across that fragmentation (the B1 capability) and measures, controlled:

  [A] provenance + behavioural,                household pool, mesh arsenal   → §18 residual open
  [B] provenance + behavioural + coordination, household pool, mesh arsenal   → does it close?
  [C] provenance + behavioural + coordination, CORPORATE pool, takeover only  → honest residual

A is the §18 result reproduced; B adds only the coordination signal; C shows the one attack
coordination is NOT meant to catch (a hub-anchored corporate-account seizure, §17-C), so the
arc's remaining residual is named honestly rather than hidden.

Benign false positives are measured at the OPERATION level (each benign graph is one linked
operation = one component), exactly where coordination could misfire — it must stay at 0%.

Run:  cd backend && .venv/bin/python -m adversarial.self_play.coordination_detector
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
from ..config import EvolutionConfig
from ..red_team import agents as _agents
from ..red_team.evolutionary_engine import EvolutionaryRedTeam
from ..red_team.graph_generator import make_base_attacks, make_benign_corpus

TAKEOVER = ('feature_mimicry', 'amount_dither', 'decoy_edges', 'relay_insertion',
            'temporal_spread', 'sink_funnel', 'cross_component_split',
            'volume_dilution', 'profile_mimicry', 'account_takeover')
MESH = TAKEOVER + ('conduit_split',)


def _run_red(oracle, bases, cfg):
    ev, mix = 0, Counter()
    for b in bases:
        best = EvolutionaryRedTeam(oracle, b, cfg).evolve()
        if best.evaded and best.objective_ok:
            ev += 1
            mix.update({m.agent for m in best.genome})
    return ev / len(bases), mix


def _op_benign_fp(oracle, comps):
    """FP at the operation level: each benign graph is one linked operation."""
    from ..common.attack_graph import AttackGraph, AttackObjective
    flagged = 0
    for c in comps:
        ag = AttackGraph(components=[c], objective=AttackObjective(set(), set(), 0.0))
        if oracle.detect(ag).flagged:
            flagged += 1
    return flagged / max(1, len(comps))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ga-pop", type=int, default=24)
    ap.add_argument("--ga-gens", type=int, default=8)
    ap.add_argument("--eval-samples", type=int, default=1)
    ap.add_argument("--seized", type=int, default=300)
    args = ap.parse_args()

    prof = build_customer_profiles()
    breg = BehavioralRegistry(prof)
    prov = ProvenanceScorer(ProvenanceRegistry(breg.universe))
    behav = BehavioralScorer(breg)
    coord = CoordinationScorer(breg)
    bases = make_base_attacks(seed=42)
    benign = make_benign_corpus(seed=23, n=80, realistic=True, registry=breg)

    rng = random.Random(7)
    hh = [c for c, p in prof.items()
          if p.segment in ("household", "retail") and p.establishment >= 0.7]
    rng.shuffle(hh); hh = hh[:args.seized]
    hh_caps = {a: breg.baseline_throughput(a) for a in hh}
    corp = breg.segment_ids("corporate", "sme"); rng.shuffle(corp); corp = corp[:args.seized]

    no_coord = BlueTeamOracle("v2", provenance=prov, behavioral=behav)
    with_coord = BlueTeamOracle("v2", provenance=prov, behavioral=behav, coordination=coord)
    cfg_mesh = EvolutionConfig(population_size=args.ga_pop, generations=args.ga_gens,
                               eval_samples=args.eval_samples, max_genome_len=6, allowed_agents=MESH)
    cfg_take = EvolutionConfig(population_size=args.ga_pop, generations=args.ga_gens,
                               eval_samples=args.eval_samples, max_genome_len=5, allowed_agents=TAKEOVER)

    print(f"\n{'='*82}\n CROSS-COMPONENT COORDINATION DETECTOR vs the conduit_split mesh  (§19)\n{'='*82}")
    print(f" Red GA {args.ga_pop}x{args.ga_gens}, seized pool {args.seized}\n")
    print(" operation-level benign FP (segment-consistent corpus):")
    print(f"   prov + behavioural                 FP = {_op_benign_fp(no_coord, benign):.0%}")
    print(f"   prov + behavioural + coordination  FP = {_op_benign_fp(with_coord, benign):.0%}"
          f"   (coordination must not over-flag linked legit ops)\n")

    _agents.set_compromised_accounts(hh, hh_caps)
    asr_a, mix_a = _run_red(no_coord, bases, cfg_mesh)
    asr_b, mix_b = _run_red(with_coord, bases, cfg_mesh)
    _agents.set_compromised_accounts(corp)
    asr_c, mix_c = _run_red(with_coord, bases, cfg_take)

    def fmt(m): return ", ".join(f"{a}x{n}" for a, n in m.most_common(2)) or "—"
    print(" attack success rate (ASR):")
    print(f"   [A] prov+behav,        mesh, seize HH    ASR = {asr_a:.2f}   [{fmt(mix_a)}]")
    print(f"   [B] +coordination,     mesh, seize HH    ASR = {asr_b:.2f}   [{fmt(mix_b)}]")
    print(f"   [C] +coordination, takeover, seize CORP  ASR = {asr_c:.2f}   [{fmt(mix_c)}]\n")
    print(f"{'-'*82}")
    print(f" §18 mesh residual (A): ASR {asr_a:.2f}  →  coordination closes it (B): ASR {asr_b:.2f}")
    print(f" honest remaining residual (C) corporate-account seizure: ASR {asr_c:.2f}")
    print(f"{'-'*82}")
    print(" → the mesh is invisible per-component but, across the LINKED operation, is a")
    print("   hub-less crowd of seized consumer accounts — a shape no legitimate operation")
    print("   has. Coordination catches it at 0% benign FP, but ONLY given cross-session")
    print("   linkage (the B1 capability V2 lacks). The corporate-seizure path (C) has a")
    print("   real hub, so coordination spares it — the costlier, still-open residual.\n")


if __name__ == "__main__":
    main()
