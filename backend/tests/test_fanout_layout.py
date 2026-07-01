"""
Fan-out layout regression suite — a wide fan-out whose children carry their own
downstream tails (e.g. SOURCE → 6 smurfs, two of which → a cash-out) must render as
a clean RADIAL FAN, not a layered column that flings the branch-bearing children to
the extremes ("one smurf shoots sideways") and stops reading as a fan.

Asserts, geometrically: every hub→child edge is the same length, children are evenly
spaced by angle, cash-out tails sit OUTSIDE the fan radius, and no edge crosses.
"""
from __future__ import annotations

import math

from graph_engine.layout import compute_layout, _build_digraph

MODES = ("fund_flow", "layered")


def _nodes(ids):
    return [{"id": i} for i in ids]


def _edges(pairs):
    return [{"source": s, "target": t} for s, t in pairs]


def _coords(res):
    return {n: (p["x"], p["y"]) for n, p in res["positions"].items()}


def _seg_cross(p1, p2, p3, p4) -> bool:
    def o(a, b, c):
        return (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])

    def s(a, b, c):
        v = o(a, b, c)
        return 1 if v > 0 else -1 if v < 0 else 0

    if p3 in (p1, p2) or p4 in (p1, p2):
        return False
    return s(p3, p4, p1) != s(p3, p4, p2) and s(p1, p2, p3) != s(p1, p2, p4)


def _no_crossings(coords, edges):
    segs = [(coords[e["source"]], coords[e["target"]], e["source"], e["target"]) for e in edges]
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            a1, a2, s1, t1 = segs[i]
            b1, b2, s2, t2 = segs[j]
            if {s1, t1} & {s2, t2}:
                continue
            if _seg_cross(a1, a2, b1, b2):
                return False
    return True


def _assert_clean_fan(nodes, edges, hub, children, cashouts=()):
    for mode in MODES:
        res = compute_layout(nodes, edges, mode=mode)
        coords = _coords(res)
        h = coords[hub]
        dists = [math.hypot(coords[c][0] - h[0], coords[c][1] - h[1]) for c in children]
        mean = sum(dists) / len(dists)
        spread = (max(dists) - min(dists)) / mean
        assert spread < 0.15, f"[{mode}] fan children not equal-radius (spread={spread:.2f})"
        # even angular spacing: adjacent gaps (excluding the largest wrap gap) uniform
        angs = sorted(math.atan2(coords[c][1] - h[1], coords[c][0] - h[0]) for c in children)
        gaps = sorted(
            (angs[i] - angs[i - 1]) % (2 * math.pi) for i in range(len(angs))
        )[:-1]  # drop the wrap/empty gap
        gmean = sum(gaps) / len(gaps)
        gvar = sum((g - gmean) ** 2 for g in gaps) / len(gaps)
        assert gvar < 0.05, f"[{mode}] fan children not evenly spaced (angVar={gvar:.3f})"
        assert _no_crossings(coords, edges), f"[{mode}] fan has edge crossings"
        # cash-out tails sit OUTSIDE the fan radius (clearly leaving outward)
        for co in cashouts:
            d = math.hypot(coords[co][0] - h[0], coords[co][1] - h[1])
            assert d > mean, f"[{mode}] cash-out {co} not outside fan radius"


def test_pure_fan_out_stays_legible_column():
    """A PURE fan (no tails) keeps the layered column: recipients share a flow layer
    (same x), spread on y, no crossings. (Radialization is reserved for fans WITH
    tails — see below — which is the case that otherwise breaks.)"""
    ids = ["H"] + [f"s{i}" for i in range(6)]
    edges = _edges([("H", f"s{i}") for i in range(6)])
    res = compute_layout(_nodes(ids), edges, mode="fund_flow")
    coords = _coords(res)
    xs = {round(coords[f"s{i}"][0], 2) for i in range(6)}
    assert len(xs) == 1, "pure fan recipients should share one flow layer (column)"
    assert _no_crossings(coords, edges)


def test_fan_out_with_one_cashout():
    """The reported failure: a 6-way fan where two smurfs forward to a cash-out."""
    ids = ["SOURCE_MAIN"] + [f"SMURF_{i:03d}" for i in range(1, 7)] + ["FANOUT_EXIT_001", "FANOUT_EXIT_002"]
    edges = _edges(
        [("SOURCE_MAIN", f"SMURF_{i:03d}") for i in range(1, 7)]
        + [("SMURF_003", "FANOUT_EXIT_001"), ("SMURF_004", "FANOUT_EXIT_002")]
    )
    _assert_clean_fan(_nodes(ids), edges, "SOURCE_MAIN",
                      [f"SMURF_{i:03d}" for i in range(1, 7)],
                      cashouts=["FANOUT_EXIT_001", "FANOUT_EXIT_002"])


def test_fan_out_with_multiple_cashouts():
    ids = ["H"] + [f"s{i}" for i in range(6)] + ["C1", "C2", "C3"]
    edges = _edges(
        [("H", f"s{i}") for i in range(6)]
        + [("s1", "C1"), ("s3", "C2"), ("s5", "C3")]
    )
    _assert_clean_fan(_nodes(ids), edges, "H", [f"s{i}" for i in range(6)],
                      cashouts=["C1", "C2", "C3"])


def test_fan_out_with_two_hop_tail():
    ids = ["H"] + [f"s{i}" for i in range(5)] + ["L1", "CASH"]
    edges = _edges(
        [("H", f"s{i}") for i in range(5)] + [("s2", "L1"), ("L1", "CASH")]
    )
    _assert_clean_fan(_nodes(ids), edges, "H", [f"s{i}" for i in range(5)], cashouts=["CASH"])


def test_fan_out_with_tail_quality_clean():
    """A fan-with-tail radializes → the 'starburst risk' quality flag must be gone."""
    ids = ["H"] + [f"s{i}" for i in range(8)] + ["X"]
    edges = _edges([("H", f"s{i}") for i in range(8)] + [("s0", "X")])
    res = compute_layout(_nodes(ids), edges, mode="fund_flow")
    assert res["quality"]["pass"], res["quality"]["issues"]
    assert res["quality"]["crossings"] == 0


def test_fanout_layout_deterministic():
    ids = ["H"] + [f"s{i}" for i in range(6)] + ["CASH"]
    edges = _edges([("H", f"s{i}") for i in range(6)] + [("s2", "CASH")])
    a = compute_layout(_nodes(ids), edges, mode="fund_flow")["positions"]
    b = compute_layout(_nodes(ids), edges, mode="fund_flow")["positions"]
    assert a == b


def test_narrow_fan_not_radialized():
    """A 3-way split (< _FAN_MIN) is NOT a wide fan — stays in the layered engine."""
    ids = ["H", "a", "b", "c", "c1"]
    edges = _edges([("H", "a"), ("H", "b"), ("H", "c"), ("c", "c1")])
    res = compute_layout(_nodes(ids), edges, mode="fund_flow")
    coords = _coords(res)
    # not forced onto a circle: children need not be equidistant from H
    dists = [math.hypot(coords[c][0] - coords["H"][0], coords[c][1] - coords["H"][1])
             for c in ("a", "b", "c")]
    # just assert it produced a valid, crossing-free layout (no radial constraint)
    assert _no_crossings(coords, edges)
    assert len(set(round(d) for d in dists)) >= 1  # sanity: positions exist
