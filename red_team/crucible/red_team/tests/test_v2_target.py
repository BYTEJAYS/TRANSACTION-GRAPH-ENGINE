"""Tests for the CRUCIBLE → Blue Team V2 coupling (sandbox/v2_target.py).

Skips cleanly if the TGIE backend (blue_team_v2) is not reachable from this
checkout, so the suite still passes in a standalone crucible clone.
"""
import os

import pytest

from red_team.demo.seed_data import SEED_GENOMES
from red_team.sandbox.v2_target import V2BlueTeam, _resolve_backend_path

pytestmark = pytest.mark.skipif(
    _resolve_backend_path() is None,
    reason="blue_team_v2 backend not found (set CRUCIBLE_V2_BACKEND)",
)


@pytest.fixture(scope="module")
def v2():
    return V2BlueTeam()


def test_engine_loads(v2):
    assert v2.version and v2.version != "unknown"


def test_score_contract(v2):
    """score() returns the 4-element ensemble in [0, 1], like MockBlueTeam."""
    g = list(SEED_GENOMES)[0]
    scores = v2.score(g)
    assert isinstance(scores, list) and len(scores) == 4
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_score_action_bands(v2):
    assert v2.score_action([0.05, 0, 0, 0]) == "PASS"
    assert v2.score_action([0.50, 0, 0, 0]) == "LOG"
    assert v2.score_action([0.70, 0, 0, 0]) == "REVIEW"
    assert v2.score_action([0.90, 0, 0, 0]) == "HIGH_RISK"


def test_detects_fraud_seeds(v2):
    """V2 is the real, stronger target: fan-in mule seeds should not all slip."""
    flagged = 0
    for g in list(SEED_GENOMES)[:5]:
        scores = v2.score(g)
        if v2.score_action(scores) in ("REVIEW", "HIGH_RISK"):
            flagged += 1
    assert flagged >= 1


def test_fixtures_accepted_but_ignored(v2):
    """account_fixtures is accepted for drop-in parity but does not change scores."""
    g = list(SEED_GENOMES)[0]
    base = V2BlueTeam().score(g)
    withfix = V2BlueTeam(account_fixtures={"acc_deadbeef00": {"kyc_age": 90}}).score(g)
    assert base == withfix


def test_drop_in_via_get_blue_team(monkeypatch):
    """get_blue_team() returns V2BlueTeam when CRUCIBLE_BLUE_TEAM=v2."""
    from red_team.sandbox.blue_clone import get_blue_team

    monkeypatch.setenv("CRUCIBLE_BLUE_TEAM", "v2")
    bt = get_blue_team()
    assert type(bt).__name__ == "V2BlueTeam"
    # exposes the MockBlueTeam surface the rest of crucible depends on
    assert hasattr(bt, "score") and hasattr(bt, "score_action")
