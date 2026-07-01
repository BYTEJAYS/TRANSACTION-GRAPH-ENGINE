# UB Hardware Analysis (Phase 1)

> Machine inspected 2026-06-24 to size UB's local LLM configuration.

## Detected hardware

| Property | Value |
|---|---|
| Model | MacBook Air (`Mac17,3`) |
| Chip | **Apple M5** |
| CPU cores | **10** (4 performance + 6 efficiency) |
| GPU cores | **8** (Metal 4) |
| Unified memory | **16 GB** |
| Neural Engine | Apple M5 16-core class (used by Metal/MLX-backed runtimes) |
| Storage free | **331 GB** of 460 GB |
| macOS | 26.4 (build 25E246) |

## What this means for local LLMs

Apple Silicon uses **unified memory** — the GPU and Neural Engine share the same 16 GB
as the CPU. Ollama runs models on the GPU via Metal, so the practical limit is
"model weights + KV cache + everything else macOS is doing" fitting inside 16 GB.

Rough working-set for common quantizations:

| Model | Params | Q4 weights | Fits 16 GB? | Notes |
|---|---|---|---|---|
| llama3.2:3b | 3B | ~2.0 GB | ✅ comfortably | very fast; lighter reasoning |
| **llama3.1:8b** | 8B | ~4.9 GB | ✅ **yes, with headroom** | best quality/size balance on this Mac |
| qwen / mistral 7-8B | 7-8B | ~4–5 GB | ✅ | viable alternatives |
| gemma2:9b | 9B | ~5.5 GB | ✅ (tighter) | viable |
| **llama3.3:70b** | 70B | ~40 GB | ❌ **no** | needs ~48 GB+ unified memory |

## Recommendation

| Role | Model | Why |
|---|---|---|
| **Primary brain** | **`llama3.1:8b`** | Best quality that fits 16 GB with headroom for the OS, Ollama KV cache, and the rest of the TGIE stack. `llama3.3` (70B) — the #1 preference — physically does not fit, so `llama3.1` (next in order) is the correct primary. |
| Fast fallback | `llama3.2:3b` | Sub-second first-token for quick lookups / low-memory situations; switch via `POST /ub/model`. |
| Embeddings | `nomic-embed-text` | 768-dim, ~274 MB, fast; powers the RAG index. |

**Memory budget while UB is active (primary brain):** ~5 GB model + ~1–2 GB KV cache
(8k context) ≈ **6–7 GB**, leaving ~9 GB for macOS, the TGIE backend, Vite, and Chrome.
Comfortable on this 16 GB M5. Keep only one chat model resident at a time (UB does — it
switches rather than co-loading), and avoid running the 8B model and a second large model
simultaneously.

**Context window:** UB requests `num_ctx=8192`, which is ample for RAG (retrieved chunks +
project summaries + recent turns) and well within memory on this machine. It can be raised
toward llama3.1's 128k ceiling, at higher memory/latency cost.

## Verdict

The M5 / 16 GB / 8-GPU-core configuration is a **strong local-inference machine** for an
8B-class assistant. UB is configured to use it optimally: `llama3.1:8b` as the brain,
`llama3.2:3b` as the fast fallback, and `nomic-embed-text` for retrieval — all local, no
cloud, no data egress.
