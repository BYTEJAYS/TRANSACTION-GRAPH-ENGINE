# Phase 3 — Backend Redesign (DESIGN DOC, for approval)

> Status: **APPROVED & BUILT (against graceful-fallback path).** Code in `backend/core/`, `backend/repositories/`, `backend/api/v1/`, `backend/migrations/`. Verified: round-trip migration exact for 9 cases + 5 users (zero field loss); all modules import; app boots with 40 legacy `/api/cases` routes preserved + 4 new `/api/v1` routes; `TGIE_PERSIST=json` default. Live DB apply (m001/m002/m003 + flag flip) pending Docker install — see §8.
> Build decision: build-against-fallback-now; user runs migrations after installing Docker.
> Builds on: Phase 1 (locked Neo4j+Postgres+Redis), Phase 2 (graph schema in `backend/graph/schema/`).
> Iron rule: **ONLY ADD / ONLY IMPROVE.** Every existing module (`case_management`, `auth`, `risk_engine`, `fraud_dna`, `recovery`, `evidence`, `blue_team_v2`, UB, BELS) keeps working unchanged. We introduce a persistence layer *underneath* them and migrate data *into* it — behind feature flags with JSON fallback.

---

## 1. Goals
1. Make state **durable and shared** (survives restart; multiple API replicas see the same data) without removing the in-memory fast path.
2. Introduce a clean **layered architecture**: `API (v1) → service → repository → store(Neo4j/Postgres/Redis)`.
3. **Version + secure the API**: `/api/v1`, auth dependency on every non-public route, RBAC, and a read-audit trail (especially PII nodes).
4. Add an **append-only transaction event store** so timeline replay / reprocessing (Part 6) is possible.
5. Migrate `cases.json` and `investigators.json` into Postgres + Neo4j **idempotently and reversibly**.

## 2. Current state (audited, ground truth)
- Persistence = JSON files + threading locks: `case_management/_data/cases.json` (`{"cases":{case_id:{…42 fields…}}, "seq":int}`, 9 cases) and `auth/_data/investigators.json` (5 users, PBKDF2 hashes, explicit `ROLE_RANK`).
- API = `api/routes.py` (20 routes, mixed `/` and `/api/...` prefixes) + 6 routers bolted in `main.py` (`auth_router`, `cases_router`, `risk_router`, `dna_router`, `recovery_router`, `redteam_router`, optional `ub_router`) — **no version prefix, no central auth dependency, no pagination**.
- `config.py` already has `DATABASE_URL` (unused) and graceful Blue-Team degradation — we extend this pattern.

## 3. Target architecture

```
backend/
  core/                     # NEW — cross-cutting
    settings.py             # extends config.py: NEO4J_*, POSTGRES_*, REDIS_*, feature flags
    db/
      neo4j.py              # re-exports graph/schema/client.py
      postgres.py           # SQLAlchemy 2.0 async engine + session
      redis.py              # redis.asyncio pool (cache + queue)
    security/
      deps.py               # FastAPI deps: current_user, require_role, require_perm
      audit.py              # write AuditEntry (Postgres + :AuditEntry node) on every read of PII/case
  repositories/             # NEW — the ONLY code that talks to a store
    case_repo.py            # CRUD over Postgres `cases` (+ Neo4j Case/Alert/Evidence projection)
    user_repo.py            # Postgres `users`
    graph_repo.py           # Neo4j reads/writes; builds NetworkX subgraph projections
    event_repo.py           # append-only `txn_events` (Postgres) + Redis stream
  api/
    v1/                     # NEW — versioned routers, thin (delegate to services)
      __init__.py           # api_v1 = APIRouter(prefix="/api/v1"); includes all sub-routers
      graph.py cases.py alerts.py search.py risk.py evidence.py ...
  services/                 # NEW — business logic (today's modules become services)
    case_service.py  graph_service.py  search_service.py ...
  graph/schema/             # Phase 2 (done)
  graph_engine/             # legacy in-memory — now a CACHE/projection (unchanged API)
  case_management/ auth/ risk_engine/ ...   # PRESERVED; gain a repo-backed store option
```

**Key principle — Strangler-Fig migration:** we do *not* rewrite the modules. We put a `Repository` behind each, with two implementations selected by a feature flag:
- `TGIE_PERSIST=json` (default until Docker is up) → today's JSON store, **zero behaviour change**.
- `TGIE_PERSIST=db` → Postgres/Neo4j repos.
The store interface matches the existing `store.py` method names so the routers/services don't change.

## 4. Persistence mapping

| Concern | Store | Why |
|---|---|---|
| Entity graph (Customer/Account/Txn/Device/identity + all relationships) | **Neo4j** | relationship traversal is the product |
| Cases, Alerts, Users, Audit, Notes/Comments/Tasks, RegulatoryReports | **Postgres** | transactional, queryable, the system-of-record for workflow |
| Transaction **event log** (append-only) | **Postgres** `txn_events` + **Redis** stream | durable replay + live fan-out |
| Cache (subgraph projections, search results, risk scores) | **Redis** | hot-path latency |
| Evidence files | object store / disk (`evidence_storage/`), **hash-anchored in BELS** | already designed; keep |
| Live graph for viz / detectors | **NetworkX** (projected from Neo4j, cached in Redis) | preserves current fast path |

Case node duality: the **workflow record** (status, owner, SLA, notes) lives in Postgres; a lightweight `:Case` node + `PART_OF_CASE`/`STORE_EVIDENCE`/`INVESTIGATED_IN` edges live in Neo4j so cases are reachable in the graph explorer. `case_id` is the shared key.

## 5. API redesign (`/api/v1`)
- New umbrella `api/v1/__init__.py` mounts every resource router under `/api/v1`. **Back-compat:** the *existing* unversioned routes stay mounted (deprecated, logged) for one release so the frontend keeps working during migration — then frontend switches to `/api/v1` in Phase 6.
- **Consistent resource routers**: `graph, transactions, accounts, customers, cases, alerts, search, risk, evidence, dna, recovery, redteam`.
- **Pagination**: all list/graph endpoints take `?limit=&cursor=` (cursor = opaque, keyset-based) — fixes the unbounded `/api/graph/state`, `/api/alerts`, case list.
- **Auth dependency**: `Depends(current_user)` on every route except `/health`, `/api/v1/auth/login|register`. RBAC via `require_role(...)` / `require_perm(...)` (reuse `auth` `ROLE_RANK` + `collab` permission tiers — not reinvented).
- **Error contract**: uniform `{error:{code,message,detail}}`; request-id middleware; structured logging.
- **OpenAPI**: tags per resource; the contract becomes the bank-integration spec.

## 6. Security (Part 9 / banking-grade)
- Every route authenticated; graph & evidence routes — **currently unauthenticated** — gain the dependency. This is a real hole today.
- **Read-audit**: any read of a `pii:true` node (PAN/Aadhaar/Phone/Email/Address) or a case writes an `AuditEntry` (Postgres + `:AuditEntry` node) capturing actor/action/target/ts/ip → "who viewed what" (regulator requirement).
- **PII vault**: raw demo PAN/Aadhaar (if ever needed) only in a Postgres `pii_vault` table keyed by node id, access-gated to `Senior Investigator+`; graph holds only hash+mask.
- Secrets via env (no secrets in JSON); JWT unchanged (`auth/security.py`).

## 7. Transaction event store (enables replay)
- New Postgres table `txn_events(id, ts, payload jsonb, ingest_ts, seq bigserial)` — append-only, never updated.
- Ingestion writes the event, then projects into Neo4j (`Transaction` node + `SENT/RECEIVED_BY`) and pushes to a Redis stream that the WS broadcaster and detectors consume. The existing `FlinkStreamProcessor` becomes a consumer of this stream instead of the source of truth → **timeline replay = re-read `txn_events` between two timestamps**.

## 8. Migration plan (idempotent, reversible)

**8a. `investigators.json` → Postgres `users`**
- One-shot loader `migrations/m001_users.py`: read JSON, upsert by `employee_id` (idempotent), preserve `password_hash` verbatim (no re-hash), map `role`. Keeps JSON as backup; `TGIE_PERSIST=db` flips reads to Postgres.

**8b. `cases.json` → Postgres `cases` + Neo4j projection**
- Loader `migrations/m002_cases.py`: for each of the 42-field case objects → insert into `cases` (core workflow columns + `payload jsonb` for the rich enrich.py output: recovery/fraud_dna/graph_snapshot/raw_graph_json/etc., so **nothing is lost**), then MERGE a `:Case` node + edges to involved `:Account`s and `:Evidence`. Preserve `case_id` and `seq`.
- Idempotent: MERGE/upsert by `case_id`; re-running is safe.
- **Reversible**: a `dump_cases.py` re-exports Postgres → the original JSON shape, so we can roll back to `TGIE_PERSIST=json` at any time.

**8c. Graph seed**
- `migrations/m003_graph_seed.py`: load `datasets/sample_transactions.json` + any current in-memory accounts → Neo4j (`Account` + `SENT/RECEIVED_BY`), then run the projection job to build `TRANSFERRED_TO`. NetworkX then reads from Neo4j.

**Rollout sequence:** schema bootstrap (Phase 2) → m001 → m002 → m003 → flip `TGIE_PERSIST=db` in a canary → verify → make default.

## 9. Dependencies
- Python: `neo4j` (added), `sqlalchemy[asyncio]>=2.0`, `psycopg[binary]>=3.2`, `redis>=5`, `alembic` (Postgres migrations).
- Infra: `deployment/docker-compose.data.yml` (Phase 2) running → **needs Docker Desktop installed** (current blocker).

## 10. Risks & mitigations
| Risk | Mitigation |
|---|---|
| Big-bang rewrite breaks working modules | Strangler-fig + `TGIE_PERSIST` flag + JSON fallback; modules untouched |
| Migration data loss (rich 42-field cases) | Whole enrich payload preserved in `jsonb`; reversible `dump_cases.py` |
| Projection drift (Neo4j ↔ NetworkX ↔ Postgres) | Single writer per store; consistency check in Phase 10 tests |
| Async refactor introduces races | Repos async-first; keep sync JSON path for fallback; load-test in Phase 9 |
| No Docker on dev machine | All new code degrades gracefully (`available()`); JSON path remains default until Docker present |

## 11. Testing strategy (gate to Phase 4)
- Unit: each repository against a throwaway Neo4j/Postgres (testcontainers or the compose stack).
- Migration: load `cases.json` → assert round-trip `dump_cases.py` == original (field-for-field).
- Contract: every `/api/v1` route has an auth test (401 without token, 403 wrong role) + a pagination test.
- Parity: `TGIE_PERSIST=json` vs `db` return identical case/alert payloads for the 9 seed cases.
- Smoke: app boots with Neo4j/Postgres/Redis down → falls back to JSON, logs degradation, serves traffic.

## 12. Expected output
- `backend/core/`, `backend/repositories/`, `backend/api/v1/`, `backend/migrations/` created.
- `/api/v1/*` live alongside legacy routes; auth+pagination on all.
- `cases.json`/`investigators.json` migrated, reversibly, into Postgres+Neo4j with zero feature loss.
- Detectors/risk/recovery/DNA unchanged (they read `TRANSFERRED_TO` projection).

## 13. Open questions for sign-off
1. **Build order within Phase 3** — recommended: (a) `core/db` + settings + graceful wiring → (b) `/api/v1` skeleton + auth/pagination middleware (no behaviour change) → (c) repositories + migrations → (d) flip flag. OK?
2. **Frontend cutover to `/api/v1`** deferred to Phase 6 (keep legacy routes alive meanwhile) — OK?
3. **Docker**: do you want to install it now so Phase 3 can be verified live, or should I build Phase 3 against the graceful-fallback path and you run migrations once Docker is up?
