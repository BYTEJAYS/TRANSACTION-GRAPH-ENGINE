# configs/

Aggregated environment templates (copies; the authoritative `.env.example` files live with
each component). **Never commit real `.env` files** — only `*.env.example`.

| File | For | Key vars |
|---|---|---|
| `backend.env.example` | TGIE core backend | `ACTIVE_BLUE_TEAM`, `ALLOWED_ORIGINS`, `BLUE_TEAM_API_KEY`, `GRAPH_MAX_NODES/EDGES`, `ENABLE_REDTEAM_PANEL`, `LOG_LEVEL`, `DEBUG` |
| `frontend.env.example` | TGIE frontend | `VITE_API_URL` |
| `bling-blue-team.env.example` | BLING service | Postgres/Neo4j/Redis credentials |
| `crucible-red-team.env.example` | CRUCIBLE | evolution + worker config |

## Production values (reference — see `deployment/DEPLOY.md`)

**Railway (backend):**
```
DEBUG=false
LOG_LEVEL=INFO
GRAPH_MAX_NODES=150
GRAPH_MAX_EDGES=600
ANOMALY_SCORE_THRESHOLD=0.65
ISOLATION_FOREST_CONTAMINATION=0.1
ALLOWED_ORIGINS=*
BLUE_TEAM_API_KEY=<rotate-me>        # do NOT ship the doc default
```
**Vercel (frontend):**
```
VITE_API_URL=https://transaction-graph-engine-production.up.railway.app
```

## Security note

`ALLOWED_ORIGINS=*` requires `allow_credentials=False` (Starlette silently drops the CORS
header otherwise). `BLUE_TEAM_API_KEY` must be rotated and moved to a secret manager — see
`../docs/production_readiness_report.md` §2.
