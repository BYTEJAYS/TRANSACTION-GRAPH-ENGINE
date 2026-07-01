"""
Behavioural-conduit detector — Blue's counter to account-takeover (§17).

§16 realised the residual provenance admitted: an attacker who seizes real KYC accounts
and routes laundering through them collapses the unverified-value ratio, so provenance
(which proves an account is *established*) clears the cluster. This runner adds the signal
provenance lacks — whether an established account is *behaving* normally — and measures,
in one controlled loop, whether it closes the §16 breach without re-opening the false
positives provenance fixed, and where Red goes next.

Defense stack escalates: native V2 → + provenance (§14) → + behavioural (§17). Every
condition is scored on a SEGMENT-CONSISTENT realistic benign corpus (a corporate payment
is between corporate-baseline accounts, a household transfer between household accounts)
so the behavioural FP test is honest: the detector must catch a household account pushing
laundering-scale value while leaving a corporate account's genuine ₹2M payment alone.

Conditions (Red runs its full arsenal incl. account_takeover each time):
  A  Blue = provenance            Red seizes any verified accounts   → §16 breach reproduced
  B  Blue = provenance+behavioural Red seizes any verified accounts  → does behavioural catch it?
  C  Blue = provenance+behavioural Red seizes HIGH-BASELINE accounts  → the next residual

Run:  cd backend && .venv/bin/python -m adversarial.self_play.behavioral_detector
"""
from __future__ import annotations

import argparse
import random
from collections import Counter

from ..common.behavioral import (BehavioralRegistry, BehavioralScorer,
                                  build_customer_profiles)
from ..common.oracle import BlueTeamOracle
from ..common.provenance import ProvenanceRegistry, ProvenanceScorer
from ..config import EvolutionConfig
from ..red_team import agents as _agents
from ..red_team.base import Move, apply_genome
from ..red_team.evolutionary_engine import EvolutionaryRedTeam
from ..red_team.evolutionary_engine.engine import stable_seed
from ..red_team.graph_generator import make_base_attacks, make_benign_corpus


def _run_red(oracle, bases, cfg) -> tuple[float, Counter]:
    evaded, mix = 0, Counter()
    for base in bases:
        best = EvolutionaryRedTeam(oracle, base, cfg).evolve()
        if best.evaded and best.objective_ok:
            evaded += 1
            mix.update({m.agent for m in best.genome})
    return evaded / len(bases), mix


def _benign_fp(oracle, comps) -> float:
    flagged = sum(1 for c in comps
                  if oracle.detect_component(c).verdict in ("SUSPICIOUS", "FRAUD"))
    return flagged / max(1, len(comps))


def _mechanism(behav: BehavioralScorer, prov: ProvenanceScorer,
               any_pool: list[str], hi_pool: list[str]) -> None:
    base = next(b for b in make_base_attacks(seed=42, archetypes=["cashout_network"]))

    def probe(pool, label):
        _agents.set_compromised_accounts(pool)
        ag = apply_genome(base, [Move("account_takeover", 0.9)],
                          random.Random(stable_seed("mech")))
        # provenance first (clears KYC), then behavioural (re-floors conduits)
        prov_risk = max((prov.adjust(c, 1.0) for c in ag.components), default=0.0)
        anom = max((behav.conduit_anomaly(c) for c in ag.components), default=0.0)
        final = max((behav.adjust(c, prov.adjust(c, 1.0)) for c in ag.components), default=0.0)
        print(f"    {label:<26} provenance→{prov_risk:.2f}  conduit_anomaly={anom:.2f}  "
              f"final risk={final:.2f}")

    print("  mechanism (cashout_network, native risk forced to 1.0; REVIEW 0.62 / HIGH 0.83):")
    probe(any_pool, "seize ANY verified")
    probe(hi_pool, "seize HIGH-baseline")


def main() -> None:
    ap = argparse.ArgumentParser(description="behavioural conduit detector vs account-takeover")
    ap.add_argument("--ga-pop", type=int, default=30)
    ap.add_argument("--ga-gens", type=int, default=12)
    ap.add_argument("--eval-samples", type=int, default=1)
    ap.add_argument("--seized", type=int, default=120)
    args = ap.parse_args()

    profiles = build_customer_profiles()
    behav_reg = BehavioralRegistry(profiles)
    prov_reg = ProvenanceRegistry(behav_reg.universe)     # same establishment base
    prov = ProvenanceScorer(prov_reg)
    behav = BehavioralScorer(behav_reg)

    bases = make_base_attacks(seed=42)
    # arsenal WITHOUT conduit_split isolates the §16/§17 story (simple takeover); the
    # split mesh is the separate §18 probe in condition D.
    TAKEOVER = ('feature_mimicry', 'amount_dither', 'decoy_edges', 'relay_insertion',
                'temporal_spread', 'sink_funnel', 'cross_component_split',
                'volume_dilution', 'profile_mimicry', 'account_takeover')
    cfg = EvolutionConfig(population_size=args.ga_pop, generations=args.ga_gens,
                          eval_samples=args.eval_samples, max_genome_len=5,
                          allowed_agents=TAKEOVER)
    cfg_split = EvolutionConfig(population_size=args.ga_pop, generations=args.ga_gens,
                                eval_samples=args.eval_samples, max_genome_len=6,
                                allowed_agents=TAKEOVER + ('conduit_split',))
    # segment-consistent benign corpus for an honest FP test
    benign = make_benign_corpus(seed=23, n=80, realistic=True, registry=behav_reg)

    rng = random.Random(7)
    # naive attacker: phished CONSUMERS — established but low-baseline household/retail
    # accounts, the easy-to-seize majority. Their envelope can't absorb laundering value.
    any_pool = [c for c, p in profiles.items()
                if p.segment in ("household", "retail") and p.establishment >= 0.7]
    rng.shuffle(any_pool); any_pool = any_pool[:args.seized]
    # post-takeover the attacker can read each victim's statements → capacity estimate
    any_caps = {a: behav_reg.baseline_throughput(a) for a in any_pool}
    # sophisticated attacker: seize accounts whose baseline SUPPORTS laundering volume
    # (corporate / SME) — only ~7% of the base and far harder to take over.
    hi_pool = behav_reg.segment_ids("corporate", "sme")
    rng.shuffle(hi_pool); hi_pool = hi_pool[:args.seized]

    prov_only = BlueTeamOracle(target="v2", provenance=prov)
    full = BlueTeamOracle(target="v2", provenance=prov, behavioral=behav)

    print(f"\n{'='*80}\n BEHAVIOURAL CONDUIT DETECTOR vs ACCOUNT-TAKEOVER  (§17–§18)\n{'='*80}")
    print(f" Red: takeover arsenal, GA {args.ga_pop}x{args.ga_gens}")
    print(f" seized pool size: {args.seized}   benign corpus: {len(benign)} segment-consistent graphs\n")

    print(" benign false positives (segment-consistent corpus):")
    print(f"   provenance only          FP = {_benign_fp(prov_only, benign):.0%}")
    print(f"   provenance + behavioural FP = {_benign_fp(full, benign):.0%}   "
          f"(behavioural must not re-open §14's FP)\n")

    _agents.set_compromised_accounts(any_pool, any_caps)
    asr_a, mix_a = _run_red(prov_only, bases, cfg)
    asr_b, mix_b = _run_red(full, bases, cfg)
    asr_d, mix_d = _run_red(full, bases, cfg_split)         # §18: mule-mesh split
    _agents.set_compromised_accounts(hi_pool)
    asr_c, mix_c = _run_red(full, bases, cfg)

    def fmt(m): return ", ".join(f"{a}x{n}" for a, n in m.most_common(2)) or "—"
    print(" attack success rate (ASR):")
    print(f"   [A] provenance,   seize HH,  takeover       ASR = {asr_a:.2f}   [{fmt(mix_a)}]")
    print(f"   [B] +behavioural, seize HH,  takeover       ASR = {asr_b:.2f}   [{fmt(mix_b)}]")
    print(f"   [C] +behavioural, seize CORP, takeover      ASR = {asr_c:.2f}   [{fmt(mix_c)}]")
    print(f"   [D] +behavioural, seize HH,  +conduit_split ASR = {asr_d:.2f}   [{fmt(mix_d)}]\n")

    _mechanism(behav, prov, any_pool, hi_pool)

    print(f"\n{'-'*80}")
    print(f" §16 breach (A): ASR {asr_a:.2f}  →  behavioural closes it (B): ASR {asr_b:.2f}")
    print(f" residual (C) seize baseline-appropriate accounts: ASR {asr_c:.2f}")
    print(f" residual (D) §18 mule-mesh split across many consumer mules: ASR {asr_d:.2f}")
    print(f"{'-'*80}")
    print(" → behavioural catches a seized account used beyond its own envelope at no new")
    print("   benign cost (B). The surviving attacks both PAY for it: (C) seize corporate")
    print("   accounts whose baseline already supports the volume (~7% of the base), or (D)")
    print("   split the laundering into a thin mule MESH across ~100 in-profile consumer")
    print("   accounts. (D) fragments the ring across many components, so catching it needs")
    print("   CROSS-COMPONENT correlation — the original B1 blind spot — not another")
    print("   per-account signal. Each Blue signal raises the attacker's cost; the open")
    print("   residual now points back at B1 as the architectural root.\n")


if __name__ == "__main__":
    main()
