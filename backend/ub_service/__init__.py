"""
UB Service (Phase 12) — FastAPI surface for the Universal Brain.

Exposes UB to any TGIE component over HTTP:
  POST /ub/chat · /ub/demo · /ub/founder · /ub/developer · /ub/presentation · /ub/judge
  GET  /ub/health · /ub/model · /ub/context · /ub/sources
Mountable on the core backend (`app.include_router(ub_router)`) or run standalone.
"""
from .app import ub_router, create_app, get_brain

__all__ = ["ub_router", "create_app", "get_brain"]
