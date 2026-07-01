"""UB Ollama Service Layer — local LLM communication for the TGIE cognitive layer."""
from .client import (
    OllamaClient, OllamaError,
    DEFAULT_CHAT_MODEL, FAST_CHAT_MODEL, DEFAULT_EMBED_MODEL, DEFAULT_HOST,
)

__all__ = ["OllamaClient", "OllamaError", "DEFAULT_CHAT_MODEL",
           "FAST_CHAT_MODEL", "DEFAULT_EMBED_MODEL", "DEFAULT_HOST"]
