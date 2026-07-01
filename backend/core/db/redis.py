"""
Redis access (cache + stream) with graceful degradation.

Used as: subgraph/search/risk cache, and the live transaction stream the WS
broadcaster + detectors consume. Absent Redis, callers skip caching and read
through to the source — correctness unaffected, just slower.
"""
from __future__ import annotations

import logging
from typing import Optional

from core.settings import data_settings

log = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis  # type: ignore
    _HAS_REDIS = True
except Exception:
    _HAS_REDIS = False

_client = None


def _get_client():
    global _client
    if not _HAS_REDIS:
        raise RuntimeError("redis not installed")
    if _client is None:
        _client = aioredis.from_url(data_settings.redis_url, decode_responses=True)
    return _client


async def available() -> bool:
    if not _HAS_REDIS:
        return False
    try:
        return bool(await _get_client().ping())
    except Exception as exc:
        log.debug("Redis not available: %s", exc)
        return False


def client():
    """Returns the client, or None if Redis is unavailable (caller skips cache)."""
    if not _HAS_REDIS:
        return None
    try:
        return _get_client()
    except Exception:
        return None


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
