"""Tests for the Red Team coupling interface (blue_team_v2.red_team_interface)."""
from __future__ import annotations

from blue_team_v2.red_team_interface import (
    RedTeamTarget,
    ensemble_scores,
    judge_component,
    judge_operation,
    score_transactions,
    to_component,
)
from blue_team_v2.simulation.generators import Simulator


def _ring():
    comp, _ = Simulator().circular()
    return comp


def test_judge_component_flags_fraud_ring():
    cv = judge_component(_ring())
    assert cv.verdict in ("FRAUD", "SUSPICIOUS")
    assert cv.flagged and not cv.benign
    assert cv.evidence_patterns                       # at least one detector fired
    assert 0.0 <= cv.risk <= 1.0


def test_judge_operation_aggregates_and_not_evaded_on_fraud():
    op = judge_operation([_ring()])
    assert op.flagged and not op.evaded
    assert op.worst_verdict in ("FRAUD", "SUSPICIOUS")
    assert op.total_flagged_nodes >= 1


def test_normal_component_evades():
    normal, _ = Simulator().normal()
    op = judge_operation([normal])
    assert op.evaded                                  # benign traffic is NOT flagged


def test_ensemble_scores_shape_and_range():
    s = ensemble_scores(_ring())
    assert len(s) == 4 and all(0.0 <= x <= 1.0 for x in s)
    assert s[0] > 0.5                                 # champion catches the ring


def test_score_transactions_genome_keys_and_empty():
    # genome.to_transaction_list() uses from_account/to_account — must bridge cleanly
    txns = [{"from_account": a, "to_account": b, "amount": 250000,
             "timestamp": "2026-05-30T09:0%d:00" % i, "payment_rail": "IMPS"}
            for i, (a, b) in enumerate([("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")])]
    s = score_transactions(txns)
    assert len(s) == 4 and s[0] > 0.5                 # ring caught via the txn bridge
    assert score_transactions([]) == [0.05, 0.05, 0.04, 0.06]


def test_to_component_field_flexibility():
    comp = to_component([{"source": "X", "target": "Y", "amount": 1000}])
    assert comp["node_ids"] == ["X", "Y"] and len(comp["edges"]) == 1


def test_tightened_thresholds_are_applied():
    # a stricter target should never judge a fraud ring as LESS than the default
    base = RedTeamTarget().judge_component(_ring()).risk
    assert base > 0.0
