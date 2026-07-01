"""Tests for the gated Red Team → Blue Team learning loop (Phase 6 learning)."""
import pytest

from knowledge import xp_config
from knowledge.learning import propose_adaptations, apply_proposal, status
from knowledge.red_team import evaluate_blue_team


@pytest.fixture(autouse=True)
def _isolate_thresholds():
    """The loop mutates global thresholds — reset around every test so neither the
    rest of the suite nor sibling tests see leaked state."""
    xp_config.reset()
    yield
    xp_config.reset()


def test_baseline_misses_the_evasive_attack():
    st = status()
    assert st["battery_detected"] == st["battery_total"]      # baseline battery fully caught
    assert st["emerging_detected"] == 0                       # but the evasive attack slips through


def test_propose_stages_a_gated_proposal_without_applying():
    out = propose_adaptations()
    assert out["applied"] is False                            # propose never auto-applies
    assert out["learning_gate"] == "investigator_approval_required"
    assert out["proposal_count"] >= 1
    p = out["proposals"][0]
    assert p["threshold"] == "xp012_min_structured" and p["from"] == 4 and p["to"] == 3
    assert "Evasive Cross-Rail Structuring" in p["attacks_newly_caught"]
    assert p["false_positives"] == 0
    # thresholds unchanged by proposing
    assert xp_config.get("xp012_min_structured") == 4


def test_apply_closes_the_gap_and_stays_clean():
    out = propose_adaptations()
    p = out["proposals"][0]
    res = apply_proposal(p["threshold"], p["to"])
    assert res["applied"] is True
    assert res["emerging_now_detected"] == 1                  # evasive attack now caught
    ev = evaluate_blue_team()
    assert ev["attacks_fully_detected"] == ev["total_attacks"]  # battery still fully caught
    assert ev["clean_on_legitimate"] is True                   # no new false positives
    assert any(h.get("source") == "learning_loop" for h in xp_config.history())


def test_gate_blocks_reckless_relaxation_below_floor():
    res = apply_proposal("xp012_min_structured", 1)           # below safety floor (3)
    assert res["applied"] is False
    assert "floor" in res["reason"]
    assert xp_config.get("xp012_min_structured") == 4         # unchanged


def test_apply_rejects_unknown_threshold():
    assert apply_proposal("not_a_threshold", 2)["applied"] is False
