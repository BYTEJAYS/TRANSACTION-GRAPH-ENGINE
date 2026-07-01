# UB Knowledge System

How UB knows the TGIE project: a local Retrieval-Augmented Generation (RAG) pipeline over
the entire workspace, plus auto-generated structured summaries.

## Pipeline

```
  workspace files ─▶ indexer (scan + chunk) ─▶ embeddings (nomic-embed-text)
        │                                              │
        ▼                                              ▼
   summarizer ─▶ 5 summary JSONs               VectorStore (vectors.npy + chunks.jsonl)
        │                                              │
        └────────────── injected into every prompt ◀───┘  (top-k cosine retrieval)
```

## 1. Indexing (`ub/knowledge_engine/indexer.py`)

- Walks the TGIE workspace, **skipping** `node_modules`, `.venv`, `.git`, `__pycache__`,
  build output, the index itself, `backups`, `logs`, and binaries.
- Indexes code (`.py/.ts/.tsx/.js`), docs (`.md`), config (`.json/.toml/.yml/.env`),
  scripts, and infra files (Dockerfile, railway/nixpacks).
- Splits each file into overlapping line windows (60 lines, 12 overlap) → **chunks**.
- Tags every chunk with **component** (Blue Team, Red Team, Frontend, UB, …), **kind**
  (python/typescript/documentation/config/…), path, and line range.
- Current index: **~711 files → ~3,950 chunks** (a few hundred oversized chunks are
  truncated/skipped at embed time).

## 2. Embeddings + vector store (`embeddings via ollama_service`, `vector_store.py`)

- Each chunk (prefixed with its component + path) is embedded locally with
  `nomic-embed-text` (768-dim).
- Vectors are L2-normalized and stored as a single NumPy array (`index/vectors.npy`);
  chunk metadata in `index/chunks.jsonl`; build info in `index/meta.json`.
- Retrieval = exact cosine (dot product of normalized vectors) — fast for ~3k chunks, with
  optional component filtering. Pure-Python fallback if NumPy is absent.

## 3. Retrieval + grounding (`engine.py`, `ai_core/ub_brain.py`)

- A question is embedded, top-k chunks retrieved, and assembled into the prompt with their
  **file paths** so UB can cite them.
- The two compact summaries (`project_summary.json`, `architecture_summary.json`) are
  injected into every prompt as always-on grounding.
- The mode persona instructs UB to answer from this context and cite real paths, never invent.

## 4. Automatic project understanding (`summarizer.py`, Phase 5)

Regenerated on every index build → `ub/data/`:

| File | Contents |
|---|---|
| `project_summary.json` | name, purpose, components, live URLs, live file counts |
| `architecture_summary.json` | services + ports, data flow, UB pipeline, invariants, modes |
| `module_summary.json` | per-top-level-dir role + key files |
| `dependency_summary.json` | parsed backend/bling requirements + frontend npm deps + UB runtime |
| `security_summary.json` | posture, readiness score, critical issues, UB's local-security stance |

## 5. Self-updating (Phase 11)

- The index stores a **manifest hash** of every indexed file's `mtime:size`.
- `KnowledgeEngine.is_stale()` compares the current workspace to that hash.
- `ub/scripts/watch.sh` (fswatch or 30s poll) re-runs `python -m ub index` on change;
  `POST /ub/reindex` does it on demand; `UBBrain(auto_refresh=True)` checks before each answer.
- Result: UB always reflects the latest state of TGIE.

## Operations

```bash
python -m ub index        # full (re)build: summaries + embeddings
python -m ub summaries    # regenerate the 5 JSONs only (fast, no embedding)
python -m ub status       # index readiness, counts, staleness, ollama health
python -m ub.knowledge_engine.indexer   # dry-run: see chunk/component counts
```

## Limits & notes

- Retrieval is the bottleneck on answer quality: if a fact isn't in a retrieved chunk, UB
  says so rather than inventing — cite-or-decline by design.
- Oversized/minified files contribute fewer chunks (truncated to 6,000 chars per chunk).
- The index is local and disposable — delete `ub/knowledge_engine/index/` and rebuild any time.
