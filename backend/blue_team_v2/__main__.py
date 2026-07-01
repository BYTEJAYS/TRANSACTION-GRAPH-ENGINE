"""
Blue Team V2 CLI.

    python -m blue_team_v2 benchmark            # V1 vs V2 benchmark report
    python -m blue_team_v2 demo                 # analyse a sample fraud cluster
    python -m blue_team_v2 shadow               # shadow-mode comparison on a mix
    python -m blue_team_v2 scale 100 1000 10000 # scalability timing
"""
from __future__ import annotations

import asyncio
import json
import sys
import time


def _benchmark() -> None:
    from .benchmark.runner import format_report, run_benchmark
    report = asyncio.run(run_benchmark(n_fraud=10, n_normal=10))
    print(format_report(report))


def _demo() -> None:
    from .adapter import analyze_component_sync
    from .simulation.generators import Simulator
    comp, gt = Simulator().hybrid()
    out = analyze_component_sync(comp)
    v2 = out["v2"]
    print(f"Verdict: {out['verdict']}  Risk: {out['risk_score']:.2%}  "
          f"Confidence: {v2['confidence']:.2%}")
    print(f"Classification: {v2['primary_classification']} / {v2['secondary_classification']}")
    print(f"Patterns: {v2['cluster_intelligence']['patterns_detected']}")
    print(f"\nNarrative:\n  {v2['narrative']}")
    print("\nNode risk scores (differentiated, no blanket scoring):")
    for nid, score in sorted(v2["node_risk_scores"].items(), key=lambda x: -x[1]):
        role = v2["node_intelligence"][nid]["role"]
        print(f"  {nid:<14} {score:6.2%}  [{role}]")
    print(f"\nGround truth: {gt.expected_verdict}, fraud nodes={len(gt.fraud_nodes)}")


def _shadow() -> None:
    from .shadow import run_shadow
    from .simulation.generators import Simulator
    sim = Simulator()
    components = [c for c, _ in sim.mixed_dataset(n_fraud=3, n_normal=3)]
    result = asyncio.run(run_shadow(components))
    print(f"Agreement V1↔V2: {result['agreement']['agreed']}/{result['agreement']['graphs']} "
          f"({result['agreement']['rate']:.0%})")
    print(f"V1 time: {result['v1']['time_ms']:.1f}ms   V2 time: {result['v2']['time_ms']:.1f}ms\n")
    for c in result["comparison"]:
        print(f"  {c['graph_id']}: V1={c['v1']['verdict']:<10} V2={c['v2']['verdict']:<10} "
              f"Δrisk={c['delta_risk']:+.2f}  {'AGREE' if c['agreement'] else 'DIFFER'}"
              f"  [{c['v2'].get('primary_classification') or '-'}]")


def _scale(sizes: list[int]) -> None:
    from .adapter import analyze_component_sync
    from .simulation.generators import Simulator
    print(f"{'Nodes':>10}{'Edges':>10}{'Time (ms)':>14}{'Verdict':>12}")
    print("-" * 46)
    for n in sizes:
        comp, _ = Simulator(seed=1).scale_test(n)
        t0 = time.perf_counter()
        out = analyze_component_sync(comp)
        dt = (time.perf_counter() - t0) * 1000
        print(f"{n:>10}{len(comp['edges']):>10}{dt:>14.1f}{out['verdict']:>12}")


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "benchmark"
    if cmd == "benchmark":
        _benchmark()
    elif cmd == "demo":
        _demo()
    elif cmd == "shadow":
        _shadow()
    elif cmd == "scale":
        sizes = [int(x) for x in args[1:]] or [100, 1000, 10000]
        _scale(sizes)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
