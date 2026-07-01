# Phase 9 — Performance & Scalability (DESIGN DOC, for approval)

> Status: **APPROVED · Wave 1 BUILT & VERIFIED.** New: `core/cache.py` (Redis-or-LRU, `@cached`, version keys), `core/async_utils.py` (`run_cpu` threadpool offload), `core/tasks.py` (inline-or-Celery `enqueue` + registry), `jobs/precompute.py` (centrality+community) + `jobs/retrain.py` (wraps Phase 5), `scripts/bench_detection.py`. Verified (no Docker, `local` cache backend): **cache cold 787ms → warm 0.64ms = ~1233× speedup** (target ≥10×); async offload runs concurrently (<0.18s for 2×0.1s); inline tasks + registry work; pipeline scales 100→2000 nodes; **53 tests pass** suite-wide, zero regressions. Wave 2 (real Celery/Redis workers, Neo4j GDS precompute, multi-replica) pending Docker.
> Sign-off: Celery+inline fallback ✅ · Redis+LRU cache ✅ · Wave-1-first ✅
> Builds on: Phase 3 (async repos, Redis client, cursor pagination), Phase 4 detectors, Phase 5 ML, Phase 6 virtualization + lazy graph, BELS. Reuses the dormant `bling/nightly_batch` + `celeryconfig` precompute design.
> Iron rule: **ONLY ADD.** Hot paths gain a cache/worker/offload layer *in front of* existing logic; nothing is rewritten. Everything degrades gracefully without Docker (in-process fallbacks), consistent with prior phases.

## 1. Goals (Part 10)
Make the platform survive **millions of accounts/transactions**: graph caching, lazy/incremental loading, parallel graph algorithms, background processing, async APIs, pagination, virtualization — without breaking the single-process demo mode.

## 2. Current bottlenecks (audited)
- **Full recompute per request**: detectors + risk + centralities run over the whole component on every call; NetworkX `cycles()`/`communities()`/`betweenness` are O(V·E) **on the request thread** → blocks the event loop on large graphs (Phase 1 #3/#13).
- **No cache**: identical subgraph/risk computations repeat.
- **No workers**: heavy jobs (precompute, ML retrain, identity-collision projection) have nowhere to run off-request.
- **State in one process** (`app_state`) → no horizontal scale (Phase 1 #14; addressed structurally by Phase 3 stores, finished here).

## 3. Target layers (in front of existing logic)
```
backend/core/
  cache.py         # NEW — get/set/memoize with TTL; Redis when up, in-process LRU fallback; key versioning
  async_utils.py   # NEW — run_cpu(fn,...) offloads CPU-bound graph ops to a threadpool (frees event loop)
  tasks.py         # NEW — task abstraction: enqueue→Celery if broker present, else run INLINE; task registry
backend/jobs/      # NEW — the heavy jobs (callable inline or as Celery tasks)
  precompute.py    # centrality/community/Louvain → store as node props (NetworkX now; Neo4j GDS when up)
  projections.py   # TRANSFERRED_TO aggregation + SHARES_*/SAME_* identity-collision builder (Phase 2/4 Wave 2)
  retrain.py       # wraps ml.platform.training.train_and_register
scripts/
  bench_detection.py  # NEW — load/throughput benchmark vs graph size (verifiable now, no Docker)
```

### 3.1 Caching (`core/cache.py`)
- `@cached(ttl, key=...)` and `cache.get/set`. Backend: **Redis when `redis.available()`**, else a bounded in-process LRU — so caching works (and is testable) without Docker, then transparently uses Redis in prod.
- Cache the hot, idempotent results: **subgraph projections** (by seed+hops), **risk assessments** (by component hash), **detector evidence** (by component hash), **search results**. Keys carry a `model/detector version` so a deploy invalidates stale entries.

### 3.2 Async offload (`core/async_utils.py`)
- `await run_cpu(fn, *args)` runs CPU-bound NetworkX work in a threadpool/executor so the FastAPI event loop never blocks. The expensive endpoints (cycles, communities, path, analysis) call through this.
- Bounds already present in the builder (length-bounded cycles, sampled betweenness) are kept; offload removes the *blocking*, precompute removes the *repetition*.

### 3.3 Background processing (`core/tasks.py` + `jobs/`)
- **Task abstraction**: `tasks.enqueue("precompute_centrality", graph_id)`. If a Celery broker (Redis) is configured → enqueue; else **run inline** (so dev/demo works). One code path, two runtimes.
- Jobs: centrality/community **precompute** (results stored as node props → requests read precomputed, not recompute), **identity-collision projection** (builds `SHARES_*` edges — unblocks Phase 4 Wave 2 ring detectors), `TRANSFERRED_TO` aggregation, **ML retrain** (drift-triggered, Phase 5).
- Reuses the `bling/nightly_batch` design + the existing `celeryconfig.py`.

### 3.4 Parallel graph algorithms
- Per-component analysis is embarrassingly parallel (each connected component is independent — the builder already isolates them). Workers process components in parallel; the precompute job fans out per component.
- Neo4j **GDS** (in the data compose) runs Louvain/centrality server-side at scale when Neo4j is up; NetworkX greedy-modularity is the fallback.

### 3.5 Async APIs & pagination
- Repos are async (Phase 3); ensure no sync DB/CPU call blocks a route (offload via `run_cpu`).
- **Keyset cursor pagination** enforced server-side on every list/graph endpoint (cases done in Phase 3; extend to alerts/transactions/search). Graph endpoints return bounded neighbourhoods + a cursor for "expand more".

### 3.6 Incremental / lazy / virtualized (already partly built)
- Frontend: `VirtualList` (built) + progressive graph expand-on-demand (Phase 6 hook) + lazy-split bundles (Phase 6).
- Backend: `graph_repo.neighbourhood` (built) returns bounded n-hop subgraphs; this phase adds caching + cursor to it.

## 4. Performance budget (targets, measured by `bench_detection.py`)
| Operation | Target |
|---|---|
| Full detector+risk pass on a 1k-node component | < 500 ms (cached: < 10 ms) |
| Neighbourhood expand (2 hops, ≤500 nodes) | < 150 ms |
| Cases list page (cursor) | < 100 ms |
| Centrality/community | moved to precompute (0 ms on request; read node props) |
| Event-loop block per request | ~0 (CPU work offloaded) |

## 5. Build order (waves)
- **Wave 1 (now, no Docker — graceful):** `core/cache.py` (Redis-or-LRU), `core/async_utils.py` (threadpool offload), `core/tasks.py` (inline-or-Celery), `jobs/precompute.py` (NetworkX) + `jobs/retrain.py` (wraps Phase 5), `scripts/bench_detection.py`. Wire caching into one hot path (risk/subgraph) to prove it. **Verify:** benchmark shows cache hit ≫ faster; offload keeps loop free; tasks run inline; precompute populates node props; tests.
- **Wave 2 (needs Docker):** real Celery workers + Redis broker, Neo4j GDS precompute, distributed cache, multi-replica stateless API, scheduled nightly batch.

## 6. Risks & mitigations
| Risk | Mitigation |
|---|---|
| Cache staleness | version keys by detector/model version + TTL + explicit invalidation on writes |
| Inline tasks block dev | inline tasks are for dev/demo small data; prod uses Celery; benchmark guards the budget |
| Threadpool starvation | bounded executor; only CPU-bound graph ops offloaded; I/O stays async |
| Precompute drift vs live graph | precompute job re-runs on ingest batch / schedule; request falls back to live compute if node props absent |
| Correctness under concurrency | single writer per store (Phase 3); cache is read-through; idempotent jobs |

## 7. Testing / verification
- `bench_detection.py`: detector+risk throughput on synthetic graphs of 100→5k nodes; assert within budget; assert **cache hit is ≥10× faster** than cold.
- Cache: get/set round-trip; LRU fallback when Redis absent; version-key invalidation.
- Offload: `run_cpu` returns correct result and doesn't block (concurrent calls overlap).
- Tasks: `enqueue` runs inline without a broker; registry resolves names.
- Precompute: job writes centrality/community to node props; request reads them.
- No-regression: detector/risk outputs identical with cache on vs off.

## 8. Expected output
- `core/cache.py`, `core/async_utils.py`, `core/tasks.py`, `jobs/`, `scripts/bench_detection.py`.
- Hot paths cached + offloaded; heavy work enqueueable; benchmark proving the budget.
- All graceful without Docker; Redis/Celery/GDS engage automatically when present.

## 9. Open questions for sign-off
1. Worker tech = **Celery** (compose + `celeryconfig.py` already exist) with **inline fallback**. **Recommended: yes.**
2. Cache = **Redis when up, in-process LRU fallback**. **Recommended: yes.**
3. **Wave 1 now** (cache + offload + task abstraction + precompute + benchmark, verifiable without Docker) before the Docker-dependent Wave 2. **Recommended: yes.**
