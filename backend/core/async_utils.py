"""
Offload CPU-bound work (NetworkX cycles/community/centrality/analysis) to a
threadpool so the FastAPI event loop never blocks — the fix for the Phase 1
"graph algorithms block the request thread" finding. I/O stays async; only
CPU-bound graph ops go through run_cpu.
"""
from __future__ import annotations

import asyncio
import functools
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

_EXEC = ThreadPoolExecutor(max_workers=int(os.getenv("TGIE_CPU_WORKERS", "4")),
                           thread_name_prefix="tgie-cpu")

T = TypeVar("T")


async def run_cpu(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_EXEC, functools.partial(fn, *args, **kwargs))
