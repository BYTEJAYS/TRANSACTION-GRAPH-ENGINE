"""
Postgres access (SQLAlchemy 2.0 async) with graceful degradation.

If `sqlalchemy`/`psycopg` aren't installed or the server is down, `available()`
returns False and callers fall back to the JSON store — so the app boots and
serves traffic without Docker.
"""
from __future__ import annotations

import logging
from typing import Optional

from core.settings import data_settings

log = logging.getLogger(__name__)

try:
    from sqlalchemy.ext.asyncio import (  # type: ignore
        AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine,
    )
    from sqlalchemy import text  # type: ignore
    _HAS_SA = True
except Exception:
    _HAS_SA = False

_engine: "Optional[AsyncEngine]" = None
_sessionmaker = None


def _get_engine():
    global _engine, _sessionmaker
    if not _HAS_SA:
        raise RuntimeError("sqlalchemy[asyncio]+psycopg not installed")
    if _engine is None:
        _engine = create_async_engine(data_settings.postgres_dsn, pool_size=10, pool_pre_ping=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine


def session_factory():
    _get_engine()
    return _sessionmaker


async def available() -> bool:
    """True if SA installed AND Postgres answers SELECT 1. Never raises."""
    if not _HAS_SA:
        return False
    try:
        async with _get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        log.debug("Postgres not available: %s", exc)
        return False


async def close() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
