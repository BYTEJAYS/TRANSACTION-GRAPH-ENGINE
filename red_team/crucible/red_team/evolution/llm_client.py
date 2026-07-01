from __future__ import annotations
"""
Local Ollama client for the CRUCIBLE Red Team brain.

Pure-stdlib HTTP client for a LOCAL Ollama instance (default http://localhost:11434),
self-contained so crucible has no cross-repo dependency. Used only by the Red Team
adversarial strategist — it never touches Blue Team.

Models (Apple-silicon friendly, already pulled on this box):
  reasoning brain = llama3.1:8b   (default; best quality that fits 16 GB)
  fast fallback   = llama3.2:3b
"""
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("CRUCIBLE_LLM_MODEL", "llama3.1:8b")
FAST_MODEL = os.environ.get("CRUCIBLE_LLM_FAST_MODEL", "llama3.2:3b")


class OllamaError(RuntimeError):
    """Local Ollama unreachable or returned an error."""


def _normalize_host(host: str) -> str:
    if not host.startswith("http"):
        host = "http://" + host
    return host.rstrip("/")


class OllamaClient:
    def __init__(self, host: str = DEFAULT_HOST, model: str = DEFAULT_MODEL,
                 timeout: int = 60) -> None:
        self.host = _normalize_host(host)
        self.model = model
        self.timeout = timeout

    # ── transport ──────────────────────────────────────────────────────────────
    def _post(self, path: str, payload: dict[str, Any], timeout: int | None = None) -> dict:
        req = urllib.request.Request(
            f"{self.host}{path}", data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise OllamaError(f"Ollama POST {path} failed against {self.host}: {e}") from e

    def _get(self, path: str, timeout: int = 5) -> dict:
        try:
            with urllib.request.urlopen(f"{self.host}{path}", timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise OllamaError(f"Ollama GET {path} failed against {self.host}: {e}") from e

    # ── health ─────────────────────────────────────────────────────────────────
    def health(self) -> dict:
        """{'up', 'model', 'model_available', 'models', 'version'} — never raises."""
        info = {"up": False, "host": self.host, "model": self.model,
                "model_available": False, "models": [], "version": None}
        try:
            info["version"] = self._get("/api/version").get("version")
            models = [m["name"] for m in self._get("/api/tags").get("models", [])]
            info["models"] = models
            info["up"] = True
            bare = {m.split(":")[0] for m in models}
            info["model_available"] = (self.model in models
                                       or self.model.split(":")[0] in bare)
        except OllamaError:
            pass
        return info

    # ── inference ──────────────────────────────────────────────────────────────
    def chat_json(self, system: str, user: str, *, model: str | None = None,
                  temperature: float = 0.4, num_ctx: int = 8192,
                  num_predict: int = 700, timeout: int | None = None) -> dict:
        """Single-shot chat constrained to JSON output. Returns the parsed object.

        Uses Ollama's `format:"json"` so the model is grammar-forced to emit valid
        JSON. Raises OllamaError on transport failure or unparseable output.
        """
        payload = {
            "model": model or self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature, "num_ctx": num_ctx,
                        "num_predict": num_predict},
        }
        t0 = time.time()
        out = self._post("/api/chat", payload, timeout=timeout)
        content = out.get("message", {}).get("content", "").strip()
        try:
            obj = json.loads(content)
        except json.JSONDecodeError as e:
            raise OllamaError(f"LLM did not return valid JSON: {e}") from e
        if not isinstance(obj, dict):
            raise OllamaError("LLM returned non-object JSON")
        obj["_latency_s"] = round(time.time() - t0, 2)
        return obj
