<div align="center">

# TGIE — Transaction Graph Intelligence Engine

### Final Product Workspace · Single Source of Truth

Real-time 3D fraud-detection ecosystem: a graph engine, adversarial Blue/Red teams,
a voice "Universal Brain", and a forensic Union Bank service — assembled into one
production-grade workspace.

</div>

---

## What this is

This `TGIE/` folder is the **consolidated master workspace** for the entire TGIE
ecosystem, assembled from four source repositories on 2026-06-24. It is a clean,
organized, additive copy — original repos were left untouched.

| Folder | Component | Source |
|---|---|---|
| `frontend/` | Vite + React 18 + three.js SPA (3D graph + UB) | TRANSACTION-GRAPH-ENGINE |
| `backend/` | FastAPI core engine: graph, simulator, Blue Team V1/V2, anomaly | TRANSACTION-GRAPH-ENGINE |
| `ub/` | Universal Brain — extracted voice-assistant source | TRANSACTION-GRAPH-ENGINE/frontend |
| `blue_team/bling/` | BLING Blue Team API (Union Bank, :8001) | bling-blue-team |
| `blue_team/bling-v2/` | BLING Blue Team v2 | "blue team v2" |
| `red_team/engine/` | In-repo isolated red team + scenario datasets | TRANSACTION-GRAPH-ENGINE/red_team |
| `red_team/adversarial/` | Red⇄Blue self-play (GA, MAP-Elites, PPO, GraphGAN) + reports | TRANSACTION-GRAPH-ENGINE/adversarial |
| `red_team/crucible/` | CRUCIBLE evolutionary fraud-genome engine + human gate | "red team union bank" |
| `shared/` | Cross-cutting contracts (proposed — see README) | — |
| `docs/` | All analysis / audit / architecture docs | generated |
| `deployment/` | Railway, nixpacks, docker-compose, launchers, infra | TRANSACTION-GRAPH-ENGINE |
| `scripts/` · `configs/` · `monitoring/` · `datasets/` · `tests/` · `research/` · `logs/` · `backups/` | support | mixed |

---

## Start here

1. **`docs/repository_analysis.md`** — architecture, services, dependency graph, debt.
2. **`docs/TGIE_MASTER_ARCHITECTURE.md`** — full ecosystem, data/feedback loops, diagrams.
3. **`docs/production_readiness_report.md`** — scored /100 + prioritized issues.
4. **`docs/blue_team_audit.md`** / **`docs/red_team_audit.md`** — subsystem scorecards.
5. **`docs/frontend_review.md`** / **`docs/graph_validation.md`** — UI + the rhombus fix.

---

## Run it locally

**TGIE backend** (from `backend/`, after `python -m venv .venv && pip install -r requirements.txt`):
```bash
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
```
**TGIE frontend** (from `frontend/`, after `npm install`):
```bash
npm run dev          # http://localhost:3000  (Vite proxies /api and /ws → :8000)
```
> The 3D graph requires the backend running on :8000 — without it, submitted
> transactions produce nothing (a canned mock appears only after the WS fallback).

**Red Team panel** (localhost only): start backend with `ENABLE_REDTEAM_PANEL=1`.

**Convenience launchers:** see `scripts/` (`start-all.sh`, `stop-all.sh`) and
`deployment/TGIE-launch.command`.

---

## Live deployment

- Backend: `https://transaction-graph-engine-production.up.railway.app`
- Frontend: Vercel (`production` branch, root `frontend/`)
- Branch strategy: `main` = full heavy build, `production` = deploy-optimized. Never merge `production → main`.

See `deployment/DEPLOY.md` for the full guide.

---

## Provenance & integrity

- Clean copies: `node_modules/`, `.venv/`, `.git/`, caches, build output and runtime
  `_data/` were excluded. Reinstall deps per component.
- This workspace is **additive** — the four source repositories were not modified or deleted.
- No destructive cleanup was performed during assembly; cleanup *candidates* are listed in
  `docs/production_readiness_report.md` and `backups/README.md` rather than executed.
