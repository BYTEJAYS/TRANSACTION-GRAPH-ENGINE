"""
Ollama service layer for UB — the Universal Brain.

Pure-stdlib HTTP client for a LOCAL Ollama instance (default http://localhost:11434).
No third-party dependencies, so it runs under any Python 3.9+ on the Mac.

Responsibilities (Phase 13):
  * Ollama communication (chat / generate / embeddings)
  * Prompt management (system + multi-turn messages)
  * Context injection (retrieved knowledge passed as system context)
  * Health monitoring + model listing
  * Model switching
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

# Selected for Apple M5 / 16 GB unified memory (see docs/model_benchmark_report.md):
#   primary brain  = llama3.1:8b  (best quality that fits 16 GB; llama3.3 is 70B → won't fit)
#   fast fallback  = llama3.2:3b
#   embeddings     = nomic-embed-text (768-dim, tiny, fast)
DEFAULT_CHAT_MODEL = os.environ.get("UB_MODEL", "llama3.1:8b")
FAST_CHAT_MODEL = os.environ.get("UB_FAST_MODEL", "llama3.2:3b")
DEFAULT_EMBED_MODEL = os.environ.get("UB_EMBED_MODEL", "nomic-embed-text")
DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


class OllamaError(RuntimeError):
    """Raised when the local Ollama instance is unreachable or returns an error."""


def _normalize_host(host: str) -> str:
    if not host.startswith("http"):
        host = "http://" + host
    return host.rstrip("/")


@dataclass
class OllamaClient:
    host: str = DEFAULT_HOST
    model: str = DEFAULT_CHAT_MODEL
    embed_model: str = DEFAULT_EMBED_MODEL
    timeout: int = 120
    # request options forwarded to Ollama (temperature, num_ctx, etc.)
    options: Dict[str, Any] = field(default_factory=lambda: {"temperature": 0.3, "num_ctx": 8192})

    def __post_init__(self) -> None:
        self.host = _normalize_host(self.host)

    # ── low-level transport ────────────────────────────────────────────────
    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.host}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise OllamaError(
                f"Could not reach Ollama at {self.host} ({e}). "
                f"Start it with:  ollama serve   (or  ub/scripts/start_ollama.sh)"
            ) from e

    def _get(self, path: str) -> Dict[str, Any]:
        try:
            with urllib.request.urlopen(f"{self.host}{path}", timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise OllamaError(f"Could not reach Ollama at {self.host} ({e}).") from e

    # ── health / introspection ─────────────────────────────────────────────
    def health(self) -> Dict[str, Any]:
        """Return {'up': bool, 'version': str, 'models': [...]}. Never raises."""
        info: Dict[str, Any] = {"up": False, "host": self.host, "model": self.model,
                                "embed_model": self.embed_model, "version": None, "models": []}
        try:
            info["version"] = self._get("/api/version").get("version")
            info["models"] = [m["name"] for m in self._get("/api/tags").get("models", [])]
            info["up"] = True
            # Ollama treats "name" and "name:latest" as the same model — match loosely.
            bare = {m.split(":")[0] for m in info["models"]}
            info["model_available"] = self.model in info["models"] or self.model.split(":")[0] in bare
            info["embed_available"] = self.embed_model in info["models"] or self.embed_model.split(":")[0] in bare
        except OllamaError:
            pass
        return info

    def list_models(self) -> List[str]:
        return [m["name"] for m in self._get("/api/tags").get("models", [])]

    def switch_model(self, model: str) -> str:
        """Switch UB's active chat model. Returns the active model name."""
        self.model = model
        return self.model

    # ── inference ──────────────────────────────────────────────────────────
    def chat(self, messages: List[Dict[str, str]], *, model: Optional[str] = None,
             options: Optional[Dict[str, Any]] = None) -> str:
        """Multi-turn chat. messages = [{'role':'system|user|assistant','content':...}]."""
        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
            "options": {**self.options, **(options or {})},
        }
        out = self._post("/api/chat", payload)
        return out.get("message", {}).get("content", "").strip()

    def chat_stream(self, messages: List[Dict[str, str]], *, model: Optional[str] = None,
                    options: Optional[Dict[str, Any]] = None) -> Iterable[str]:
        """Yield response tokens as they arrive (used by the dashboard / CLI)."""
        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": True,
            "options": {**self.options, **(options or {})},
        }
        url = f"{self.host}/api/chat"
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for line in resp:
                    line = line.decode("utf-8").strip()
                    if not line:
                        continue
                    chunk = json.loads(line)
                    tok = chunk.get("message", {}).get("content", "")
                    if tok:
                        yield tok
                    if chunk.get("done"):
                        break
        except urllib.error.URLError as e:
            raise OllamaError(f"Stream failed against {self.host} ({e}).") from e

    def embed(self, text: str, *, model: Optional[str] = None) -> List[float]:
        """Embed a single string → vector (uses the embedding model)."""
        out = self._post("/api/embeddings", {"model": model or self.embed_model, "prompt": text})
        vec = out.get("embedding")
        if not vec:
            raise OllamaError(f"No embedding returned (is '{model or self.embed_model}' pulled?).")
        return vec

    def embed_batch(self, texts: List[str], *, model: Optional[str] = None) -> List[List[float]]:
        return [self.embed(t, model=model) for t in texts]

    def benchmark(self, prompt: str = "Explain transaction graph fraud detection in 2 sentences.",
                  *, model: Optional[str] = None) -> Dict[str, Any]:
        """Quick latency/throughput probe for one model (used by the benchmark report)."""
        m = model or self.model
        t0 = time.time()
        payload = {"model": m, "messages": [{"role": "user", "content": prompt}],
                   "stream": False, "options": self.options}
        out = self._post("/api/chat", payload)
        wall = time.time() - t0
        eval_count = out.get("eval_count", 0)
        eval_dur_s = out.get("eval_duration", 0) / 1e9 or wall
        return {
            "model": m,
            "wall_seconds": round(wall, 2),
            "tokens": eval_count,
            "tokens_per_sec": round(eval_count / eval_dur_s, 1) if eval_dur_s else None,
            "response_preview": out.get("message", {}).get("content", "")[:160],
        }


if __name__ == "__main__":  # smoke test:  python -m ub.ollama_service.client
    c = OllamaClient()
    print(json.dumps(c.health(), indent=2))
