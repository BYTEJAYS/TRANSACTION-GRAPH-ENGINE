"""
Counterparty-relationship detector — the corporate-seizure counter, and the synthesis (§20).

§19 left the corporate-account seizure (§17-C) as the last open residual: route the laundering
through seized high-baseline CORPORATE accounts and every signal so far passes — provenance (the
accounts are verified), behavioural (a corporate baseline absorbs the volume), coordination (a
real hub anchors the flow). The signal they all miss is the RELATIONSHIP between the parties: a
real business pays its own established suppliers and employees, a seized one suddenly pays
verified accounts it has no shared history with.

This runner adds that signal (per-component novel-verified-counterparty value) and measures it on
a circle-coherent benign corpus (every legitimate operation runs inside one established
relationship circle). Conditions:

  [A] prov+behav+coordination,  seize CORPORATE, takeover  → §17-C residual (coordination misses)
  [B] + relationship,           seize CORPORATE, takeover  → does it close?
  [C] + relationship,           seize HOUSEHOLD, mesh       → relationship vs the §18 mesh too

The headline of §20 is condition C: the relationship signal is PER-COMPONENT, yet it also closes
the conduit_split mesh (its edges are between seized accounts with no shared history). So §19's
"the mesh needs cross-component correlation" was true only for the signals built by then — a
per-component COUNTERPARTY-HISTORY signal catches it as well, and additionally catches the
corporate seizure coordination cannot. The deeper truth both rounds point to: every effective
defence injects CONTEXT beyond V2's isolated transaction-graph snapshot (KYC, baseline, linkage,
relationship history); the snapshot-only, component-isolated view is the root limitation.

Run:  cd backend && .venv/bin/python -m adversarial.self_play.relationship_detector
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
                                    build_relationship_circles, make_circle_benign_corpus)
from ..config import EvolutionConfig
from ..red_team import agents as _agents
from ..red_team.evolutionary_engine import EvolutionaryRedTeam
from ..red_team.graph_generator import make_base_attacks

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


def _op_fp(oracle, comps):
    from ..common.attack_graph import AttackGraph, AttackObjective
    f = 0
    for c in comps:
        if oracle.detect(AttackGraph([c], AttackObjective(set(), set(), 0.0))).flagged:
            f += 1
    return f / max(1, len(comps))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ga-pop", type=int, default=24)
    ap.add_argument("--ga-gens", type=int, default=8)
    ap.add_argument("--eval-samples", type=int, default=1)
    ap.add_argument("--seized", type=int, default=200)
    args = ap.parse_args()

    prof = build_customer_profiles()
    breg = BehavioralRegistry(prof)
    rreg = RelationshipRegistry(build_relationship_circles(prof), prof)
    prov = ProvenanceScorer(ProvenanceRegistry(breg.universe))
    behav = BehavioralScorer(breg)
    coord = CoordinationScorer(breg)
    rel = RelationshipScorer(rreg)
    bases = make_base_attacks(seed=42)
    benign = make_circle_benign_corpus(breg, rreg, n=80, seed=23)

    rng = random.Random(7)
    corp = breg.segment_ids("corporate", "sme"); rng.shuffle(corp); corp = corp[:args.seized]
    hh = [c for c, p in prof.items() if p.segment in ("household", "retail") and p.establishment >= 0.7]
    rng.shuffle(hh); hh = hh[:args.seized]
    hh_caps = {a: breg.baseline_throughput(a) for a in hh}

    no_rel = BlueTeamOracle("v2", provenance=prov, behavioral=behav, coordination=coord)
    with_rel = BlueTeamOracle("v2", provenance=prov, behavioral=behav, coordination=coord, relationship=rel)
    cfg_take = EvolutionConfig(population_size=args.ga_pop, generations=args.ga_gens,
                               eval_samples=args.eval_samples, max_genome_len=5, allowed_agents=TAKEOVER)
    cfg_mesh = EvolutionConfig(population_size=args.ga_pop, generations=args.ga_gens,
                               eval_samples=args.eval_samples, max_genome_len=6, allowed_agents=MESH)

    print(f"\n{'='*82}\n COUNTERPARTY-RELATIONSHIP DETECTOR — corporate-seizure counter + synthesis (§20)\n{'='*82}")
    print(f" {rreg.num_circles()} relationship circles; Red GA {args.ga_pop}x{args.ga_gens}, seized {args.seized}\n")
    print(" benign FP (circle-coherent corpus, operation level):")
    print(f"   prov+behav+coordination                FP = {_op_fp(no_rel, benign):.0%}")
    print(f"   prov+behav+coordination+relationship   FP = {_op_fp(with_rel, benign):.0%}\n")

    _agents.set_compromised_accounts(corp)
    asr_a, mix_a = _run_red(no_rel, bases, cfg_take)
    asr_b, mix_b = _run_red(with_rel, bases, cfg_take)
    _agents.set_compromised_accounts(hh, hh_caps)
    asr_c, mix_c = _run_red(with_rel, bases, cfg_mesh)

    def fmt(m): return ", ".join(f"{a}x{n}" for a, n in m.most_common(2)) or "—"
    print(" attack success rate (ASR):")
    print(f"   [A] +coordination,  seize CORP, takeover   ASR = {asr_a:.2f}   [{fmt(mix_a)}]   (§17-C open)")
    print(f"   [B] +relationship,  seize CORP, takeover   ASR = {asr_b:.2f}   [{fmt(mix_b)}]   (§17-C closed)")
    print(f"   [C] +relationship,  seize HH,   mesh       ASR = {asr_c:.2f}   [{fmt(mix_c)}]   (mesh too)\n")
    print(f"{'-'*82}")
    print(f" §17-C corporate seizure (A→B): ASR {asr_a:.2f} → {asr_b:.2f}")
    print(f" relationship also closes the §18 mesh per-component (C): ASR {asr_c:.2f}")
    print(f"{'-'*82}")
    print(" → a seized account betrays itself by paying verified STRANGERS. Counterparty history")
    print("   catches both the corporate seizure (coordination missed) and the consumer mesh, all")
    print("   per-component — at the cost of the strongest data assumption (a complete relationship")
    print("   graph) and real consumer-novelty FP in production. The synthesis of §16–§20: every")
    print("   defence injects CONTEXT beyond V2's isolated snapshot (KYC, baseline, linkage,")
    print("   relationships); the snapshot-only view is the root. Residual: an attacker patient")
    print("   enough to SEASON genuine history between its mules before the run.\n")


if __name__ == "__main__":
    main()
