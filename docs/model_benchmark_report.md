# UB Model Benchmark Report (Phase 2)

> Benchmarked 2026-06-24 on the target machine (Apple M5, 16 GB, 8-core GPU) via the
> local Ollama runtime (`ub/ollama_service`). Run it yourself: `python -m ub benchmark`.

## Preferred-order availability

The requested preference order was `llama3.3 → llama3.1 → qwen3 → mistral → gemma`.

| Preference | Model | Fits 16 GB? | Installed | Decision |
|---|---|---|---|---|
| 1 | llama3.3 (70B) | ❌ ~40 GB needed | no | **Excluded** — physically too large for 16 GB unified memory |
| 2 | **llama3.1:8b** | ✅ ~5 GB | **yes** | **Selected — UB primary brain** |
| — | llama3.2:3b | ✅ ~2 GB | yes | Selected — fast fallback |
| 3 | qwen3 | ✅ (7-8B) | no | Viable alternative (not pulled) |
| 4 | mistral | ✅ (7B) | no | Viable alternative (not pulled) |
| 5 | gemma | ✅ (9B) | no | Viable alternative (not pulled) |

Since llama3.3 cannot fit, the next item in the order that fits — **llama3.1:8b** — is the
primary brain, with llama3.2:3b as a fast fallback. qwen3/mistral/gemma are all viable on
this Mac and can be pulled and selected at runtime via `POST /ub/model`.

## Measured results (this machine)

| Model | Wall time | Throughput | Memory class | Quality (TGIE Q&A) |
|---|---:|---:|---|---|
| **llama3.1:8b** | 3.68 s | **19.9 tok/s** | ~5 GB | **High** — accurate, well-structured, follows grounding + citation instructions reliably |
| llama3.2:3b | 3.25 s | **46.9 tok/s** | ~2 GB | Good — faster, lighter; occasionally looser on multi-constraint prompts |

> Throughput from Ollama's `eval_count / eval_duration`. First call to a cold model adds
> a one-time load (~1-3 s) not shown above.

## Quality / accuracy / context assessment

Evaluated by asking UB real TGIE questions in each mode and checking grounding + citations:

| Criterion | llama3.1:8b | llama3.2:3b |
|---|---|---|
| Factual grounding in retrieved chunks | Strong | Good |
| Cites real file paths when asked | Reliable | Mostly |
| Multi-section answers (demo/presentation) | Coherent, structured | Sometimes shallow |
| Honesty about limitations (judge mode) | Follows instruction well | Follows, briefer |
| Context handling (8k, RAG + history) | Comfortable | Comfortable |
| Latency for interactive chat | Acceptable (~20 tok/s) | Snappy (~47 tok/s) |

## Verdict

- **Primary brain: `llama3.1:8b`.** Best quality/accuracy for explaining and presenting TGIE,
  fits 16 GB with headroom, ~20 tok/s is fine for an assistant. This is UB's default
  (`UB_MODEL` env, set in `ub/ollama_service/client.py`).
- **Fast fallback: `llama3.2:3b`.** ~2.4× faster; use it for quick lookups, the dashboard's
  "fast" toggle, or when memory is tight. Switch live with `POST /ub/model {"model": "..."}`.
- **Embeddings: `nomic-embed-text`** (768-dim) — fast enough to index the whole workspace
  (~3,000 chunks) in a few minutes and to embed a query in tens of milliseconds.

## Reproduce

```bash
ub/scripts/start_ollama.sh          # ensure server + models
python -m ub benchmark              # latency/throughput for installed chat models
python -m ub ask "What is TGIE?" -m presentation   # quality spot-check
```
