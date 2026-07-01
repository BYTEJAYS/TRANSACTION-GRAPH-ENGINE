"""
/api/v1 umbrella (Phase 3).

Versioned, auth-gated, paginated API. Mounted ALONGSIDE the legacy unversioned
routes (which stay live until the frontend cuts over in Phase 6). New resource
routers are added here incrementally; cases is the reference implementation.

A `/api/v1/health` reports live persistence-layer status so ops can see whether
Neo4j/Postgres/Redis are up and which persist mode is active.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from core.security.deps import current_user
from core.security import audit
from core.settings import data_settings

from . import cases as _cases
from . import evidence as _evidence

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(_cases.router)
api_v1.include_router(_evidence.router)


@api_v1.get("/health", tags=["meta"])
async def health():
    from core.db import postgres, redis, neo4j
    return {
        "status": "ok",
        "persist_mode": data_settings.persist,
        "stores": {
            "neo4j": neo4j.available(),
            "postgres": await postgres.available(),
            "redis": await redis.available(),
        },
    }


@api_v1.get("/audit/recent", tags=["meta"])
async def audit_recent(limit: int = 100, user: dict = Depends(current_user)):
    return {"items": audit.recent(limit)}


def mount(app) -> None:
    """Called from main.py to attach v1 without disturbing legacy routes."""
    app.include_router(api_v1)
