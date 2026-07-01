"""Shared pytest fixtures for the TGIE backend suite."""
from __future__ import annotations

import pytest


@pytest.fixture
def v1_app():
    """A bare FastAPI app mounting only /api/v1 (no heavy lifespan), with
    current_user overridable per-test. Returns (app, set_user)."""
    from fastapi import FastAPI
    from api.v1 import api_v1
    from core.security.deps import current_user

    app = FastAPI()
    app.include_router(api_v1)

    def set_user(user: dict | None):
        if user is None:
            app.dependency_overrides.pop(current_user, None)
        else:
            app.dependency_overrides[current_user] = lambda: user

    return app, set_user


@pytest.fixture
def fake_user():
    return {"sub": "INV-TEST", "investigator_id": "INV-TEST",
            "role": "Senior Investigator", "employee_id": "EMP-TEST"}


@pytest.fixture
def sample_component():
    return {
        "graph_id": "G_TEST",
        "nodes": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        "edges": [
            {"source": "A", "target": "B", "amount": 250000, "payment_rail": "UPI",
             "timestamp": "2026-06-01T10:00:00"},
            {"source": "B", "target": "C", "amount": 240000, "payment_rail": "IMPS",
             "timestamp": "2026-06-01T10:05:00"},
        ],
    }
