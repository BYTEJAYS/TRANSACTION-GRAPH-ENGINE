"""
Detection throughput benchmark + cache-speedup demo (Phase 9). No Docker needed.

    python -m scripts.bench_detection

Builds synthetic components of increasing size, times a full detector+risk pass,
and demonstrates that a cached repeat is far faster than a cold compute.
"""
from __future__ import annotations

import random
import time

from blue_team_v2.core.graph_engine.builder import TransactionGraph
from blue_team_v2.core.risk_engine.node_intelligence import RiskEngine
from blue_team_v2.core.pattern_engine.orchestrator import PatternEngine
from core import cache


def synth_component(n: int, seed: int = 1) -> dict:
    rng = random.Random(seed)
    nodes = [{"id": f"A{i}"} for i in range(n)]
    edges = []
    for i in range(n * 2):                      # ~2 edges/node
        a, b = rng.randrange(n), rng.randrange(n)
        if a != b:
            edges.append({"source": f"A{a}", "target": f"A{b}",
                          "amount": rng.choice([25_000, 90_000, 250_000, 8_60_000]),
                          "payment_rail": rng.choice(["UPI", "IMPS", "RTGS", "NEFT"]),
                          "timestamp": f"2026-06-01T{rng.randrange(24):02d}:00:00"})
    return {"graph_id": f"G{n}", "nodes": nodes, "edges": edges}


def run_pipeline(component: dict) -> int:
    tg = TransactionGraph(component)
    metrics, _cluster, meta = RiskEngine(tg).compute()
    evidence = PatternEngine().run(tg, metrics, meta)
    return len(evidence)


@cache.cached(ttl=60, key_fn=lambda c: c["graph_id"])
def cached_pipeline(component: dict) -> int:
    return run_pipeline(component)


def main() -> int:
    print(f"cache backend: {cache.backend()}\n")
    print(f"{'nodes':>7} {'edges':>7} {'detectors_ms':>13} {'findings':>9}")
    for n in (100, 500, 1000, 2000):
        comp = synth_component(n)
        t0 = time.perf_counter()
        findings = run_pipeline(comp)
        dt = (time.perf_counter() - t0) * 1000
        print(f"{n:>7} {len(comp['edges']):>7} {dt:>13.1f} {findings:>9}")

    # cache speedup demo on the 1000-node component
    comp = synth_component(1000)
    cache.clear_local()
    t0 = time.perf_counter(); cached_pipeline(comp); cold = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter(); cached_pipeline(comp); warm = (time.perf_counter() - t0) * 1000
    speedup = cold / warm if warm else float("inf")
    print(f"\ncache cold: {cold:.1f} ms | warm: {warm:.3f} ms | speedup: {speedup:.0f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
