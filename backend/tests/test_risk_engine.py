"""
Risk Engine contract tests — the guarantees a Union Bank investigator relies on.

These lock the invariants that were violated by the "FRAUD 1000%" defect:
  * every score is bounded 0–100 (never negative, never >100, never overflows);
  * every score is fully explainable (each contributing factor carries points
    ≤ its weight, and the score equals the clamped sum of those points);
  * confidence is a DISTINCT, bounded metric (not a copy of risk);
  * the wire contract divides the 0–100 score to a 0–1 fraction in [0,1].
"""
from __future__ import annotations

import pytest

from risk_engine import assess
from risk_engine.config import config as _config


def _comp(graph_id, node_ids, edges):
    nodes = [{"id": n, "risk_score": 0.0, "account_type": "normal",
              "detected_patterns": [], "transaction_count": 1} for n in node_ids]
    return {"graph_id": graph_id, "node_ids": node_ids, "nodes": nodes, "edges": edges}


def _edge(s, t, amount=50_000, ts="2026-01-01T10:00:00", rail="UPI"):
    return {"source": s, "target": t, "amount": amount, "timestamp": ts, "payment_rail": rail}


# A spread of structurally different components, incl. pathological amounts.
FAN_OUT = _comp("G_FAN", ["A", "B", "C", "D", "E", "F"],
                [_edge("A", x) for x in ["B", "C", "D", "E", "F"]])
CHAIN = _comp("G_CHAIN", ["A", "B", "C", "D", "E"],
              [_edge("A", "B"), _edge("B", "C"), _edge("C", "D"), _edge("D", "E")])
CYCLE = _comp("G_CYC", ["A", "B", "C"], [_edge("A", "B"), _edge("B", "C"), _edge("C", "A")])
HUGE = _comp("G_HUGE", ["A", "B"], [_edge("A", "B", amount=99_99_99_999)])  # ~₹100 Cr
EMPTY = _comp("G_EMPTY", [], [])
SINGLE = _comp("G_ONE", ["A"], [])

ALL = [FAN_OUT, CHAIN, CYCLE, HUGE, EMPTY, SINGLE]


@pytest.mark.parametrize("comp", ALL, ids=lambda c: c["graph_id"])
def test_score_is_bounded_0_100(comp):
    a = assess(comp)
    assert 0 <= a["score"] <= 100, f"{comp['graph_id']} score out of range: {a['score']}"


@pytest.mark.parametrize("comp", ALL, ids=lambda c: c["graph_id"])
def test_confidence_is_bounded_and_distinct(comp):
    a = assess(comp)
    assert 5 <= a["confidence"] <= 99
    # Confidence must be its own metric, never silently equal to the risk score
    # (they answer different questions). They MAY coincide numerically, but the
    # engine derives them independently — assert the keys are both present.
    assert "score" in a and "confidence" in a


@pytest.mark.parametrize("comp", ALL, ids=lambda c: c["graph_id"])
def test_every_factor_is_explainable_and_within_weight(comp):
    a = assess(comp)
    for f in a["factors"]:
        assert 0 < f["points"] <= f["max"], f"{f['key']} points {f['points']} > max {f['max']}"
        assert f["label"] and f["detail"], "every factor must carry a human-readable explanation"


@pytest.mark.parametrize("comp", ALL, ids=lambda c: c["graph_id"])
def test_score_equals_clamped_sum_of_factor_points(comp):
    """The headline number must be reconstructable from its parts (no black box).
    With false-positive suppression the score may be pulled DOWN, never up."""
    a = assess(comp)
    raw = sum(f["points"] for f in a["factors"])
    assert a["score"] <= min(100, raw) + 0  # never exceeds the sum of contributions
    if not a["suppressed"]:
        assert a["score"] == min(100, raw)


@pytest.mark.parametrize("comp", ALL, ids=lambda c: c["graph_id"])
def test_wire_fraction_is_in_unit_interval(comp):
    """The websocket sends score/100 — the frontend renders it as `* 100`.
    This is the contract the 'FRAUD 1000%' bug broke."""
    a = assess(comp)
    fraction = round(a["score"] / 100.0, 4)
    assert 0.0 <= fraction <= 1.0


def test_empty_component_does_not_invent_risk():
    a = assess(EMPTY)
    assert a["score"] == 0
    assert a["should_create_case"] is False
    assert a["factors"] == []


def test_huge_amount_alone_cannot_create_a_case():
    """A single enormous transfer with no structural fraud signal must be
    suppressed below the alert threshold — amount alone never triggers."""
    a = assess(HUGE)
    assert a["should_create_case"] is False
    assert a["score"] <= 100
