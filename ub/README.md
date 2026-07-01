# UB — Universal Brain

> The local AI **cognitive layer** of TGIE. UB understands, explains, navigates, and
> presents the entire project — powered by a local LLM (Ollama / `llama3.1:8b`) over a RAG
> index of the actual codebase. No cloud, no fine-tuning, no data egress.
>
> *"Talking directly to the brain of TGIE."*

## Quick start

```bash
ub/scripts/start_ollama.sh                 # 1. Ollama + models (:11434)
cd /Users/bytejay/Desktop/TGIE
python -m ub index                         # 2. build the knowledge index (~minutes)
python -m ub ask "What is TGIE?" -m presentation   # 3. ask UB anything
python -m ub chat -m developer             #    …or an interactive REPL
python -m ub demo                          #    …or auto-present the whole project
```
Service + dashboard: see `docs/UB_DEPLOYMENT_GUIDE.md`.

## Layout

```
ub/
├── ollama_service/     Local LLM client (chat/embed/health/stream/switch) — stdlib only
├── knowledge_engine/   RAG: indexer · embeddings · numpy vector store · summarizer
│   └── index/          persisted vectors.npy + chunks.jsonl + meta.json (gitignored)
├── ai_core/            UBBrain orchestrator · 6 modes · conversation/session memory
├── data/               5 summary JSONs · judge_questions.json · sessions/
├── scripts/            start_ollama.sh · watch.sh (self-updating)
├── src/                reference snapshots of the in-frontend UB voice orb (see below)
├── cli.py / __main__   `python -m ub …`
└── README.md
```

The FastAPI surface lives at `backend/ub_service/` (`/ub/*`); the dashboard at
`frontend/ub_dashboard/`.

## Modes

| Mode | Audience | Style |
|---|---|---|
| `chat` | anyone | adaptive, cites files |
| `founder` | vision/story | visionary, grounded |
| `developer` | engineers | file-level, precise |
| `presentation` | investors/judges/recruiters | concise, polished |
| `demo` | hands-off tour | 9-section auto-present |
| `judge` | hard Q&A | direct + honest about limits |

## How it works (one line)

embed your question → retrieve top-k matching chunks from the local index → build a grounded
prompt (persona + summaries + retrieved code/docs + history) → generate locally with
`llama3.1:8b` → answer **with source-file citations**.

Full detail: `docs/UB_ARCHITECTURE.md`, `docs/UB_KNOWLEDGE_SYSTEM.md`,
`docs/UB_OPERATIONS_MANUAL.md`, `docs/UB_DEMO_GUIDE.md`, `docs/UB_DEPLOYMENT_GUIDE.md`.

## Relationship to the in-frontend voice orb

`ub/src/` holds reference snapshots of the **browser** UB (the call-driven voice orb in
`frontend/src/ai/ub.ts`, `hooks/useUB.ts`, `components/ai/UBOrb.tsx`). That orb is the
in-app voice companion that narrates fraud events. This `ub/` package is the broader
**cognitive layer / knowledge brain** — the two share the "UB" identity; the voice orb can
call the `/ub/*` service as its backend for richer, project-aware answers (Phase 14 voice
path: browser STT/TTS already exists in the frontend and remains fully local).
