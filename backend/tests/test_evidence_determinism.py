"""Phase 10 — evidence package determinism + completeness (unit level)."""
from __future__ import annotations

import pytest

from evidence import packager, anchor, fiu


def _a_case_id() -> str:
    from case_management.store import store
    cases = store.all()
    if not cases:
        pytest.skip("no seed cases")
    return cases[0]["case_id"]


def test_fifteen_sections():
    pkg = packager.build_package(_a_case_id(), actor="t")
    assert pkg is not None
    assert len(pkg["sections"]) == 15


def test_deterministic_hash_and_id():
    cid = _a_case_id()
    a = packager.build_package(cid, actor="alice")
    b = packager.build_package(cid, actor="bob")          # different actor must NOT change the hash
    assert a["integrity"]["sha256"] == b["integrity"]["sha256"]
    assert a["package_id"] == b["package_id"]


def test_verify_local_match():
    pkg = packager.build_package(_a_case_id(), actor="t")
    v = anchor.verify_package(pkg)
    assert v["local_match"] is True
    assert v["verdict"] in ("VERIFIED", "VERIFIED_LOCAL")


def test_tamper_detected():
    pkg = packager.build_package(_a_case_id(), actor="t")
    pkg["sections"]["8_reason"] = "TAMPERED CONTENT"      # mutate after hashing
    v = anchor.verify_package(pkg)
    assert v["local_match"] is False and v["verdict"] == "TAMPERED"


def test_fiu_str_fields():
    pkg = packager.build_package(_a_case_id(), actor="t")
    doc = fiu.build_str(pkg)
    for k in ("report_type", "regulator", "case_reference", "integrity"):
        assert k in doc
    assert doc["report_type"] == "STR"
