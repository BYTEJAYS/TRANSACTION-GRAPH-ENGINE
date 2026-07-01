# UB Operations Manual

Day-to-day operation of the Universal Brain.

## Start everything

```bash
# 1. Ollama (leave running in its own window)
ub/scripts/start_ollama.sh

# 2. (first time / after code changes) build the index
cd /Users/bytejay/Desktop/TGIE && python -m ub index

# 3. UB service
cd backend && PYTHONPATH=. <python> -m ub_service     # :8000, /ub/*

# 4. (optional) keep it fresh
ub/scripts/watch.sh
```

`<python>` = an interpreter with numpy+fastapi (here:
`/Users/bytejay/transaction-graph-intelligence/backend/.venv/bin/python`).

## CLI reference

| Command | Does |
|---|---|
| `python -m ub status` | ollama health + index stats |
| `python -m ub index` | rebuild summaries + embeddings |
| `python -m ub summaries` | regenerate the 5 JSONs only |
| `python -m ub ask "Q" -m developer` | one-shot question in a mode |
| `python -m ub chat -m founder` | interactive REPL (`:mode X`, `:quit`) |
| `python -m ub demo` | auto-present TGIE |
| `python -m ub benchmark` | latency/throughput of installed chat models |

## API reference (`/ub/*`)

| Method · Route | Purpose |
|---|---|
| `POST /ub/chat` | `{message, mode, session_id}` → `{answer, sources, model}` |
| `POST /ub/chat/stream` | streaming tokens (text/plain) |
| `POST /ub/founder` · `/developer` · `/presentation` · `/judge` | mode shortcuts `{message, session_id}` |
| `POST /ub/demo` | full scripted demo |
| `GET /ub/health` | ollama up?, models, availability |
| `GET /ub/model` · `POST /ub/model {model}` | view / switch active chat model |
| `GET /ub/context` | knowledge stats + ollama health + modes |
| `GET /ub/modes` | mode list + demo outline |
| `GET /ub/sources?q=&k=` | retrieval sources for a query (no generation) |
| `POST /ub/reindex` | force a synchronous re-index |

## Health checks

```bash
python -m ub status                       # one-shot
curl -s localhost:8000/ub/health          # via the service
curl -s localhost:11434/api/version       # ollama itself
```

Green = `ollama.up: true`, `knowledge.ready: true`, `stale: false`.

## Monitoring (what to watch)

| Signal | Where | Healthy |
|---|---|---|
| Ollama reachable | `/ub/health` `.up` | true |
| Index built | `/ub/context` `.knowledge.ready` | true |
| Index fresh | `.knowledge.stale` | false |
| Active model | `/ub/model` | `llama3.1:8b` |
| Throughput | dashboard `tokens/s` | ~20 (8b) / ~47 (3b) |
| Memory | Activity Monitor / `ollama ps` | model fits, no swap storm |

## Common operations

- **Switch to the fast model:** `curl -X POST localhost:8000/ub/model -d '{"model":"llama3.2:3b"}' -H 'Content-Type: application/json'`
- **Pull an alternative brain:** `ollama pull qwen3` (or mistral/gemma) → `POST /ub/model`.
- **Reset a conversation:** start a new `session_id` (sessions persist in `ub/data/sessions/`).
- **Rebuild from scratch:** `rm -rf ub/knowledge_engine/index && python -m ub index`.

## Failure playbook

| Problem | Likely cause | Action |
|---|---|---|
| `/ub/*` returns 503 | Ollama down / model missing | `start_ollama.sh`; `ollama pull llama3.1:8b` |
| Answers ignore the codebase | no index | `python -m ub index` |
| Service won't import `ub` | wrong CWD/PYTHONPATH | run from `backend/` with `PYTHONPATH=.` (the app also self-adds the TGIE root) |
| `scipy` build error on local python | Python 3.14 | use the 3.11 venv interpreter for the service |
| Slow / swapping | two large models resident | keep one chat model; UB switches rather than co-loading |
| Ollama dies when launched in background | `&`/nohup reaped by shell exit | run `ollama serve` as a foreground process in its own window |

## Security posture

UB is **local-only**: the model runs on-device via Ollama and the index is built from the
local workspace. No transaction data or source code leaves the Mac. Intended for
localhost / trusted-network use; if exposed, put it behind the same auth as the TGIE backend
(see docs/production_readiness_report.md).
