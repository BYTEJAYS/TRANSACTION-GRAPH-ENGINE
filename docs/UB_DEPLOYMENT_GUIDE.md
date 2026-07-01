# UB Deployment Guide

UB runs entirely locally on macOS (Apple Silicon). Three things must be up: **Ollama**,
the **knowledge index**, and the **UB service**.

## 0. Prerequisites

- Ollama installed (`~/.local/bin/ollama` or via `brew install ollama` / ollama.com).
- A Python with `numpy` + `fastapi` + `uvicorn`. On this machine the working interpreter is
  the original repo venv:
  `/Users/bytejay/transaction-graph-intelligence/backend/.venv/bin/python`
  (the local Python 3.14 can't build `scipy`; see docs/production_readiness_report.md).
  UB itself only needs `numpy` + stdlib; the FastAPI service needs `fastapi`/`uvicorn`.

## 1. Start Ollama + ensure models

```bash
ub/scripts/start_ollama.sh      # starts server on :11434, pulls llama3.1:8b + nomic-embed-text
```
Keep `ollama serve` running in its own terminal/window (background `&`/nohup processes get
reaped when their launching shell exits — run it as a foreground process you leave open).

## 2. Build the knowledge index

```bash
cd /Users/bytejay/Desktop/TGIE
python -m ub index              # regenerates summaries + embeds the whole workspace (~minutes)
python -m ub status             # confirm: ollama up, index ready, chunk/file counts
```

## 3. Run the UB service

**Option A — standalone (recommended for the dashboard):**
```bash
cd /Users/bytejay/Desktop/TGIE/backend
PYTHONPATH=. <python> -m ub_service        # uvicorn on :8000, routes under /ub/*
```

**Option B — mounted on the TGIE core backend:** add to `backend/main.py`:
```python
from ub_service import ub_router
app.include_router(ub_router)
```
Then UB shares the existing `:8000` server alongside the fraud-detection API.

## 4. Open the dashboard

Open `frontend/ub_dashboard/index.html` directly in a browser, or serve it. It calls
`http://localhost:8000/ub/*`. When the TGIE frontend runs on `:3000`, the dashboard auto-
targets `:8000`.

## 5. Verify

```bash
curl -s localhost:8000/ub/health
curl -s -X POST localhost:8000/ub/chat -H 'Content-Type: application/json' \
  -d '{"message":"What is TGIE?","mode":"presentation"}'
```

## 6. Keep it fresh (self-updating)

```bash
ub/scripts/watch.sh             # re-indexes whenever the codebase changes
```
or rely on `UBBrain(auto_refresh=True)` / `POST /ub/reindex`.

## Environment variables

| Var | Default | Purpose |
|---|---|---|
| `UB_MODEL` | `llama3.1:8b` | primary chat model |
| `UB_FAST_MODEL` | `llama3.2:3b` | fast fallback |
| `UB_EMBED_MODEL` | `nomic-embed-text` | embeddings |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint |
| `UB_PORT` | `8000` | standalone service port |

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Could not reach Ollama` | `ub/scripts/start_ollama.sh`; check `:11434`. |
| `/ub/*` 503 | Ollama down or model not pulled. |
| Answers ignore the code | Index not built — run `python -m ub index`. |
| Embedding HTTP 500 on a chunk | Handled — oversized chunks are truncated/skipped during build. |
| Slow first answer | Cold model load (one-time); subsequent calls are fast. |
