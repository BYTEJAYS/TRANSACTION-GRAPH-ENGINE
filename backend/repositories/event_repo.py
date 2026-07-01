"""
Transaction event store — append-only log that enables timeline replay.

db mode: INSERT into Postgres `txn_events` + XADD to a Redis stream (live fan-out).
json mode: no-op persistence (the in-memory deque in main.py remains the log),
so behaviour is unchanged until the DB is switched on.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from core.settings import data_settings

_STREAM = "tgie:txn"


async def append(event: dict[str, Any]) -> str:
    event_id = event.get("event_id") or f"EVT-{uuid.uuid4().hex[:14]}"
    ts = event.get("ts") or datetime.utcnow().isoformat()
    if not data_settings.db_mode:
        return event_id  # legacy in-memory path owns the log

    import json as _json
    from sqlalchemy import text  # type: ignore
    from core.db import postgres, redis
    async with postgres.session_factory()() as s:
        await s.execute(
            text("INSERT INTO txn_events (event_id, ts, payload) "
                 "VALUES (:eid, :ts, :payload) ON CONFLICT (event_id) DO NOTHING"),
            {"eid": event_id, "ts": ts, "payload": _json.dumps(event)},
        )
        await s.commit()
    rc = redis.client()
    if rc is not None:
        await rc.xadd(_STREAM, {"event_id": event_id, "payload": _json.dumps(event)})
    return event_id


async def replay(start_ts: str, end_ts: str, limit: int = 1000) -> list[dict]:
    """Re-read events in a time window — the basis for Fund Journey / timeline replay."""
    if not data_settings.db_mode:
        return []
    from sqlalchemy import text  # type: ignore
    from core.db import postgres
    async with postgres.session_factory()() as s:
        rows = (await s.execute(
            text("SELECT payload FROM txn_events WHERE ts BETWEEN :a AND :b "
                 "ORDER BY seq ASC LIMIT :lim"),
            {"a": start_ts, "b": end_ts, "lim": limit},
        )).all()
    return [r[0] for r in rows]
