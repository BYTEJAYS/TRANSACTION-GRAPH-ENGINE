"""
Task abstraction — one code path, two runtimes.

`enqueue(name, *args)` runs the task INLINE (dev/demo, no broker) or hands it to
Celery when a broker is configured (TGIE_CELERY_BROKER). Heavy jobs register here
so the API can fire-and-forget precompute / projection / retrain without blocking.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable

log = logging.getLogger("tgie.tasks")

_REGISTRY: dict[str, Callable[..., Any]] = {}


def task(name: str):
    def deco(fn: Callable[..., Any]):
        _REGISTRY[name] = fn
        return fn
    return deco


def registered() -> list[str]:
    return sorted(_REGISTRY)


def _celery_enabled() -> bool:
    return bool(os.getenv("TGIE_CELERY_BROKER"))


def enqueue(name: str, *args: Any, **kwargs: Any) -> dict:
    """Run/queue a registered task. Returns {mode, result?} — inline returns the
    result; celery returns the task id."""
    fn = _REGISTRY.get(name)
    if fn is None:
        raise KeyError(f"unknown task '{name}' (registered: {registered()})")

    if _celery_enabled():
        try:
            from celery import Celery  # type: ignore
            app = Celery(broker=os.getenv("TGIE_CELERY_BROKER"))
            async_res = app.send_task(f"tgie.{name}", args=args, kwargs=kwargs)
            return {"mode": "celery", "task_id": getattr(async_res, "id", None)}
        except Exception as exc:  # broker set but unavailable → fall back to inline
            log.warning("celery enqueue failed (%s); running inline", exc)

    return {"mode": "inline", "result": fn(*args, **kwargs)}
