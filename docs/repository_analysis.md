# TGIE Repository Analysis

> Generated during the TGIE Final Product Assembly. Source of truth: the consolidated
> `TGIE/` workspace assembled from four repositories on 2026-06-24.

---

## 1. Source Repositories

| Component | Origin | GitHub | Imported to |
|---|---|---|---|
| **TGIE Core Engine + Frontend + UB** | `~/transaction-graph-intelligence` (branch `production`) | `BYTEJAYS/TRANSACTION-GRAPH-ENGINE` | `backend/`, `frontend/`, `ub/` |
| **In-repo Red Team (isolated)** | `~/transaction-graph-intelligence/red_team` | same | `red_team/engine/` |
| **Adversarial self-play program** | `~/transaction-graph-intelligence/adversarial` | same | `red_team/adversarial/` |
| **BLING Blue Team (Union Bank :8001)** | `~/bling-blue-team` (branch `main`) | `BYTEJAYS/bling-blue-team` | `blue_team/bling/` |
| **BLING Blue Team v2** | `~/blue team v2` | (points at TGE remote) | `blue_team/bling-v2/` |
| **CRUCIBLE Red Team (Union Bank)** | `~/red team union bank` | (points at TGE remote) | `red_team/crucible/` |

> **Import policy:** clean copies only. `node_modules/`, `.venv/`, `.git/`, `__pycache__/`,
> caches, build output and runtime `_data/` were excluded. Original repositories were left
> **untouched** — this workspace is additive. Restore dependencies with `pip install -r requirements.txt`
> and `npm install` per component.

---

## 2. Architecture (high level)

```
            ┌──────────────────────────────────────────────────────────┐
            │                     TGIE FRONTEND (Vite SPA, :3000)        │
            │   React 18 · react-force-graph-3d · three.js · framer     │
            │   UB (Universal Brain) voice assistant · risk intel layer │
            └───────────────┬───────────────────────────┬──────────────┘
                            │ WS /ws/live   POST /transaction/manual
                            ▼                           ▼
            ┌──────────────────────────────────────────────────────────┐
            │              TGIE CORE BACKEND (FastAPI, :8000)            │
            │  graph_engine (networkx) · simulator · streaming          │
            │  Blue Team router → V1 (ML) | V2 (deterministic graph)    │
            │  anomaly_detection (IsolationForest) · fraud_classifier   │
            │  api/redteam.py (localhost-gated adversarial panel)       │
            └───────────────┬──────────────────────────────────────────┘
                            │ (optional, per TGIE_README architecture)
                            ▼
            ┌──────────────────────────────────────────────────────────┐
            │         BLING BLUE TEAM API (FastAPI, :8001)              │
            │  SQLAlchemy + Postgres · Neo4j graph · Redis/Celery       │
            │  detection · evidence (forensic PDF) · ML bridges         │
            └──────────────────────────────────────────────────────────┘

  Offline / research plane:
    red_team/adversarial   — Red⇄Blue self-play (GA, MAP-Elites, PPO, GraphGAN)
    red_team/engine        — in-repo isolated red team (datasets, scenarios)
    red_team/crucible      — CRUCIBLE evolutionary fraud-genome engine + human gate
```

---

## 3. Services & Runtimes

| Service | Stack | Port | State |
|---|---|---|---|
| TGIE Frontend | Vite + React 18 + TS | 3000 | Active (Vercel `production`) |
| TGIE Core Backend | FastAPI + Uvicorn (Py 3.11 deploy / 3.14 local) | 8000 | Active (Railway `production`) |
| Blue Team V1 | scikit-learn IsolationForest + XGBoost + rule classifier | in-proc | Active (default engine) |
| Blue Team V2 | deterministic graph engine, 11 detectors | in-proc | Opt-in via `ACTIVE_BLUE_TEAM` |
| BLING Blue Team | FastAPI + Postgres + Neo4j + Celery | 8001 | Standalone (Union Bank) |
| CRUCIBLE Red Team | evolutionary engine + workers + human gate | offline | Standalone (Union Bank) |
| Adversarial self-play | pure-NumPy GA/QD/PPO/GAN | offline | Research |

---

## 4. Dependency Graph (key)

**TGIE Core Backend** — `fastapi 0.111`, `uvicorn 0.29`, `pydantic 2.7`, `networkx 3.3`,
`scipy 1.13`, `scikit-learn 1.4.2`, `xgboost 2.0.3`, `shap 0.45`, `numpy 1.26.4`,
`pandas 2.2`, `reportlab` (evidence PDFs), `faker`, `orjson`.
*Removed for deploy:* `aiokafka`, PyTorch Geometric (GNN), live retrain loop.

**Frontend** — `react 18.3`, `react-force-graph-3d 1.29`, `three 0.184`,
`@react-three/fiber/drei/postprocessing`, `d3-force-3d`, `d3-quadtree`, `d3-scale`,
`framer-motion 11`, `gsap`, `recharts`, `cytoscape`, `jspdf`/`html2canvas` (export),
`leva` (dev tuning), `lucide-react`.

**BLING Blue Team** — `fastapi`, `sqlalchemy 2.0`, `alembic`, `psycopg2-binary 2.9.9`
(pins Python ≤3.11), `asyncpg`, `neo4j 5.20`, Redis/Celery, scikit-learn.

**Adversarial** — pure NumPy only (deliberately torch-free; deployment removed PyTorch).

---

## 5. Consolidated Folder Structure

```
TGIE/
├── frontend/        TGIE Vite SPA (graph viz + UB)
├── backend/         TGIE core engine (FastAPI, graph, blue_team V1/V2, anomaly, sim)
├── ub/              Universal Brain — extracted AI-assistant source for reference
├── blue_team/
│   ├── bling/       BLING Blue Team API (Union Bank, :8001)
│   └── bling-v2/    BLING Blue Team v2
├── red_team/
│   ├── engine/      in-repo isolated red team (datasets, scenarios)
│   ├── adversarial/ Red⇄Blue self-play research program (+ reports/)
│   └── crucible/    CRUCIBLE evolutionary fraud-genome engine + human gate
├── shared/          cross-cutting contracts (see shared/README.md)
├── docs/            all generated analysis/audit/architecture docs
├── tests/           test index → per-component test suites
├── deployment/      railway.toml, nixpacks.toml, docker-compose, DEPLOY.md, launchers, infrastructure/
├── monitoring/      observability plan (see monitoring/README.md)
├── scripts/         start-all / stop-all / start.sh
├── configs/         environment templates
├── logs/            runtime logs (gitignored)
├── datasets/        sample transactions + scenario corpora
├── research/        pointers to research artifacts
├── backups/         pre-cleanup snapshots
└── .github/         CI workflow
```

---

## 6. Missing / Placeholder Components

| Expected | Status | Notes |
|---|---|---|
| Shared libraries package | **Placeholder** | No formal shared package exists today; verdict schema is the de-facto contract duplicated across V1/V2/hardened. See `shared/README.md` for the proposed extraction. |
| Monitoring stack | **Placeholder** | No Prometheus/Grafana/OTel today; `/health` endpoint only. Plan in `monitoring/README.md`. |
| Unified test runner | **Partial** | 5 separate suites (pytest per backend component, none on frontend). |
| Frontend tests | **Missing** | No vitest/playwright; verification is manual via puppeteer screenshots. |
| GNN model (trained) | **Missing/known** | GraphSAGE/GAE in V2 ships with random weights (never trained) — see audits. |

---

## 7. Technical Debt

- **Two Blue Team generations coexist** (V1 ML, V2 deterministic) selected by `ACTIVE_BLUE_TEAM`; V2 is faster/more accurate but not the default in production.
- **Verdict schema is duplicated** across V1 adapter, V2 adapter, and the hardened integration rather than defined once in `shared/`.
- **Frontend `GraphScene.tsx` is 1,287 lines** — a single monolith mixing force config, camera, rendering, intel overlays, and event handling.
- **GNN never trained** (random weights) yet still wired into V2's class output — dead/noise signal.
- **Label leakage in V1** — `IsolationForest.score` reads ground-truth `txn.fraud_pattern` (B5); must be stripped from any honest eval harness.
- **Dead JSX** left in `App.tsx` (header wrapped in `{false && (…)}`).
- **Three Python interpreters** in play (3.11 deploy, 3.14 local TGIE, ≤3.11 BLING) — documented but fragile.

---

## 8. Security Concerns (summary — full detail in production_readiness_report.md)

- `ALLOWED_ORIGINS=*` with `allow_credentials=False` in production (acceptable but permissive).
- `BLUE_TEAM_API_KEY` is a static shared secret committed in env docs (`tgie-secret-2025`) — rotate and move to a secret manager.
- The localhost-gated `api/redteam.py` panel is double-gated (env `ENABLE_REDTEAM_PANEL` + hostname regex) — verify the gate before any non-local deploy.
- BLING Blue Team uses `psycopg2-binary` and DB creds in compose; ensure no default `trust` auth reaches a public surface.
- No rate limiting / authN on the public TGIE WebSocket and `/transaction/manual` endpoint.

See `blue_team_audit.md`, `red_team_audit.md`, and `production_readiness_report.md` for depth.
