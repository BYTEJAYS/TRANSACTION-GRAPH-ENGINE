"""
Case repository — the only code that reads/writes case storage.

Mode is chosen by TGIE_PERSIST:
  json (default) → delegates to the existing case_management.store (zero change)
  db             → Postgres `cases` (+ Neo4j :Case projection)

Routers/services call this; they never touch a store directly.
"""
from __future__ import annotations

from typing import Any, Optional

from core.settings import data_settings
from migrations.transforms import case_to_record, record_to_case


# ── reads ────────────────────────────────────────────────────────────────────
async def get_case(case_id: str) -> Optional[dict[str, Any]]:
    if not data_settings.db_mode:
        from case_management.store import store
        return store.get(case_id)
    from sqlalchemy import text  # type: ignore
    from core.db import postgres
    async with postgres.session_factory()() as s:
        row = (await s.execute(
            text("SELECT payload FROM cases WHERE case_id = :id"), {"id": case_id}
        )).first()
    return record_to_case({"payload": row[0]}) if row else None


async def list_cases(limit: int, offset: int, status: Optional[str] = None) -> list[dict]:
    if not data_settings.db_mode:
        from case_management.store import store
        cases = store.all()
        if status:
            cases = [c for c in cases if c.get("status") == status]
        return cases[offset:offset + limit]
    from sqlalchemy import text  # type: ignore
    from core.db import postgres
    q = "SELECT payload FROM cases"
    params: dict = {"lim": limit, "off": offset}
    if status:
        q += " WHERE status = :status"; params["status"] = status
    q += " ORDER BY created_at DESC LIMIT :lim OFFSET :off"
    async with postgres.session_factory()() as s:
        rows = (await s.execute(text(q), params)).all()
    return [record_to_case({"payload": r[0]}) for r in rows]


# ── writes / migration ─────────────────────────────────────────────────────────
async def upsert_cases(cases: dict[str, dict]) -> int:
    from sqlalchemy import text  # type: ignore
    from core.db import postgres
    cols = ["case_id", "title", "category", "status", "priority", "risk_score",
            "fraud_confidence", "assigned_to", "department", "created_at",
            "updated_at", "due_date", "primary_account", "source", "payload"]
    placeholders = ", ".join(f":{c}" for c in cols)
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "case_id")
    sql = text(
        f"INSERT INTO cases ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT (case_id) DO UPDATE SET {updates}"
    )
    n = 0
    async with postgres.session_factory()() as s:
        for case in cases.values():
            rec = case_to_record(case)
            import json as _json
            rec["payload"] = _json.dumps(rec["payload"])  # JSONB bind
            await s.execute(sql, rec)
            n += 1
        await s.commit()
    return n


def project_cases_to_graph(cases: dict[str, dict]) -> None:
    """MERGE a lightweight :Case node + PART_OF_CASE edges to involved accounts.
    Best-effort; the workflow record stays the Postgres row."""
    from core.db import neo4j
    c = neo4j.client()
    for case in cases.values():
        c.write(
            "MERGE (k:Case {case_no:$cid}) "
            "SET k.title=$title, k.status=$status, k.priority=$priority, "
            "    k.risk_score=$risk, k.owner=$owner",
            {"cid": case.get("case_id"), "title": case.get("title"),
             "status": case.get("status"), "priority": case.get("priority"),
             "risk": case.get("risk_score"), "owner": case.get("assigned_to")},
        )
        for acct in (case.get("accounts") or [])[:50]:
            acct_id = acct.get("account_id") if isinstance(acct, dict) else acct
            if acct_id:
                c.write(
                    "MERGE (a:Account {id:$aid}) "
                    "WITH a MATCH (k:Case {case_no:$cid}) "
                    "MERGE (a)-[:PART_OF_CASE]->(k)",
                    {"aid": acct_id, "cid": case.get("case_id")},
                )
