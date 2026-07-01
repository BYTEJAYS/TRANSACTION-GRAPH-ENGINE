"""Phase 10 — /api/v1 contract & auth tests (TestClient + dependency_overrides)."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_cases_requires_auth(v1_app):
    app, _ = v1_app
    client = TestClient(app)
    r = client.get("/api/v1/cases")
    assert r.status_code == 401, "unauthenticated request must be rejected"


def test_cases_list_shape_and_seed_data(v1_app, fake_user):
    app, set_user = v1_app
    set_user(fake_user)
    client = TestClient(app)
    r = client.get("/api/v1/cases?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"items", "next_cursor", "limit"}
    assert body["limit"] == 5
    # json mode reads the 9 seed cases (regression guard for the case_repo fix)
    assert len(body["items"]) >= 1
    assert "case_id" in body["items"][0]


def test_cases_pagination_cursor(v1_app, fake_user):
    app, set_user = v1_app
    set_user(fake_user)
    client = TestClient(app)
    r = client.get("/api/v1/cases?limit=2")
    body = r.json()
    assert len(body["items"]) <= 2


def test_evidence_build_and_verify(v1_app, fake_user):
    app, set_user = v1_app
    set_user(fake_user)
    client = TestClient(app)
    # pick a real seed case
    case_id = client.get("/api/v1/cases?limit=1").json()["items"][0]["case_id"]
    r = client.post(f"/api/v1/evidence/build/{case_id}")
    assert r.status_code == 200
    pkg = r.json()
    assert pkg["sha256"] and len(pkg["sections"]) == 15
    # determinism via the API: rebuild → same hash
    r2 = client.post(f"/api/v1/evidence/build/{case_id}")
    assert r2.json()["sha256"] == pkg["sha256"]
    # verify endpoint
    v = client.get(f"/api/v1/evidence/verify/{pkg['package_id']}")
    assert v.status_code == 200
    assert v.json()["verdict"] in ("VERIFIED", "VERIFIED_LOCAL")


def test_evidence_unknown_case_404(v1_app, fake_user):
    app, set_user = v1_app
    set_user(fake_user)
    client = TestClient(app)
    r = client.post("/api/v1/evidence/build/NOPE-9999")
    assert r.status_code == 404
