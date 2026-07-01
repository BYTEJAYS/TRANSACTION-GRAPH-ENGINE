"""UB Knowledge Engine — RAG over the entire TGIE workspace (Phase 4 + 5 + 11)."""
from .engine import KnowledgeEngine
from .vector_store import VectorStore
from .summarizer import generate_all, DATA_DIR

__all__ = ["KnowledgeEngine", "VectorStore", "generate_all", "DATA_DIR"]
