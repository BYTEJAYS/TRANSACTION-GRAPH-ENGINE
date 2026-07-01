"""Tests for the backend graph layout engine (graph_engine/layout.py)."""
import math

import pytest

from graph_engine.layout import LAYOUT_MODES, compute_layout


def _mk(node_ids, edge_pairs, amount=10000, ts_base="2026-01-01T10:0"):
    nodes = [{"id": n} for n in node_ids]
    edges = [
        {"source": s, "target": t, "amount": amount, "timestamp": f"{ts_base}{i % 6}:00"}
        for i, (s, t) in enumerate(edge_pairs)
    ]
    return nodes, edges


# ── fraud topologies ─────────────────────────────────────────────────────────
FAN_OUT = _mk(["A", "B", "C", "D", "E"], [("A", "B"), ("A", "C"), ("A", "D"), ("A", "E")])
CHAIN = _mk(["A", "B", "C", "D", "E"], [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")])
DIAMOND = _mk(["S", "L", "R", "T"], [("S", "L"), ("S", "R"), ("L", "T"), ("R", "T")])
CYCLE = _mk(["A", "B", "C"], [("A", "B"), ("B", "C"), ("C", "A")])


@pytest.mark.parametrize("mode", LAYOUT_MODES)
@pytest.mark.parametrize("graph", [FAN_OUT, CHAIN, DIAMOND, CYCLE], ids=["fanout", "chain", "diamond", "cycle"])
def test_every_mode_places_every_node_with_finite_coords(mode, graph):
    nodes, edges = graph
    out = compute_layout(nodes, edges, mode=mode)
    assert out["mode"] == mode
    assert set(out["positions"]) == {n["id"] for n in nodes}
    for p in out["positions"].values():
        assert math.isfinite(p["x"]) and math.isfinite(p["y"])


@pytest.mark.parametrize("mode", LAYOUT_MODES)
def test_layout_is_deterministic(mode):
    nodes, edges = DIAMOND
    a = compute_layout(nodes, edges, mode=mode)
    b = compute_layout(nodes, edges, mode=mode)
    assert a["positions"] == b["positions"], f"{mode} layout is not stable between runs"


def test_fund_flow_is_left_to_right_monotonic():
    """Money must move strictly rightwards: every edge's target.x > source.x."""
    nodes, edges = CHAIN
    out = compute_layout(nodes, edges, mode="fund_flow")
    pos = out["positions"]
    for e in edges:
        assert pos[e["target"]]["x"] > pos[e["source"]]["x"]
    # source at layer 0, sink at the deepest layer
    assert out["node_meta"]["A"]["layer"] == 0
    assert out["node_meta"]["E"]["layer"] == 4


def test_fund_flow_fans_out_into_a_column():
    """Fan-out: the 4 recipients share one layer (same x), spread on y."""
    nodes, edges = FAN_OUT
    out = compute_layout(nodes, edges, mode="fund_flow")
    pos = out["positions"]
    recipients = ["B", "C", "D", "E"]
    xs = {round(pos[r]["x"], 2) for r in recipients}
    ys = {round(pos[r]["y"], 2) for r in recipients}
    assert len(xs) == 1          # same flow layer → identical x
    assert len(ys) == len(recipients)  # spread vertically, no overlap


def test_layered_is_top_to_bottom():
    nodes, edges = CHAIN
    out = compute_layout(nodes, edges, mode="layered")
    pos = out["positions"]
    for e in edges:
        assert pos[e["target"]]["y"] < pos[e["source"]]["y"]  # flow goes downward


def test_cycle_does_not_explode_layering():
    nodes, edges = CYCLE
    out = compute_layout(nodes, edges, mode="fund_flow")
    layers = [out["node_meta"][n]["layer"] for n in ("A", "B", "C")]
    assert all(l == layers[0] for l in layers)  # SCC collapses to one layer


def test_community_separates_two_disjoint_clusters():
    nodes, edges = _mk(
        ["A1", "A2", "A3", "B1", "B2", "B3"],
        [("A1", "A2"), ("A2", "A3"), ("A3", "A1"), ("B1", "B2"), ("B2", "B3"), ("B3", "B1")],
    )
    out = compute_layout(nodes, edges, mode="community")
    comm = out["node_meta"]
    a_comm = {comm[n]["community"] for n in ("A1", "A2", "A3")}
    b_comm = {comm[n]["community"] for n in ("B1", "B2", "B3")}
    assert len(a_comm) == 1 and len(b_comm) == 1
    assert a_comm != b_comm  # the two rings are assigned to different communities


# ── investigation-layout refinements ─────────────────────────────────────────
def test_disconnected_components_do_not_overlap_in_fund_flow():
    # diamond cluster + independent chain — must occupy disjoint perpendicular bands
    nodes, edges = _mk(
        ["A", "B", "C", "D", "P", "Q", "R"],
        [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"), ("P", "Q"), ("Q", "R")],
    )
    out = compute_layout(nodes, edges, mode="fund_flow")
    pos = out["positions"]
    band1 = [pos[n]["y"] for n in ("A", "B", "C", "D")]
    band2 = [pos[n]["y"] for n in ("P", "Q", "R")]
    # the two clusters' y-ranges must not interleave
    assert max(band1) < min(band2) or max(band2) < min(band1)
    assert out["quality"]["overlap_count"] == 0


def test_cycle_is_drawn_as_a_ring():
    nodes, edges = _mk(["A", "B", "C", "D"], [("A", "B"), ("B", "C"), ("C", "D"), ("D", "B")])
    out = compute_layout(nodes, edges, mode="fund_flow")
    pos = out["positions"]
    ring = ["B", "C", "D"]  # the strongly-connected cycle
    xs = {round(pos[n]["x"], 1) for n in ring}
    ys = {round(pos[n]["y"], 1) for n in ring}
    # a ring spreads across BOTH axes, not collapsed onto one line
    assert len(xs) > 1 and len(ys) > 1


def test_semantic_stage_labels():
    nodes, edges = _mk(
        ["ORIG", "M1", "M2", "M3", "SINK"],
        [("ORIG", "M1"), ("ORIG", "M2"), ("ORIG", "M3"),
         ("M1", "SINK"), ("M2", "SINK"), ("M3", "SINK")],
    )
    meta = compute_layout(nodes, edges, mode="fund_flow")["node_meta"]
    assert meta["ORIG"]["stage"] == "origin"                 # no inflow, fans out
    assert meta["SINK"]["stage"] in ("aggregation", "exit")  # collects from 3, terminal
    assert "stage" in meta["M1"]


def test_empty_graph_is_safe():
    out = compute_layout([], [], mode="force")
    assert out["positions"] == {}
    assert out["node_count"] == 0


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        compute_layout(*DIAMOND, mode="rainbow")


# ── automatic backend layout selection ───────────────────────────────────────
def test_auto_reports_selection_metadata():
    out = compute_layout(*DIAMOND, mode="auto")
    assert out["requested_mode"] == "auto"
    assert out["auto_selected"] is True
    assert out["mode"] in LAYOUT_MODES          # resolved to a concrete mode
    assert isinstance(out["selection_reason"], str) and out["selection_reason"]


def test_auto_picks_community_for_disconnected_clusters():
    nodes, edges = _mk(
        ["A1", "A2", "A3", "B1", "B2", "B3"],
        [("A1", "A2"), ("A2", "A3"), ("A3", "A1"), ("B1", "B2"), ("B2", "B3"), ("B3", "B1")],
    )
    out = compute_layout(nodes, edges, mode="auto")
    assert out["mode"] == "community"


def test_auto_picks_layered_for_deep_chain():
    nodes, edges = _mk(["A", "B", "C", "D", "E", "F"],
                       [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"), ("E", "F")])
    out = compute_layout(nodes, edges, mode="auto")
    assert out["mode"] == "layered"


def test_auto_picks_fund_flow_for_fan_out():
    out = compute_layout(*FAN_OUT, mode="auto")
    assert out["mode"] == "fund_flow"


def test_explicit_modes_still_work():
    for mode in LAYOUT_MODES:
        out = compute_layout(*DIAMOND, mode=mode)
        assert out["mode"] == mode
        assert out["auto_selected"] is False
