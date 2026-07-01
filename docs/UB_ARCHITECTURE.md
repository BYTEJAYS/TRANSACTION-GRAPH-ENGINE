# UB Architecture

UB (Universal Brain) is the local AI cognitive layer of TGIE. It understands, explains,
and presents the entire project by running a local LLM over a Retrieval-Augmented
Generation (RAG) index of the actual codebase — no cloud, no fine-tuning, no data egress.

## 1. Layer diagram

```
  ┌───────────────────────────────────────────────────────────────┐
  │ CLIENTS                                                        │
  │  frontend/ub_dashboard (matte-black console)  ·  CLI (python -m ub)  ·  any TGIE component │
  └───────────────────────────────┬───────────────────────────────┘
                                   │ HTTP  (POST /ub/chat, /demo, /founder, …)
                                   ▼
  ┌───────────────────────────────────────────────────────────────┐
  │ FASTAPI  —  backend/ub_service/app.py   (ub_router, mountable)  │
  └───────────────────────────────┬───────────────────────────────┘
                                   ▼
  ┌───────────────────────────────────────────────────────────────┐
  │ UB AI CORE  —  ub/ai_core                                      │
  │   UBBrain (orchestrator) · modes (founder/developer/…) ·       │
  │   ConversationManager (session memory)                         │
  └───────────────┬───────────────────────────────┬───────────────┘
                  ▼                                 ▼
  ┌───────────────────────────────┐   ┌────────────────────────────┐
  │ KNOWLEDGE ENGINE              │   │ OLLAMA SERVICE             │
  │ ub/knowledge_engine           │   │ ub/ollama_service          │
  │  indexer → embeddings →       │   │  chat · embed · health ·   │
  │  VectorStore (numpy) ·        │   │  stream · model switch     │
  │  summarizer (5 JSONs)         │   └──────────────┬─────────────┘
  └───────────────┬───────────────┘                  ▼
                  ▼                          ┌────────────────────┐
       index/ (vectors.npy,                 │ OLLAMA  :11434     │
       chunks.jsonl, meta.json)             │  llama3.1:8b       │
                                            │  nomic-embed-text  │
                                            └────────────────────┘
```

## 2. Request lifecycle (one question)

1. Client `POST /ub/chat {message, mode, session_id}`.
2. `UBBrain.ask` selects the mode persona (`ai_core/modes.py`).
3. Knowledge Engine embeds the question (`nomic-embed-text`) and retrieves the top-k
   most-similar chunks from the local vector store (cosine).
4. The prompt is assembled: **mode system prompt + project summaries + retrieved chunks
   (with file paths) + recent conversation history + the user message.**
5. `OllamaClient.chat` generates with `llama3.1:8b` locally.
6. Response returned with the **source files** it drew from; the turn is saved to session memory.

## 3. Components

| Package | Responsibility |
|---|---|
| `ub/ollama_service` | Stdlib HTTP client for Ollama: chat, streaming chat, embeddings, health, benchmark, model switching. Zero third-party deps. |
| `ub/knowledge_engine` | `indexer` (scan+chunk the workspace), `engine` (embed+retrieve+staleness), `vector_store` (numpy cosine, persisted), `summarizer` (5 summary JSONs). |
| `ub/ai_core` | `modes` (6 personas + params), `conversation` (session memory), `ub_brain` (orchestrator + demo). |
| `backend/ub_service` | FastAPI router + standalone app exposing the `/ub/*` API. |
| `frontend/ub_dashboard` | Self-contained matte-black dashboard talking to `/ub/*`. |

## 4. Design decisions

- **RAG, not fine-tuning** — cheap, and always reflects the current code (the watcher
  re-indexes on change). Fine-tuning would go stale and cost GPU time.
- **Local-only** — Ollama runs the model on-device; the index is built from the local
  workspace. Nothing about the project or its data leaves the Mac.
- **Dependency-light vector store** — vectors in a NumPy array on disk + exact cosine.
  No external vector DB to run; trivially fast for a single project's ~3k chunks.
- **Modes as personas over one knowledge base** — the same grounded retrieval, reshaped
  for founder / developer / presentation / demo / judge audiences.
- **Mountable router** — UB attaches to the existing TGIE backend (`include_router`) so it
  shares the `:8000` surface, or runs standalone (`python -m ub_service`).

## 5. Models (see hardware_analysis.md + model_benchmark_report.md)

| Role | Model | Notes |
|---|---|---|
| Primary brain | `llama3.1:8b` | best quality that fits 16 GB; ~20 tok/s |
| Fast fallback | `llama3.2:3b` | ~47 tok/s; switch via `POST /ub/model` |
| Embeddings | `nomic-embed-text` | 768-dim, fast |
