"""
Cache layer — Redis when reachable, bounded in-process TTL/LRU fallback otherwise.

So caching works (and is testable) without Docker, then transparently uses Redis
in prod. Keys carry a version tag (detector/model version) so a deploy invalidates
stale entries. Synchronous API — safe to call from detectors and (via run_cpu)
from async routes.
"""
from __future__ import annotations

import json
import time
import threading
from collections import OrderedDict
from typing import Any, Callable, Optional

# Try a SYNC redis client; absent → in-process fallback (graceful, like everything else).
try:
    import redis as _redis  # type: ignore
    _HAS_REDIS = True
except Exception:
    _HAS_REDIS = False


class _LRUTTL:
    def __init__(self, maxsize: int = 4096):
        self.maxsize = maxsize
        self._d: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._d.get(key)
            if item is None:
                return None
            expires, val = item
            if expires and expires < time.time():
                self._d.pop(key, None)
                return None
            self._d.move_to_end(key)
            return val

    def set(self, key: str, val: Any, ttl: float) -> None:
        with self._lock:
            self._d[key] = (time.time() + ttl if ttl else 0, val)
            self._d.move_to_end(key)
            while len(self._d) > self.maxsize:
                self._d.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._d.clear()


_local = _LRUTTL()
_redis_client = None


def _get_redis():
    global _redis_client
    if not _HAS_REDIS:
        return None
    if _redis_client is None:
        import os
        try:
            _redis_client = _redis.Redis.from_url(
                os.getenv("TGIE_REDIS_URL", "redis://localhost:6380/0"),
                decode_responses=True, socket_connect_timeout=0.3)
            _redis_client.ping()
        except Exception:
            _redis_client = None
    return _redis_client


def backend() -> str:
    return "redis" if _get_redis() is not None else "local"


def make_key(*parts: Any, version: str = "v1") -> str:
    return f"tgie:{version}:" + ":".join(str(p) for p in parts)


def get(key: str) -> Optional[Any]:
    r = _get_redis()
    if r is not None:
        try:
            raw = r.get(key)
            return json.loads(raw) if raw is not None else None
        except Exception:
            pass
    return _local.get(key)


def set(key: str, val: Any, ttl: float = 300) -> None:
    r = _get_redis()
    if r is not None:
        try:
            r.set(key, json.dumps(val, default=str), ex=int(ttl) or None)
            return
        except Exception:
            pass
    _local.set(key, val, ttl)


def cached(ttl: float = 300, version: str = "v1", key_fn: Optional[Callable[..., str]] = None):
    """Memoize a pure function. key_fn(*args,**kwargs)->str builds the cache key
    (defaults to the positional args)."""
    def deco(fn: Callable):
        def wrapper(*args, **kwargs):
            k = make_key(fn.__name__, key_fn(*args, **kwargs) if key_fn else args, version=version)
            hit = get(k)
            if hit is not None:
                return hit
            val = fn(*args, **kwargs)
            set(k, val, ttl)
            return val
        wrapper.__name__ = getattr(fn, "__name__", "cached")
        return wrapper
    return deco


def clear_local() -> None:
    _local.clear()
