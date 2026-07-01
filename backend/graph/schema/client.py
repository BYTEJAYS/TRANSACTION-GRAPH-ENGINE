"""
Neo4j client for the TGIE graph layer.

Adapted from the proven read-only client in blue_team/bling, extended to support
writes (the new Graph Engine owns writes) and — critically — **graceful
degradation**: if the `neo4j` driver isn't installed or the server is
unreachable, callers get a clear `available() == False` instead of a crash, so
the in-memory NetworkX path keeps working in dev/demo without Docker.

Config via env (see deployment/docker-compose.data.yml):
    TGIE_NEO4J_URI   (default bolt://localhost:7687)
    TGIE_NEO4J_USER  (default neo4j)
    TGIE_NEO4J_PASS  (default tgie-dev-password)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

log = logging.getLogger(__name__)

try:
    from neo4j import GraphDatabase, Driver  # type: ignore
    _HAS_DRIVER = True
except Exception:  # driver not installed yet — dev/demo path
    GraphDatabase = None  # type: ignore
    Driver = Any  # type: ignore
    _HAS_DRIVER = False


class Neo4jClient:
    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.uri = uri or os.getenv("TGIE_NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("TGIE_NEO4J_USER", "neo4j")
        self.password = password or os.getenv("TGIE_NEO4J_PASS", "tgie-dev-password")
        self._driver: Optional[Driver] = None

    # ── connection ──────────────────────────────────────────────────────────
    def available(self) -> bool:
        """True if the driver is installed AND the server answers. Never raises."""
        if not _HAS_DRIVER:
            return False
        try:
            self._connect().verify_connectivity()
            return True
        except Exception as exc:
            log.debug("Neo4j not available: %s", exc)
            return False

    def _connect(self) -> Driver:
        if self._driver is None:
            if not _HAS_DRIVER:
                raise RuntimeError("neo4j driver not installed (pip install neo4j)")
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                max_connection_pool_size=50,  # cap — avoids exhaustion under worker+API load
            )
        return self._driver

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    # ── queries (always parameterized — never f-strings into Cypher) ──────────
    def read(self, cypher: str, params: dict | None = None) -> list[dict]:
        with self._connect().session() as s:
            return [r.data() for r in s.run(cypher, **(params or {}))]

    def write(self, cypher: str, params: dict | None = None) -> list[dict]:
        with self._connect().session() as s:
            result = s.run(cypher, **(params or {}))
            return [r.data() for r in result]

    def run_script(self, statements: list[str]) -> int:
        """Run a list of DDL/DML statements in their own auto-commit txns.
        Returns the count that executed. Used by bootstrap for idempotent DDL."""
        n = 0
        with self._connect().session() as s:
            for stmt in statements:
                if stmt.strip():
                    s.run(stmt)
                    n += 1
        return n


_client: Optional[Neo4jClient] = None


def get_client() -> Neo4jClient:
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client
