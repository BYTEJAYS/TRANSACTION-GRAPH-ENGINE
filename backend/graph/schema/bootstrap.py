"""
Idempotent schema bootstrap.

    python -m graph.schema.bootstrap            # apply against Neo4j
    python -m graph.schema.bootstrap --dry-run  # parse + list statements, no connection

Reads constraints.cypher, splits on `;`, strips // comments, and applies each
statement (all are `IF NOT EXISTS`, so re-running is safe). If Neo4j is
unavailable it prints actionable guidance and exits 0 in --dry-run, else exits 2.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

_DDL = pathlib.Path(__file__).with_name("constraints.cypher")


def parse_statements(text: str) -> list[str]:
    # drop // line comments, then split on semicolons
    no_comments = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("//")
    )
    return [s.strip() for s in no_comments.split(";") if s.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    statements = parse_statements(_DDL.read_text())
    constraints = [s for s in statements if re.match(r"(?i)create constraint", s)]
    indexes = [s for s in statements if re.match(r"(?i)create (index|fulltext)", s)]
    print(f"Parsed {len(statements)} statements "
          f"({len(constraints)} constraints, {len(indexes)} indexes).")

    if args.dry_run:
        for s in statements:
            print("  •", s.split("\n")[0][:90])
        return 0

    from .client import get_client
    client = get_client()
    if not client.available():
        print(
            "\nNeo4j is not reachable. Start the data layer first:\n"
            "    docker compose -f deployment/docker-compose.data.yml up -d neo4j\n"
            "(Docker Desktop must be installed.) Re-run with --dry-run to validate "
            "the DDL without a server.",
            file=sys.stderr,
        )
        return 2

    applied = client.run_script(statements)
    print(f"Applied {applied} schema statements to {client.uri}.")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
