"""Phase 10 — migration reversibility as a pytest (wraps migrations.run)."""
from __future__ import annotations

from migrations.run import check_roundtrip, _load_cases, _load_users
from migrations.transforms import (
    case_to_record, record_to_case, user_to_record, record_to_user,
)


def test_cases_users_roundtrip_exact():
    # check_roundtrip prints + returns 0 on success, 1 on any failure
    assert check_roundtrip() == 0


def test_case_record_is_reversible():
    for case in _load_cases().values():
        assert record_to_case(case_to_record(case)) == case


def test_user_record_is_reversible():
    for user in _load_users():
        assert record_to_user(user_to_record(user)) == user
