# deployment/

Everything needed to build, ship, and launch the TGIE ecosystem.

| File | Purpose |
|---|---|
| `DEPLOY.md` | Full Railway (backend) + Vercel (frontend) deployment guide |
| `railway.toml` | Railway build/deploy config (NIXPACKS, `/health`, `sh -c` start wrapper) |
| `nixpacks.toml` | Points nixpacks at `backend/requirements.txt`, Python 3.11 |
| `docker-compose.yml` | Full local stack (heavy build: Postgres, Redis, Kafka, Flink) |
| `infrastructure/` | Flink + Kafka configs (heavy build only) |
| `TGIE-launch.command` | macOS double-click launcher (backend + frontend) |
| `TGIE-stop.command` | macOS stop launcher |
| `start.sh` | Repo-root start script (also in `../scripts/`) |

## Branch strategy

```
main        full heavy build — Kafka, GNN, docker-compose, all services
production  deploy-optimized — what runs on Railway + Vercel
```
**Never merge `production → main`.** When scaling up, merge `main → production`.

## Critical deploy lessons (from DEPLOY.md)

- `railway.toml` **must** be at repo root (Railway deploys from root).
- Start command must use `sh -c '...'` — exec form passes `${PORT:-8000}` literally.
- `ALLOWED_ORIGINS=*` requires `allow_credentials=False`.
- `ALLOWED_ORIGINS` must be typed `str` (not `List[str]`) — pydantic-settings json.loads()
  on list env vars before validators run.
- Vercel: Root `frontend/`, Production Branch `production`, env `VITE_API_URL`. Use the
  production domain alias, never a hashed deployment URL.

## Live URLs

- Backend: `https://transaction-graph-engine-production.up.railway.app`
- Frontend: Vercel `production` branch.

> BLING Blue Team and CRUCIBLE deploy separately (Union Bank) via their own
> `docker-compose.yml` — not part of the public TGIE deploy.
