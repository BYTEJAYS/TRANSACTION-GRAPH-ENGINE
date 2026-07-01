"""
Pure, reversible transforms between the legacy JSON shapes and the relational
records. PURE functions (no I/O) so the round-trip invariant is unit-testable
without a database:

    record_to_case(case_to_record(c)) == c        # field-for-field
    record_to_user(user_to_record(u)) == u

Strategy: the FULL original object is stored verbatim in a `payload` JSONB
column (so a Postgres → JSON dump reproduces it exactly), and the queryable
fields are *also* copied into real indexed columns for fast filtering. The
reverse transform returns the payload untouched → round-trip is exact by
construction, regardless of which optional fields a given record happens to have.
"""
from __future__ import annotations

from typing import Any

# Fields denormalized into real, indexed Postgres columns (also kept in payload).
CASE_CORE = [
    "case_id", "title", "category", "status", "priority", "risk_score",
    "fraud_confidence", "assigned_to", "department", "created_at", "updated_at",
    "due_date", "primary_account", "source",
]

USER_CORE = [
    "investigator_id", "name", "employee_id", "department", "role", "branch",
    "email", "password_hash", "created_at",
]


def case_to_record(case: dict[str, Any]) -> dict[str, Any]:
    rec = {k: case.get(k) for k in CASE_CORE}
    rec["payload"] = dict(case)          # full verbatim copy → exact reversibility
    return rec


def record_to_case(rec: dict[str, Any]) -> dict[str, Any]:
    return dict(rec.get("payload") or {})


def user_to_record(user: dict[str, Any]) -> dict[str, Any]:
    rec = {k: user.get(k) for k in USER_CORE}
    rec["extra"] = dict(user)
    return rec


def record_to_user(rec: dict[str, Any]) -> dict[str, Any]:
    return dict(rec.get("extra") or {})
