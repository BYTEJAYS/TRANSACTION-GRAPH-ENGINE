# TGIE → Financial Fraud Intelligence Platform — Redesign Summary

A 10-phase, design-doc-per-phase redesign that evolved the MVP into an
enterprise-shaped fraud investigation platform. Authoritative tree: `~/Desktop/TGIE`.
Iron rule throughout: **ONLY ADD / ONLY IMPROVE** — no feature removed; everything
degrades gracefully without the data stack.

## Locked decisions
- **Persistence:** Neo4j (entity graph) + Postgres (cases/users/audit/events) + Redis (cache/queue) + object store (evidence, BELS-anchored). NetworkX demoted to hot-cache/demo projection.
- **Cadence:** design doc → approval → build → verify → gate, per phase.

## Phase outcomes
| # | Phase | Status | Key artifacts |
|---|---|---|---|
| 1 | Architecture audit | ✅ | 19-dimension audit; found the wrong (in-memory) Blue Team was wired in; the dormant `bling` Neo4j engine to re-converge on |
| 2 | Graph schema | ✅ built | `backend/graph/schema/*` — 39 labels / 50 rels, reified Transaction + derived `TRANSFERRED_TO`, idempotent Cypher DDL; 62 stmts |
| 3 | Backend redesign | ✅ built (fallback) | `core/` (db+security), `repositories/`, `api/v1/`, `migrations/`; strangler-fig `TGIE_PERSIST=json\|db`; reversible cases/users migration |
| 4 | Detection library | ✅ Wave 1 | 11→22 detectors (diamond/nested/round-trip/hub/scatter-gather/structuring/cash/night/weekend/temporal/uniform) + entity-context bridge |
| 5 | ML engine | ✅ Wave A | `ml/platform/` registry+feature-store+ensemble+drift+explain; RF/IF/XGB wrappers; ROC-AUC 0.93; capped factor into risk engine |
| 6 | Frontend | ✅ Waves 1–2 | single Cytoscape renderer; workstation shell (Cmd-K, dockable/resizable panels, selected-entity context); cinematic lazy-split |
| 7 | Investigation panels | ✅ Wave 1 | panel registry + filters + bookmarks + Score/Explain/Patterns/Audit/Workflow/Evidence panels; v1-first resource APIs |
| 8 | Evidence package | ✅ Wave 1 | server-side deterministic 15-section bundle, SHA-256, reportlab PDF, FIU-IND STR, BELS anchor (graceful) |
| 9 | Performance | ✅ Wave 1 | `core/cache` (Redis-or-LRU), `async_utils.run_cpu` offload, `tasks` (inline-or-Celery), precompute/retrain jobs; ~1233× cache speedup |
| 10 | Testing | ✅ Wave 1 | pytest config + conftest; API-contract/auth, evidence-determinism, migration tests; **81 tests pass**; readiness 80/80 |

## Verification (no Docker)
- **81 tests pass** suite-wide; frontend `tsc` clean + `npm run build` OK.
- Readiness scorecard **80/80** (migration, detection, ML, evidence, performance, API). See `scripts/readiness.py`.
- Bug fixed in Phase 10: `case_repo` json branch (`store.list_cases/get_case` → `.all()/.get()`).

## What remains (Wave 2 — needs Docker)
Bring up `deployment/docker-compose.data.yml`, then:
```
cd backend
python3 -m graph.schema.bootstrap        # apply Neo4j schema
python3 -m migrations.run --all          # load Postgres + Neo4j; set TGIE_PERSIST=db to flip
```
Then the **live** acceptance tests (`pytest -m live`) and Wave 2 features unlock:
identity-ring detectors (L9), Neo4j GDS precompute, real Celery/Redis workers,
BELS custody/verify round-trip, timeline/fund-journey replay, geo/heatmap, FIU PDF,
multi-replica stateless API. Frontend visual screenshot of the workstation also pending a dev-server run.

## Run it
```
# backend (json/demo mode, no Docker)
cd backend && uvicorn main:app --port 8000
# frontend
cd frontend && npm run dev        # http://localhost:3000 → /workstation
# scorecard / benchmark
cd backend && python3 -m scripts.readiness && python3 -m scripts.bench_detection
```
