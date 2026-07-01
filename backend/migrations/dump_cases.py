"""
Reverse migration — Postgres `cases` → the original cases.json shape.

    python -m migrations.dump_cases > /tmp/cases_dump.json

Proves the migration is reversible: the output is byte-equivalent (modulo key
order) to case_management/_data/cases.json. Lets us roll back to TGIE_PERSIST=json
at any time. Requires Postgres reachable.
"""
from __future__ import annotations

import asyncio
import json
import sys

from migrations.transforms import record_to_case


async def dump() -> dict:
    from sqlalchemy import text  # type: ignore
    from core.db import postgres
    if not await postgres.available():
        print("Postgres unreachable.", file=sys.stderr)
        raise SystemExit(2)
    async with postgres.session_factory()() as s:
        rows = (await s.execute(text("SELECT case_id, payload FROM cases"))).all()
    cases = {cid: record_to_case({"payload": payload}) for cid, payload in rows}
    return {"cases": cases, "seq": len(cases)}


if __name__ == "__main__":
    print(json.dumps(asyncio.run(dump()), indent=2, default=str))
