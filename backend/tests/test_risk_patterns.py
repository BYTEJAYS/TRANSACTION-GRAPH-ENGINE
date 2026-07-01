"""
Risk Engine — per-pattern behavioural tests (audit areas 9 & 15).

For each canonical fraud topology these assert:
  * the CORRECT factor fires (a claimed pattern is backed by a real graph signal),
  * the pattern claim is consistent with the returned metrics (no "circular
    detected" without an actual cycle, etc. — area 9),
  * the score lands in a defensible band,
  * a clean graph is suppressed and never auto-creates a case.

Every component here is built from explicit edges, so the signal is genuine, not
asserted into existence.
"""
from __future__ import annotations

from risk_engine import assess


def _comp(graph_id, node_ids, edges, patterns=None, acct_types=None, profiles=None):
    pat = patterns or {}
    typ = acct_types or {}
    nodes = [{
        "id": n, "risk_score": 0.0,
        "account_type": typ.get(n, "normal"),
        "detected_patterns": pat.get(n, []),
        "transaction_count": 1,
    } for n in node_ids]
    comp = {"graph_id": graph_id, "node_ids": node_ids, "nodes": nodes, "edges": edges}
    if profiles is not None:
        comp["customer_profiles"] = profiles
    return comp


def _edge(s, t, amount=50_000, sec=0, rail="UPI"):
    ts = f"2026-01-01T10:{(sec // 60) % 60:02d}:{sec % 60:02d}"
    return {"source": s, "target": t, "amount": amount, "timestamp": ts, "payment_rail": rail}


def _keys(a):
    return {f["key"] for f in a["factors"]}


# ── Round-tripping (cycle) ────────────────────────────────────────────────────
def test_round_tripping_fires_circular_and_metric_agrees():
    a = assess(_comp("RT", ["A", "B", "C"],
                     [_edge("A", "B", sec=0), _edge("B", "C", sec=20), _edge("C", "A", sec=40)]))
    assert "circular" in _keys(a)            # factor fired
    assert a["metrics"]["circular"] is True  # area 9: claim backed by a real cycle
    assert a["score"] >= 25


# ── Fan-out ───────────────────────────────────────────────────────────────────
def test_fan_out_fires_and_degree_agrees():
    a = assess(_comp("FO", ["A", "B", "C", "D", "E", "F"],
                     [_edge("A", x, sec=i * 5) for i, x in enumerate(["B", "C", "D", "E", "F"])]))
    assert "fan_out" in _keys(a)
    assert a["metrics"]["max_fan_out"] >= 4


# ── Fan-in ────────────────────────────────────────────────────────────────────
def test_fan_in_fires_and_degree_agrees():
    a = assess(_comp("FI", ["A", "B", "C", "D", "E", "S"],
                     [_edge(x, "S", sec=i * 5) for i, x in enumerate(["A", "B", "C", "D", "E"])]))
    assert "fan_in" in _keys(a)
    assert a["metrics"]["max_fan_in"] >= 4


# ── Layering (multi-hop chain) ────────────────────────────────────────────────
def test_layering_fires_when_chain_is_deep():
    a = assess(_comp("LAY", ["A", "B", "C", "D", "E"],
                     [_edge("A", "B", sec=0), _edge("B", "C", sec=15),
                      _edge("C", "D", sec=30), _edge("D", "E", sec=45)]))
    assert "layering" in _keys(a)
    assert a["metrics"]["layering_depth"] >= 3   # claim backed by real depth


# ── Structuring (many rapid sub-threshold transfers) ──────────────────────────
def test_structuring_fires_velocity():
    # 6 transfers just under the ₹2L structuring band, all within the velocity window
    edges = [_edge("A", f"R{i}", amount=1_95_000, sec=i * 10) for i in range(6)]
    a = assess(_comp("STR", ["A"] + [f"R{i}" for i in range(6)], edges))
    assert "velocity" in _keys(a) or "fan_out" in _keys(a)
    assert a["score"] >= 30


# ── Dormant activation ────────────────────────────────────────────────────────
def test_dormant_activation_fires_only_with_signal():
    with_dormant = assess(_comp("DORM", ["A", "B"], [_edge("A", "B", sec=0)],
                                patterns={"A": ["dormant account reactivated"]}))
    without = assess(_comp("NODORM", ["A", "B"], [_edge("A", "B", sec=0)]))
    assert "dormant" in _keys(with_dormant)
    assert "dormant" not in _keys(without)      # never asserted without evidence


# ── Cash-out ──────────────────────────────────────────────────────────────────
def test_cash_out_fires_with_cash_endpoint_and_structure():
    a = assess(_comp("CASH", ["A", "B", "C", "D"],
                     [_edge("A", "B", sec=0), _edge("B", "C", sec=15), _edge("C", "D", sec=30)],
                     acct_types={"D": "cash"}))
    assert "cash" in _keys(a)
    assert a["metrics"]["cash"] is True


# ── Profile mismatch (graceful) ───────────────────────────────────────────────
def test_profile_mismatch_is_bounded_and_explainable():
    # A salaried customer moving ₹25L — the profile layer (if available) adds a
    # deviation factor; if the module is absent the engine still returns a bounded,
    # explainable score. Either way: no crash, no fabricated number.
    a = assess(_comp("PROF", ["A", "B"], [_edge("A", "B", amount=25_00_000, sec=0)],
                     profiles={"A": {"customer_type": "Salaried Employee",
                                     "monthly_income": 80_000}}))
    assert 0 <= a["score"] <= 100
    for f in a["factors"]:
        assert 0 < f["points"] <= f["max"] and f["label"] and f["detail"]


# ── Clean / normal graph ──────────────────────────────────────────────────────
def test_clean_graph_is_suppressed_and_creates_no_case():
    # One small, single-hop transfer with no structural signal → legitimate.
    a = assess(_comp("CLEAN", ["A", "B"], [_edge("A", "B", amount=8_000, sec=0)]))
    assert a["should_create_case"] is False
    assert a["score"] <= a["investigation_threshold"]


# ── Cross-check: a claimed pattern always matches a metric (area 9) ───────────
def test_no_pattern_is_claimed_without_a_matching_metric():
    for comp in (
        _comp("c1", ["A", "B", "C"], [_edge("A", "B"), _edge("B", "C"), _edge("C", "A")]),
        _comp("c2", ["A", "B", "C", "D", "E", "F"], [_edge("A", x) for x in ["B", "C", "D", "E", "F"]]),
    ):
        a = assess(comp)
        k = _keys(a)
        if "circular" in k:
            assert a["metrics"]["circular"] is True
        if "fan_out" in k:
            assert a["metrics"]["max_fan_out"] >= 2
        if "layering" in k:
            assert a["metrics"]["layering_depth"] >= 3
