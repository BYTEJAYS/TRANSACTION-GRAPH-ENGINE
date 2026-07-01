"""Phase 9 Wave 1 — cache, async offload, task abstraction, precompute job."""
from __future__ import annotations

import asyncio
import time

from core import cache
from core.async_utils import run_cpu
from core import tasks
import jobs.precompute  # noqa: F401  (registers tasks)
import jobs.retrain     # noqa: F401


def test_cache_round_trip():
    cache.clear_local()
    k = cache.make_key("unit", 1, version="t")
    assert cache.get(k) is None
    cache.set(k, {"x": 1}, ttl=30)
    assert cache.get(k) == {"x": 1}


def test_cache_memoize_speedup():
    cache.clear_local()
    calls = {"n": 0}

    @cache.cached(ttl=30, version="t", key_fn=lambda x: x)
    def slow(x):
        calls["n"] += 1
        time.sleep(0.05)
        return x * 2

    t0 = time.perf_counter(); assert slow(21) == 42; cold = time.perf_counter() - t0
    t0 = time.perf_counter(); assert slow(21) == 42; warm = time.perf_counter() - t0
    assert calls["n"] == 1, "second call should hit cache, not recompute"
    assert warm < cold / 5, f"cache not faster (cold={cold}, warm={warm})"


def test_run_cpu_offload():
    def work(a, b):
        return a + b
    assert asyncio.run(run_cpu(work, 2, 3)) == 5


def test_run_cpu_concurrent_overlap():
    # two 0.1s blocking calls should overlap (run in parallel threads) → < 0.18s
    def block():
        time.sleep(0.1); return 1
    async def both():
        return await asyncio.gather(run_cpu(block), run_cpu(block))
    t0 = time.perf_counter()
    asyncio.run(both())
    assert time.perf_counter() - t0 < 0.18


def test_tasks_inline():
    comp = {"graph_id": "G", "nodes": [{"id": "A"}, {"id": "B"}],
            "edges": [{"source": "A", "target": "B", "amount": 50000,
                       "payment_rail": "UPI", "timestamp": "2026-06-01T10:00:00"}]}
    res = tasks.enqueue("precompute_centrality", comp)
    assert res["mode"] == "inline"
    assert "A" in res["result"] and "B" in res["result"]


def test_task_registry():
    for name in ("precompute_centrality", "precompute_community", "retrain_models"):
        assert name in tasks.registered()
