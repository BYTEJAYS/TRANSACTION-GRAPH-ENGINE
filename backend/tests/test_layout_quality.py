"""Tests for the layout-quality validation + repair engine."""
from graph_engine.layout import compute_layout
from graph_engine.layout_quality import (
    assess_quality,
    count_crossings,
    detect_overlaps,
    repair_overlaps,
)


def test_detect_and_repair_overlaps():
    # three nodes piled on the same point
    coords = {"A": (0.0, 0.0), "B": (1.0, 0.0), "C": (0.0, 1.0)}
    overlaps = detect_overlaps(coords, min_dist=60.0)
    assert len(overlaps) == 3  # all pairs overlap
    fixed = repair_overlaps(coords, min_dist=60.0)
    assert detect_overlaps(fixed, min_dist=60.0) == []  # repaired apart


def test_count_crossings_on_a_known_X():
    # two segments that cross: A-B and C-D form an X
    coords = {"A": (0.0, 0.0), "B": (100.0, 100.0), "C": (0.0, 100.0), "D": (100.0, 0.0)}
    r = count_crossings(coords, [("A", "B"), ("C", "D")])
    assert r["crossings"] == 1
    # adjacent edges sharing a node never count as a crossing
    r2 = count_crossings(coords, [("A", "B"), ("B", "C")])
    assert r2["crossings"] == 0


def test_assess_quality_pass_and_fail():
    good = {"A": (0.0, 0.0), "B": (200.0, 0.0), "C": (400.0, 0.0)}
    q = assess_quality(good, [("A", "B"), ("B", "C")], min_dist=60.0)
    assert q["pass"] is True and q["overlap_count"] == 0

    piled = {"A": (0.0, 0.0), "B": (5.0, 0.0)}
    q2 = assess_quality(piled, [("A", "B")], min_dist=60.0)
    assert q2["pass"] is False and q2["overlap_count"] == 1
    assert q2["issues"]


def test_compute_layout_attaches_quality_and_has_no_overlap():
    nodes = [{"id": n} for n in ["SRC", "M1", "M2", "M3", "CASH_OUT_1"]]
    edges = [
        {"source": "SRC", "target": "M1", "amount": 100, "timestamp": "2026-01-01T10:00:00"},
        {"source": "SRC", "target": "M2", "amount": 100, "timestamp": "2026-01-01T10:01:00"},
        {"source": "SRC", "target": "M3", "amount": 100, "timestamp": "2026-01-01T10:02:00"},
        {"source": "M1", "target": "CASH_OUT_1", "amount": 90, "timestamp": "2026-01-01T11:00:00"},
    ]
    for mode in ("fund_flow", "layered", "community", "force", "timeline"):
        r = compute_layout(nodes, edges, mode=mode)
        assert "quality" in r
        q = r["quality"]
        # after the repair pass the returned coordinates must have no overlap
        assert q["overlap_count"] == 0, f"{mode} left overlapping nodes"
        assert 0.0 <= q["quality_score"] <= 1.0


def test_community_mode_orders_cashout_to_the_right():
    # two separate clusters: a benign pair and a chain ending in cash-out
    nodes = [{"id": n} for n in ["P", "Q", "SRC", "M1", "CASH_OUT_1"]]
    edges = [
        {"source": "P", "target": "Q", "amount": 100, "timestamp": "2026-01-01T10:00:00"},
        {"source": "SRC", "target": "M1", "amount": 5000, "timestamp": "2026-01-01T10:00:00"},
        {"source": "M1", "target": "CASH_OUT_1", "amount": 4900, "timestamp": "2026-01-01T11:00:00"},
    ]
    r = compute_layout(nodes, edges, mode="community")
    pos = r["positions"]
    # cash-out cluster sits to the right of the benign cluster
    assert pos["CASH_OUT_1"]["x"] >= pos["P"]["x"]
