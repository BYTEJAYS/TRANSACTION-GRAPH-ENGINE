"""
Phase 3 migration runner.

    python -m migrations.run --check        # verify the round-trip invariant (NO DB needed)
    python -m migrations.run --all          # apply schema + m001 users + m002 cases + m003 graph

--check is what we can verify WITHOUT Docker: it loads the real JSON stores and
asserts record_to_X(X_to_record(obj)) == obj for every case and user. The DB
loaders run only when Postgres/Neo4j are reachable.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys

from migrations.transforms import (
    case_to_record, record_to_case, user_to_record, record_to_user,
)

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_CASES = _BACKEND / "case_management" / "_data" / "cases.json"
_USERS = _BACKEND / "auth" / "_data" / "investigators.json"


def _load_cases() -> dict:
    raw = json.loads(_CASES.read_text())
    return raw.get("cases", raw)


def _load_users() -> list:
    raw = json.loads(_USERS.read_text())
    return list(raw.values()) if isinstance(raw, dict) else raw


def check_roundtrip() -> int:
    cases = _load_cases()
    users = _load_users()
    failures = 0

    for cid, case in cases.items():
        if record_to_case(case_to_record(case)) != case:
            print(f"  ✗ case round-trip FAILED: {cid}", file=sys.stderr)
            failures += 1
    for u in users:
        if record_to_user(user_to_record(u)) != u:
            print(f"  ✗ user round-trip FAILED: {u.get('employee_id')}", file=sys.stderr)
            failures += 1

    if failures == 0:
        print(f"✓ round-trip exact for {len(cases)} cases and {len(users)} users "
              f"— migration is reversible, zero field loss.")
    return 1 if failures else 0


async def apply_all() -> int:
    from core.db import postgres, neo4j
    if not await postgres.available():
        print("Postgres unreachable — start deployment/docker-compose.data.yml first.",
              file=sys.stderr)
        return 2

    # 1) schema
    from sqlalchemy import text  # type: ignore
    ddl = (pathlib.Path(__file__).with_name("schema.sql")).read_text()
    async with postgres.session_factory()() as s:
        for stmt in [x for x in ddl.split(";") if x.strip()]:
            await s.execute(text(stmt))
        await s.commit()
    print("✓ Postgres schema applied")

    # 2) users  3) cases  (idempotent upserts)
    from repositories.user_repo import upsert_users
    from repositories.case_repo import upsert_cases
    n_u = await upsert_users(_load_users())
    n_c = await upsert_cases(_load_cases())
    print(f"✓ migrated {n_u} users, {n_c} cases into Postgres")

    # 4) graph projection of cases (best-effort if Neo4j up)
    if neo4j.available():
        from repositories.case_repo import project_cases_to_graph
        project_cases_to_graph(_load_cases())
        print("✓ projected :Case nodes into Neo4j")
    else:
        print("• Neo4j down — skipped graph projection (re-run when up)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if args.check or not args.all:
        return check_roundtrip()
    return asyncio.run(apply_all())


if __name__ == "__main__":
    raise SystemExit(main())
