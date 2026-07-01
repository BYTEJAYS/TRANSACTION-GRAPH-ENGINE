"""
Read/write audit trail — "who viewed/changed what".

Banking requirement: every access to PII or a case is recorded. Writes an
AuditEntry to Postgres (when in db mode) AND emits an :AuditEntry graph node so
the trail is reachable in the investigation graph. Degrades to an in-memory ring
buffer + log line when no DB is present, so auditing never blocks a request.
"""
from __future__ import annotations

import logging
import uuid
from collections import deque
from datetime import datetime
from typing import Optional

log = logging.getLogger("tgie.audit")

# transient fallback so the trail exists even without Postgres
_RING: deque = deque(maxlen=5000)


async def record(
    actor: str,
    action: str,
    target_ref: Optional[str] = None,
    ip: Optional[str] = None,
    pii: bool = False,
) -> dict:
    entry = {
        "id": f"AUD-{uuid.uuid4().hex[:12]}",
        "actor": actor,
        "action": action,
        "target_ref": target_ref,
        "ip": ip,
        "pii": pii,
        "ts": datetime.utcnow().isoformat(),
    }
    _RING.append(entry)
    # Always log PII reads at INFO so they surface even in fallback mode.
    (log.info if pii else log.debug)("audit %s %s %s", actor, action, target_ref)

    from core.settings import data_settings
    if data_settings.db_mode:
        try:
            from repositories.audit_repo import write_audit  # lazy import
            await write_audit(entry)
        except Exception as exc:  # auditing must never break the request
            log.warning("audit DB write failed (kept in ring buffer): %s", exc)
    return entry


def recent(n: int = 100) -> list[dict]:
    return list(_RING)[-n:]
