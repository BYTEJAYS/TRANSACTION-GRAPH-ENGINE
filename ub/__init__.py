"""
UB — Universal Brain · the local AI cognitive layer of the TGIE ecosystem.

Subpackages:
  ollama_service   — local LLM communication (Ollama)
  knowledge_engine — RAG over the whole TGIE workspace (index + retrieve + summaries)
  ai_core          — conversation memory, operating modes, and the UBBrain orchestrator
"""
__version__ = "1.0.0"

from .ai_core import UBBrain  # noqa: E402

__all__ = ["UBBrain", "__version__"]
