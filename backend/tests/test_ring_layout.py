"""
Ring-layout regression suite — circular laundering motifs must NEVER be drawn
with an unrelated edge cutting through the ring interior.

This guards the class of bug where `fund_flow`/`layered` circularizes a cycle but
leaves a branch (e.g. ROUND_C → CIR_LAYER_001 → … → CIR_CASHOUT) on the global
L→R axis, so the connecting edge stabs straight through the laundering circle.
Every scenario asserts, geometrically, that no non-ring edge passes through any
ring interior, that branch/cash-out nodes sit OUTSIDE the ring, and that the
layout's own quality report agrees (ring_interior_crossings == 0).
"""
from __future__ import annotations

import math

import pytest

from graph_engine.layout import compute_layout, ring_geometry, _build_digraph
from graph_engine.layout_quality import (
    detect_ring_interior_crossings,
    _seg_point_dist,
)

MODES = ("fund_flow", "layered")


def _nodes(ids):
    return [{"id": i} for i in ids]


def _edges(pairs):
    return [{"source": s, "target": t} for s, t in pairs]


def _coords(result):
    return {n: (p["x"], p["y"]) for n, p in result["positions"].items()}


def _assert_no_interior_crossing(nodes, edges, ring_members_list):
    """Run both flow modes and assert every ring is interior-clean."""
    for mode in MODES:
        res = compute_layout(nodes, edges, mode=mode)
        coords = _coords(res)
        G = _build_digraph(nodes, edges)
        rings = ring_geometry(G, coords)
        edge_pairs = [(e["source"], e["target"]) for e in edges]

        # 1. every expected ring is actually realised as a ring (SCC ≥ 3)
        assert len(rings) >= len(ring_members_list), (
            f"[{mode}] expected ≥{len(ring_members_list)} ring(s), found {len(rings)}"
        )

        # 2. the layout engine's own validator reports a clean interior
        offenders = detect_ring_interior_crossings(coords, edge_pairs, rings)
        assert offenders == [], f"[{mode}] edges cut through ring interior: {offenders}"
        assert res["quality"]["ring_interior_crossings"] == 0, (
            f"[{mode}] quality report flags ring crossings: {res['quality']}"
        )

        # 3. branch / external nodes sit OUTSIDE every ring they don't belong to
        for members, (cx, cy), R in rings:
            for n, (x, y) in coords.items():
                if n in members:
                    continue
                d = math.hypot(x - cx, y - cy)
                assert d >= R * 0.9, (
                    f"[{mode}] node {n} sits inside ring (d={d:.1f} < {R*0.9:.1f})"
                )
    return True


# ── Test 1 — Pure ring ────────────────────────────────────────────────────────
def test_pure_ring_is_circular():
    ids = ["A", "B", "C", "D"]
    edges = _edges([("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")])
    for mode in MODES:
        res = compute_layout(_nodes(ids), edges, mode=mode)
        coords = _coords(res)
        rings = ring_geometry(_build_digraph(_nodes(ids), edges), coords)
        assert len(rings) == 1
        members, (cx, cy), R = rings[0]
        assert members == set(ids)
        # all four nodes roughly equidistant from the centre → a real circle
        for n in ids:
            x, y = coords[n]
            assert abs(math.hypot(x - cx, y - cy) - R) < R * 0.25 + 1


# ── Test 2 — Ring with one exit branch (the reported bug) ──────────────────────
def test_ring_with_one_exit_branch_outside():
    ids = ["A", "B", "C", "D", "X", "Y", "EXIT"]
    edges = _edges([
        ("A", "B"), ("B", "C"), ("C", "D"), ("D", "A"),
        ("C", "X"), ("X", "Y"), ("Y", "EXIT"),
    ])
    _assert_no_interior_crossing(_nodes(ids), edges, [{"A", "B", "C", "D"}])


def test_reported_round_dataset():
    """The exact dataset from the bug report must not stab the ring."""
    ids = ["ROUND_A", "ROUND_B", "ROUND_C", "ROUND_D", "ROUND_E", "ROUND_F",
           "CIR_LAYER_001", "CIR_LAYER_002", "CIR_CASHOUT"]
    edges = _edges([
        ("ROUND_A", "ROUND_B"), ("ROUND_B", "ROUND_C"), ("ROUND_C", "ROUND_D"),
        ("ROUND_D", "ROUND_E"), ("ROUND_E", "ROUND_F"), ("ROUND_F", "ROUND_A"),
        ("ROUND_C", "CIR_LAYER_001"), ("CIR_LAYER_001", "CIR_LAYER_002"),
        ("CIR_LAYER_002", "CIR_CASHOUT"),
    ])
    ring = {"ROUND_A", "ROUND_B", "ROUND_C", "ROUND_D", "ROUND_E", "ROUND_F"}
    _assert_no_interior_crossing(_nodes(ids), edges, [ring])
    # the cash-out terminal must be the farthest-out node (a clean external exit)
    res = compute_layout(_nodes(ids), edges, mode="fund_flow")
    coords = _coords(res)
    rings = ring_geometry(_build_digraph(_nodes(ids), edges), coords)
    _, centre, R = rings[0]
    cashd = math.hypot(coords["CIR_CASHOUT"][0] - centre[0],
                       coords["CIR_CASHOUT"][1] - centre[1])
    assert cashd > R, "cash-out node must sit outside the ring"


# ── Test 3 — Ring with multiple exits ─────────────────────────────────────────
def test_ring_with_multiple_exits():
    ids = ["A", "B", "C", "D", "X", "Y"]
    edges = _edges([
        ("A", "B"), ("B", "C"), ("C", "D"), ("D", "A"),
        ("B", "X"), ("D", "Y"),
    ])
    _assert_no_interior_crossing(_nodes(ids), edges, [{"A", "B", "C", "D"}])


# ── Test 4 — Ring with an inbound entry ───────────────────────────────────────
def test_ring_with_entry_branch():
    ids = ["SOURCE", "A", "B", "C", "D"]
    edges = _edges([
        ("SOURCE", "A"),
        ("A", "B"), ("B", "C"), ("C", "D"), ("D", "A"),
    ])
    _assert_no_interior_crossing(_nodes(ids), edges, [{"A", "B", "C", "D"}])


# ── Test 5 — Two connected rings (bridge) ─────────────────────────────────────
def test_two_connected_rings():
    ids = ["A", "B", "C", "D", "BRIDGE", "E", "F", "G", "H"]
    edges = _edges([
        ("A", "B"), ("B", "C"), ("C", "D"), ("D", "A"),
        ("C", "BRIDGE"), ("BRIDGE", "E"),
        ("E", "F"), ("F", "G"), ("G", "H"), ("H", "E"),
    ])
    _assert_no_interior_crossing(
        _nodes(ids), edges, [{"A", "B", "C", "D"}, {"E", "F", "G", "H"}]
    )


# ── Test 6 — Ring + diamond ───────────────────────────────────────────────────
def test_ring_plus_diamond():
    ids = ["A", "B", "C", "D", "P", "Q", "R", "S"]
    edges = _edges([
        ("A", "B"), ("B", "C"), ("C", "D"), ("D", "A"),
        ("C", "P"), ("P", "Q"), ("P", "R"), ("Q", "S"), ("R", "S"),
    ])
    _assert_no_interior_crossing(_nodes(ids), edges, [{"A", "B", "C", "D"}])


# ── Test 7 — Ring + cash-out terminal ─────────────────────────────────────────
def test_ring_plus_cashout_terminal_external():
    ids = ["A", "B", "C", "D", "MULE", "CASH_OUT_1"]
    edges = _edges([
        ("A", "B"), ("B", "C"), ("C", "D"), ("D", "A"),
        ("C", "MULE"), ("MULE", "CASH_OUT_1"),
    ])
    _assert_no_interior_crossing(_nodes(ids), edges, [{"A", "B", "C", "D"}])
    res = compute_layout(_nodes(ids), edges, mode="fund_flow")
    coords = _coords(res)
    rings = ring_geometry(_build_digraph(_nodes(ids), edges), coords)
    _, centre, R = rings[0]
    d = math.hypot(coords["CASH_OUT_1"][0] - centre[0], coords["CASH_OUT_1"][1] - centre[1])
    assert d > R, "cash-out node must be external to the ring"


# ── Test 8 — Large hybrid fraud graph (ring + fan-out + fan-in + chain) ───────
def test_large_hybrid_fraud_graph():
    ids = ["A", "B", "C", "D", "E", "F",           # ring
           "F1", "F2", "F3",                        # fan-out off B
           "G1", "G2", "SINK",                      # fan-in off D
           "L1", "L2", "L3", "CASH"]                # layering chain off E
    edges = _edges([
        ("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"), ("E", "F"), ("F", "A"),
        ("B", "F1"), ("B", "F2"), ("B", "F3"),
        ("G1", "D"), ("G2", "D"), ("D", "SINK"),
        ("E", "L1"), ("L1", "L2"), ("L2", "L3"), ("L3", "CASH"),
    ])
    _assert_no_interior_crossing(
        _nodes(ids), edges, [{"A", "B", "C", "D", "E", "F"}]
    )


# ── Determinism ───────────────────────────────────────────────────────────────
def test_ring_layout_is_deterministic():
    ids = ["A", "B", "C", "D", "X", "Y", "EXIT"]
    edges = _edges([
        ("A", "B"), ("B", "C"), ("C", "D"), ("D", "A"),
        ("C", "X"), ("X", "Y"), ("Y", "EXIT"),
    ])
    a = compute_layout(_nodes(ids), edges, mode="fund_flow")["positions"]
    b = compute_layout(_nodes(ids), edges, mode="fund_flow")["positions"]
    assert a == b


# ── The protected-interior helper itself ──────────────────────────────────────
def test_detector_flags_a_real_interior_stab():
    """Sanity: the detector DOES flag an edge through a ring centre."""
    coords = {"A": (100, 0), "B": (0, 100), "C": (-100, 0), "D": (0, -100),
              "P": (-200, 5), "Q": (200, -5)}
    rings = [({"A", "B", "C", "D"}, (0.0, 0.0), 100.0)]
    # P→Q runs straight across the centre → must be flagged
    assert detect_ring_interior_crossings(coords, [("P", "Q")], rings) == [("P", "Q")]
    # a ring boundary edge is never flagged
    assert detect_ring_interior_crossings(coords, [("A", "B")], rings) == []
