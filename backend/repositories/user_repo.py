"""
User repository. json mode delegates to auth.store; db mode → Postgres `users`.
Password hashes are migrated VERBATIM — never re-hashed.
"""
from __future__ import annotations

from typing import Any, Optional

from core.settings import data_settings
from migrations.transforms import user_to_record, record_to_user


async def get_user_by_employee(employee_id: str) -> Optional[dict[str, Any]]:
    if not data_settings.db_mode:
        # In json mode the auth module owns its own directory (auth.store, keyed by
        # investigator_id, no employee_id index). This repo is the db-mode path; the
        # live auth flow reads auth.store directly, so json mode is a no-op here.
        return None
    from sqlalchemy import text  # type: ignore
    from core.db import postgres
    async with postgres.session_factory()() as s:
        row = (await s.execute(
            text("SELECT extra FROM users WHERE employee_id = :e"), {"e": employee_id}
        )).first()
    return record_to_user({"extra": row[0]}) if row else None


async def upsert_users(users: list[dict]) -> int:
    from sqlalchemy import text  # type: ignore
    from core.db import postgres
    import json as _json
    cols = ["investigator_id", "name", "employee_id", "department", "role",
            "branch", "email", "password_hash", "created_at", "extra"]
    placeholders = ", ".join(f":{c}" for c in cols)
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "investigator_id")
    sql = text(
        f"INSERT INTO users ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT (investigator_id) DO UPDATE SET {updates}"
    )
    n = 0
    async with postgres.session_factory()() as s:
        for u in users:
            rec = user_to_record(u)
            rec["extra"] = _json.dumps(rec["extra"])
            await s.execute(sql, rec)
            n += 1
        await s.commit()
    return n
