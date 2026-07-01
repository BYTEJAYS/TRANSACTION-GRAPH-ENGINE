# TGIE — Deployment Guide

Frontend → **Vercel** | Backend → **Railway**

---

## Architecture Overview

```
┌─────────────────────────┐        WSS / HTTPS        ┌──────────────────────────┐
│   Vercel (Frontend)     │ ◄────────────────────────► │   Railway (Backend)      │
│   React + Three.js      │                            │   FastAPI + uvicorn      │
│   Static site deploy    │                            │   1 worker, 512MB RAM    │
└─────────────────────────┘                            └──────────────────────────┘
         │                                                        │
  Falls back to                                         Optional: Supabase
  mock demo mode                                        PostgreSQL (free tier)
  if backend offline
```

**Key design decisions:**
- Frontend is a pure static site — never crashes
- Backend does inference + WebSocket only, no heavy infrastructure
- If backend is unreachable, frontend auto-switches to animated mock demo mode after 5 retries
- Kafka, Flink server, GNN (PyTorch Geometric), and live retraining are all removed from production

---

## Step 1 — Deploy Backend on Railway

### 1.1 Create Railway project

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
2. Select your TGIE repository
3. In **Settings → Source** set **Root Directory** to: `backend`
4. Railway will auto-detect Python via `requirements.txt` and use `railway.toml` for the start command

### 1.2 Set environment variables in Railway

Go to your service → **Variables** tab and add:

```
DEBUG=false
LOG_LEVEL=INFO
ALLOWED_ORIGINS=https://YOUR-APP.vercel.app
GRAPH_MAX_NODES=150
GRAPH_MAX_EDGES=600
ANOMALY_SCORE_THRESHOLD=0.65
ISOLATION_FOREST_CONTAMINATION=0.1
BLUE_TEAM_URL=https://YOUR-BLUE-TEAM.up.railway.app
BLUE_TEAM_API_KEY=your-secret-key-here
```

> `PORT` is injected automatically by Railway — do not set it manually.

### 1.3 Verify the deploy

Once deployed, open:
```
https://YOUR-BACKEND.up.railway.app/health
```

Expected response:
```json
{
  "status": "operational",
  "components": {
    "graph_engine": "online",
    "anomaly_detector": "online",
    "simulator": "manual-mode",
    "kafka": "fallback-queue",
    "ws_connections": 0
  }
}
```

### 1.4 Copy your Railway backend URL

It will look like: `https://tgie-backend-production.up.railway.app`

---

## Step 2 — Deploy Frontend on Vercel

### 2.1 Import project

1. Go to [vercel.com](https://vercel.com) → New Project → Import from GitHub
2. Select your TGIE repository
3. Set **Root Directory** to: `frontend`
4. Framework: **Vite** (auto-detected)

### 2.2 Set environment variables in Vercel

Go to **Settings → Environment Variables** and add:

```
VITE_API_URL=https://YOUR-BACKEND.up.railway.app
```

Optionally:
```
VITE_ELEVENLABS_API_KEY=your_key_here
VITE_ELEVENLABS_VOICE_ID=pNInz6obpgDQGcFmaJgB
```

### 2.3 Deploy

Click **Deploy**. Vercel runs `npm run build` automatically.

### 2.4 Update Railway CORS

Go back to Railway → Variables and update:
```
ALLOWED_ORIGINS=https://YOUR-APP.vercel.app
```

Redeploy the Railway service for the change to take effect.

---

## Step 3 — Verify End-to-End

1. Open your Vercel URL
2. The status bar should show **CONNECTED** once WebSocket connects to Railway
3. Use the Transaction Input Panel to submit a chain — graph should animate in real time
4. If backend is unreachable, the frontend falls back to **Demo Mode** (animated mock graph)

---

## Common Failure Fixes

### Backend crashes on Railway startup

**Symptom:** Deploy log shows OOM or timeout during startup.

**Fix:**
1. Check that `GRAPH_MAX_NODES=150` is set (not the old 500)
2. Ensure `.python-version` file exists with `3.11` (not 3.14)
3. Check Railway logs: `railway logs --tail`

### WebSocket connection fails (frontend shows disconnected)

**Symptom:** Status bar stays red, no graph data.

**Cause:** `ALLOWED_ORIGINS` on Railway doesn't include your Vercel URL.

**Fix:** Set `ALLOWED_ORIGINS=https://your-app.vercel.app` in Railway variables and redeploy.

### CORS errors in browser console

**Symptom:** `Access-Control-Allow-Origin` missing on API responses.

**Fix:** Same as above — update `ALLOWED_ORIGINS` on Railway to exactly match your Vercel domain (no trailing slash).

### Frontend shows 404 on page refresh

**Symptom:** Refreshing any route other than `/` gives a 404.

**Fix:** `vercel.json` already has the SPA rewrite rule. If it's still broken, confirm the file exists in `frontend/vercel.json` and redeploy.

### Build fails — chunk too large warning

**Symptom:** Vite build warns about large chunks.

**This is a warning, not an error.** `chunkSizeWarningLimit: 2000` in `vite.config.ts` silences it. Three.js is inherently large. The `manualChunks` config ensures they load lazily.

### Blue Team verdicts show "offline"

**Symptom:** After simulation, Blue Team panel shows offline status.

**Expected behavior** — Blue Team is a separate optional service (`bling-blue-team`). The main TGIE app degrades gracefully and still shows full graph analysis and fraud detection. Deploy Blue Team separately on Railway if needed.

---

## Resource Budget (Railway Free Tier: 512MB RAM, shared CPU)

| Component              | Approx. RAM |
|------------------------|-------------|
| Python + FastAPI base  | ~80MB       |
| networkx graph (150 nodes) | ~20MB  |
| IsolationForest model  | ~30MB       |
| Flink stream processor | ~10MB       |
| Buffer + history       | ~20MB       |
| **Total**              | **~160MB**  |

Leaves ~350MB headroom. Safe for Railway's free tier.

---

## Environment Variables Reference

### Backend (Railway)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ALLOWED_ORIGINS` | Yes | localhost | Comma-separated frontend URLs |
| `GRAPH_MAX_NODES` | No | 150 | Max nodes in graph |
| `GRAPH_MAX_EDGES` | No | 600 | Max edges in graph |
| `BLUE_TEAM_URL` | No | localhost:8001 | Blue Team service URL |
| `BLUE_TEAM_API_KEY` | No | changeme | Shared secret for Blue Team |
| `DEBUG` | No | false | Enable debug logging |

### Frontend (Vercel)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VITE_API_URL` | Yes | (empty) | Railway backend URL |
| `VITE_ELEVENLABS_API_KEY` | No | (empty) | Voice synthesis API key |
| `VITE_ELEVENLABS_VOICE_ID` | No | pNInz6... | ElevenLabs voice ID |

---

## Future Scaling Roadmap

When you're ready to move beyond free tier:

1. **Database**: Enable Supabase PostgreSQL and set `DATABASE_URL` — persist graph history and alerts
2. **Blue Team**: Deploy `bling-blue-team` as a second Railway service — enables multi-graph verdict overlays
3. **Worker upgrade**: Bump Railway to Starter plan ($5/mo) for dedicated RAM — increase `GRAPH_MAX_NODES=500`
4. **Redis**: Add Railway Redis addon for WS pub/sub if you need multi-instance scaling
5. **Custom domain**: Point your own domain at Vercel for the portfolio URL

The architecture is intentionally designed so each upgrade is additive — nothing needs to be rewritten.
