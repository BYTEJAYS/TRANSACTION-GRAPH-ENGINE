"""
Data-layer settings (Phase 3).

Kept SEPARATE from the canonical app `config.Settings` so we add the persistence
layer without touching the file every module already imports. Reads env only;
sane localhost defaults that match deployment/docker-compose.data.yml.

The `persist` flag is the strangler-fig switch:
    TGIE_PERSIST=json  (default) → legacy JSON stores, zero behaviour change
    TGIE_PERSIST=db               → Postgres/Neo4j repositories
"""
from __future__ import annotations

import os
from functools import lru_cache


class DataSettings:
    def __init__(self) -> None:
        self.persist: str = os.getenv("TGIE_PERSIST", "json").lower()  # json | db

        self.neo4j_uri: str = os.getenv("TGIE_NEO4J_URI", "bolt://localhost:7687")
        self.neo4j_user: str = os.getenv("TGIE_NEO4J_USER", "neo4j")
        self.neo4j_pass: str = os.getenv("TGIE_NEO4J_PASS", "tgie-dev-password")

        # 5433 host port per the data compose (avoids clashing with local pg)
        self.postgres_dsn: str = os.getenv(
            "TGIE_POSTGRES_DSN",
            "postgresql+psycopg://tgie:tgie-dev-password@localhost:5433/tgie",
        )
        self.redis_url: str = os.getenv("TGIE_REDIS_URL", "redis://localhost:6380/0")

    @property
    def db_mode(self) -> bool:
        return self.persist == "db"


@lru_cache
def get_data_settings() -> DataSettings:
    return DataSettings()


data_settings = get_data_settings()
