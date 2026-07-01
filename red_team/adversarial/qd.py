"""
Quality-Diversity campaign — illuminate the attack space with MAP-Elites and
contrast its diversity against the scalar GA's single collapsed strategy.

For each confirmed-FRAUD archetype it runs MAP-Elites, reports coverage / evading
cells / distinct technique families, renders the illumination grid, and stores the
diverse evading elites to attack memory (the varied corpus a detector-level
hardener needs — see audit §9). With --compare it also runs the scalar GA on the
same budget to show the collapse it avoids.

Run:  cd backend && .venv/bin/python -m adversarial.qd --evaluations 2000
      python -m adversarial.qd --evaluations 3000 --detail mule_network --compare
"""
from __future__ import annotations

import argparse

from .attack_memory import AttackMemory
from .common.oracle import BlueTeamOracle
from .config import EvolutionConfig, QDConfig
from .red_team.evolutionary_engine import EvolutionaryRedTeam
from .red_team.graph_generator import make_base_attacks
from .red_team.quality_diversity import MapElitesRedTeam
from .red_team.quality_diversity.map_elites import _agent_family


def main() -> None:
    ap = argparse.ArgumentParser(description="TGiE MAP-Elites attack illumination")
    ap.add_argument("--evaluations", type=int, default=2000)
    ap.add_argument("--eval-samples", type=int, default=3)
    ap.add_argument("--detail", type=str, default="mule_network",
                    help="archetype whose illumination grid is rendered")
    ap.add_argument("--compare", action="store_true",
                    help="also run the scalar GA on the same budget to show collapse")
    args = ap.parse_args()

    oracle = BlueTeamOracle(target="v2")
    bases = make_base_attacks(seed=42)
    memory = AttackMemory()

    print(f"\n{'='*78}\n TGiE QUALITY-DIVERSITY — MAP-Elites attack illumination (V2)\n{'='*78}")
    print(f" archetypes={len(bases)}  evaluations/archetype={args.evaluations}  "
          f"eval_samples={args.eval_samples}\n")

    all_families: set[str] = set()
    ga_families: set[str] = set()
    total_evading_cells = 0
    detail_engine = None

    for base in bases:
        qd = QDConfig(evaluations=args.evaluations, eval_samples=args.eval_samples)
        me = MapElitesRedTeam(oracle, base, qd)
        me.illuminate()
        s = me.stats()
        total_evading_cells += s.cells_evading
        fams = {_agent_family(e) for e in me.evading_elites()}
        all_families |= fams
        if base.archetype == args.detail:
            detail_engine = me

        # store the cheapest evasion per family (the diverse hardening corpus)
        seen: set[str] = set()
        for e in me.evading_elites():
            fam = _agent_family(e)
            if fam in seen:
                continue
            seen.add(fam)
            memory.remember(
                attack_id=f"qd_{base.archetype}_{fam[:24]}",
                archetype=base.archetype, target_engine=oracle.target, genome=e.genome,
                baseline_verdict="FRAUD", final_verdict=e.worst_verdict,
                detection_score=e.detection_score, cluster_risk=e.max_cluster_risk,
                distortion=e.distortion, num_components=e.num_components,
                residual_detectors=e.evidence, objective_ok=True)

        line = (f"  {base.archetype:<16} coverage={s.coverage:<5} "
                f"filled={s.cells_filled:2d}/{s.cells_total} evading_cells={s.cells_evading:2d} "
                f"families={len(fams):2d}  qd_score={s.qd_score:.2f}")
        if args.compare:
            ga = EvolutionaryRedTeam(
                oracle, base,
                EvolutionConfig(population_size=40,
                                generations=max(1, args.evaluations // 40),
                                eval_samples=args.eval_samples))
            best = ga.evolve()
            gfam = _agent_family(best) if (best.evaded and best.objective_ok) else "(none)"
            ga_families.add(gfam)
            line += f"  | GA→ {gfam[:34]}"
        print(line)

    if detail_engine is not None:
        print(f"\n{'-'*78}\n ILLUMINATION MAP — {args.detail}  "
              f"(# = evading elite, o = detected, · = empty)\n{'-'*78}")
        print(detail_engine.render_map())
        print("\n  cheapest evasions by fragmentation level:")
        for e in detail_engine.evading_elites()[:8]:
            print(f"    comps={e.num_components:>3}  dist={e.distortion:.2f}  "
                  f"risk={e.max_cluster_risk:.2f}  {_agent_family(e)}")

    print(f"\n{'-'*78}\n DIVERSITY SUMMARY\n{'-'*78}")
    print(f"  distinct evading technique families (QD, all archetypes)   {len(all_families)}")
    print(f"  total evading cells across archetypes                      {total_evading_cells}")
    if args.compare:
        print(f"  distinct evading families found by the scalar GA           {len(ga_families)}")
        print(f"  → QD illuminates {len(all_families)} strategies where the GA keeps "
              f"{len(ga_families)}")
    print(f"  diverse evasions written to attack memory                  "
          f"{len(memory.hard_examples())} total records")
    print()


if __name__ == "__main__":
    main()
