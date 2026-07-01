"""
Detector-hardening campaign — fit the learned factor calibration (Phase B/C
successor) and test whether it actually adds fraud–benign margin.

Pipeline:
  1. build a DIVERSE evasion corpus with MAP-Elites against baseline V2;
  2. extract per-component 16-factor vectors (evasion fragments = positive,
     benign traffic = negative) and fit a logistic calibration on a TRAIN split;
  3. static check: re-flag rate on a held-out evasion split + benign false
     positives on a held-out benign set;
  4. dynamic check (the real test of generalization): let the Red Team RE-EVOLVE
     against the calibrated detector and compare ASR + distortion to baseline.

Run:  cd backend && .venv/bin/python -m adversarial.self_play.detector_harden
      python -m adversarial.self_play.detector_harden --qd-evals 1500 --ga-gens 12
"""
from __future__ import annotations

import argparse
import random

from ..common.oracle import BlueTeamOracle
from ..config import EvolutionConfig, QDConfig
from ..red_team.base import apply_genome
from ..red_team.evolutionary_engine import EvolutionaryRedTeam
from ..red_team.evolutionary_engine.engine import stable_seed
from ..red_team.graph_generator import make_base_attacks, make_benign_corpus
from ..red_team.quality_diversity import MapElitesRedTeam
from .detector_hardener import FactorCalibrationHardener, cluster_features


def _feats_for_components(engine, components) -> list[list[float]]:
    out = []
    for c in components:
        if len(c.get("edges", [])) >= 1:          # skip inert singleton fragments
            out.append(cluster_features(engine.analyze_component(c)))
    return out


def build_evasion_corpus(oracle, engine, bases, qd_evals, eval_samples):
    feats: list[list[float]] = []
    for base in bases:
        me = MapElitesRedTeam(oracle, base,
                              QDConfig(evaluations=qd_evals, eval_samples=eval_samples))
        me.illuminate()
        for elite in me.evading_elites():
            ag = apply_genome(base, elite.genome, random.Random(stable_seed(elite.repr)))
            feats.extend(_feats_for_components(engine, ag.components))
    return feats


def _split(rows, frac, rng):
    rows = list(rows)
    rng.shuffle(rows)
    k = int(len(rows) * frac)
    return rows[:k], rows[k:]


def _asr(oracle, bases, cfg) -> tuple[float, float]:
    """(ASR, mean distortion of evasions) for a fresh GA search vs this oracle."""
    evaded, dists = 0, []
    for base in bases:
        best = EvolutionaryRedTeam(oracle, base, cfg).evolve()
        if best.evaded and best.objective_ok:
            evaded += 1
            dists.append(best.distortion)
    return evaded / len(bases), (sum(dists) / len(dists) if dists else 0.0)


def main() -> None:
    ap = argparse.ArgumentParser(description="TGiE detector-level hardening")
    ap.add_argument("--qd-evals", type=int, default=1200)
    ap.add_argument("--eval-samples", type=int, default=2)
    ap.add_argument("--ga-pop", type=int, default=30)
    ap.add_argument("--ga-gens", type=int, default=10)
    args = ap.parse_args()

    from blue_team_v2.engine import BlueTeamV2Engine
    engine = BlueTeamV2Engine()
    baseline = BlueTeamOracle(target="v2")
    bases = make_base_attacks(seed=42)
    rng = random.Random(0)

    print(f"\n{'='*78}\n TGiE DETECTOR-LEVEL HARDENING — learned 16-factor calibration\n{'='*78}")
    print(" building diverse evasion corpus (MAP-Elites) …")
    evasion_feats = build_evasion_corpus(baseline, engine, bases,
                                         args.qd_evals, args.eval_samples)
    benign_train_comps = make_benign_corpus(seed=7, n=80)
    benign_holdout_comps = make_benign_corpus(seed=23, n=80)
    benign_feats = _feats_for_components(engine, benign_train_comps)
    benign_holdout = _feats_for_components(engine, benign_holdout_comps)
    print(f"   evasion fragments={len(evasion_feats)}  benign(train)={len(benign_feats)}"
          f"  benign(holdout)={len(benign_holdout)}")

    # train / test split on the evasion fragments
    ev_train, ev_test = _split(evasion_feats, 0.7, rng)
    calib = FactorCalibrationHardener().fit(ev_train, benign_feats)

    # ── static check: the calibrator's standalone discrimination ──
    review = baseline.blue_config.review_threshold
    reflag = sum(1 for f in ev_test if calib._prob(f) >= review) / max(1, len(ev_test))
    calib_fp = sum(1 for f in benign_holdout if calib._prob(f) >= review) / max(1, len(benign_holdout))
    print(f"\n{'-'*78}\n STATIC — calibrator only (held-out fragments)\n{'-'*78}")
    print(f"  evasion-fragment re-flag rate   {reflag:.1%}")
    print(f"  calibrator benign FP            {calib_fp:.1%}")
    from .detector_hardener import FACTOR_KEYS
    top = sorted(range(len(calib.weights)), key=lambda j: -abs(calib.weights[j]))[:5]
    print(f"  top calibrated factors          "
          f"{', '.join(f'{FACTOR_KEYS[j]}({calib.weights[j]:+.2f})' for j in top)}")

    # ── operational benign FP: through the actual oracles (native risk OR calibrator) ──
    hardened = BlueTeamOracle(target="v2", calibrator=calib)
    def _benign_fp(oracle, comps):
        flagged = sum(1 for c in comps
                      if oracle.detect_component(c).verdict in ("SUSPICIOUS", "FRAUD"))
        return flagged / max(1, len(comps))
    native_fp = _benign_fp(baseline, benign_holdout_comps)
    hardened_fp = _benign_fp(hardened, benign_holdout_comps)
    print(f"\n{'-'*78}\n OPERATIONAL benign FP (held-out, through the oracle)\n{'-'*78}")
    print(f"  native V2 benign FP             {native_fp:.1%}  (pre-existing, Phase B)")
    print(f"  hardened benign FP              {hardened_fp:.1%}  "
          f"(+{hardened_fp-native_fp:.1%} from the calibration)")

    # ── dynamic check: Red re-evolves against the calibrated detector ──
    cfg = EvolutionConfig(population_size=args.ga_pop, generations=args.ga_gens,
                          eval_samples=args.eval_samples)
    print(f"\n{'-'*78}\n DYNAMIC (Red re-evolves vs the hardened detector, ga={args.ga_pop}x{args.ga_gens})\n{'-'*78}")
    asr0, d0 = _asr(baseline, bases, cfg)
    asr1, d1 = _asr(hardened, bases, cfg)
    print(f"  ASR  baseline → hardened        {asr0:.3f} → {asr1:.3f}   (gain {asr0-asr1:+.3f})")
    dist_str = f"{d0:.2f} → {d1:.2f}" if asr1 > 0 else f"{d0:.2f} → n/a (no evasions found)"
    print(f"  mean evasion distortion         {dist_str}")
    print()


if __name__ == "__main__":
    main()
