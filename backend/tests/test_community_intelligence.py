"""Tests for the community-intelligence engine."""
from graph_engine.community_intelligence import analyze_communities


def _mk(edges):
    nodes = {}
    for s, t, *_ in edges:
        nodes.setdefault(s, {"id": s})
        nodes.setdefault(t, {"id": t})
    edge_dicts = [
        {"source": s, "target": t, "amount": a, "risk_score": r,
         "is_flagged": r >= 0.7}
        for (s, t, a, r) in edges
    ]
    return list(nodes.values()), edge_dicts


def test_empty_graph_is_safe():
    r = analyze_communities([], [])
    assert r["available"] is False
    assert r["community_count"] == 0


def test_detects_communities_and_membership():
    # two clear clusters joined by a single weak bridge edge
    nodes, edges = _mk([
        ("A", "B", 100, 0.2), ("B", "C", 100, 0.2), ("C", "A", 100, 0.2),
        ("X", "Y", 100, 0.2), ("Y", "Z", 100, 0.2), ("Z", "X", 100, 0.2),
        ("C", "X", 10, 0.1),  # bridge
    ])
    r = analyze_communities(nodes, edges)
    assert r["available"] is True
    assert r["community_count"] >= 2
    assert set(r["node_membership"]) == {"A", "B", "C", "X", "Y", "Z"}


def test_entry_exit_and_risk_ordering():
    # SRC funds a mule ring that cashes out; high-risk edges flagged
    nodes, edges = _mk([
        ("SRC", "M1", 90000, 0.8), ("M1", "M2", 88000, 0.85),
        ("M2", "CASH_OUT_1", 86000, 0.9),
        # a separate low-risk benign pair
        ("P", "Q", 500, 0.1),
    ])
    r = analyze_communities(nodes, edges)
    assert r["available"] is True
    # strongest-risk community first
    top = r["communities"][0]
    assert top["risk_score"] >= r["communities"][-1]["risk_score"]
    # the laundering community should expose a cash-out exit point
    laundering = next(c for c in r["communities"] if any(
        "CASH" in ep["account"] for ep in c["exit_points"]))
    assert laundering["leader"] is not None
    # deep enrichment (Bundle A): the engine-derived fields are present
    assert "dominant_pattern" in laundering
    assert "reasoning" in laundering and isinstance(laundering["reasoning"], str)
    assert "avg_layering_depth" in laundering
    assert "total_exposure" in laundering and laundering["total_exposure"] > 0
    assert "beneficiaries" in laundering


def test_deep_enrichment_can_be_disabled():
    nodes, edges = _mk([
        ("SRC", "M1", 90000, 0.8), ("M1", "M2", 88000, 0.85),
        ("M2", "CASH_OUT_1", 86000, 0.9),
    ])
    r = analyze_communities(nodes, edges, deep=False)
    assert r["available"] is True
    # cheap mode: no engine-derived fields
    assert "dominant_pattern" not in r["communities"][0]
