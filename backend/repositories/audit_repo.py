"""Audit repository — persists AuditEntry rows in db mode (called by core.security.audit)."""
from __future__ import annotations


async def write_audit(entry: dict) -> None:
    from sqlalchemy import text  # type: ignore
    from core.db import postgres
    async with postgres.session_factory()() as s:
        await s.execute(
            text("INSERT INTO audit_entries (id, actor, action, target_ref, ip, pii, ts) "
                 "VALUES (:id,:actor,:action,:target_ref,:ip,:pii,:ts) "
                 "ON CONFLICT (id) DO NOTHING"),
            entry,
        )
        await s.commit()
