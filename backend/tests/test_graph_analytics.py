"""Tests for the graph analytics + path-intelligence engine."""
from graph_engine.analytics import analyze_paths, compute_analytics, narrate_flows


def _mk(edges):
    nodes = {}
    for s, t, *_ in edges:
        nodes[s] = nodes.get(s, {"id": s})
        nodes[t] = nodes.get(t, {"id": t})
    edge_dicts = [
        {"source": s, "target": t, "amount": a, "risk_score": r}
        for (s, t, a, r) in edges
    ]
    return list(nodes.values()), edge_dicts


# SRC fans out to 3 mules, all funnel into CASH (collector/beneficiary)
RING = _mk([
    ("SRC", "M1", 90000, 0.7), ("SRC", "M2", 80000, 0.6), ("SRC", "M3", 95000, 0.8),
    ("M1", "CASH", 88000, 0.9), ("M2", "CASH", 78000, 0.6), ("M3", "CASH", 93000, 0.95),
])


def test_analytics_summary_counts():
    nodes, edges = RING
    a = compute_analytics(nodes, edges)
    assert a["available"] is True
    s = a["summary"]
    assert s["node_count"] == 5
    assert s["edge_count"] == 6
    assert 0 < s["density"] <= 1
    assert s["weakly_connected_components"] == 1


def test_cash_is_top_beneficiary_and_aggregator():
    nodes, edges = RING
    a = compute_analytics(nodes, edges)
    top_benef = a["fund_flow"]["top_beneficiaries"][0]["account"]
    top_aggr = a["fund_flow"]["top_aggregators"][0]["account"]
    assert top_benef == "CASH"   # receives the most value
    assert top_aggr == "CASH"    # collects from the most counterparties


def test_src_is_top_source_and_distributor():
    nodes, edges = RING
    a = compute_analytics(nodes, edges)
    assert a["fund_flow"]["top_sources"][0]["account"] == "SRC"
    assert a["fund_flow"]["top_distributors"][0]["account"] == "SRC"


def test_influence_and_centrality_present():
    nodes, edges = RING
    a = compute_analytics(nodes, edges)
    assert a["influence_ranking"]
    for key in ("pagerank", "hubs", "authorities", "eigenvector", "betweenness"):
        assert key in a["centrality"]


def test_bridge_detection_on_a_chain():
    # a pure chain → every edge is a bridge
    nodes, edges = _mk([("A", "B", 100, 0.1), ("B", "C", 100, 0.1), ("C", "D", 100, 0.1)])
    a = compute_analytics(nodes, edges)
    assert a["summary"]["bridge_count"] == 3
    assert "B" in a["structure"]["articulation_points"]


def test_empty_graph_is_safe():
    a = compute_analytics([], [])
    assert a["available"] is False


# ── path intelligence ────────────────────────────────────────────────────────
def test_paths_shortest_and_highest_risk_differ():
    # two routes A→D: low-risk direct-ish vs high-risk longer
    nodes, edges = _mk([
        ("A", "X", 10000, 0.1), ("X", "D", 10000, 0.1),          # 2 hops, low risk
        ("A", "Y", 50000, 0.9), ("Y", "Z", 60000, 0.95), ("Z", "D", 55000, 0.92),  # 3 hops, high risk + value
    ])
    p = analyze_paths(nodes, edges, "A", "D")
    assert p["available"] and p["connected"]
    assert p["shortest"]["hops"] == 2
    assert p["highest_risk"]["path"] == ["A", "Y", "Z", "D"]
    assert p["largest_amount"]["path"] == ["A", "Y", "Z", "D"]


def test_paths_unconnected():
    nodes, edges = _mk([("A", "B", 100, 0.1), ("C", "D", 100, 0.1)])
    p = analyze_paths(nodes, edges, "A", "D")
    assert p["available"] is True
    assert p["connected"] is False


def test_paths_missing_node():
    nodes, edges = RING
    p = analyze_paths(nodes, edges, "SRC", "NOPE")
    assert p["available"] is False


# ── path narratives (P9) ──────────────────────────────────────────────────────
def test_paths_carry_narrative_and_layered_route():
    nodes, edges = _mk([
        ("A", "X", 10000, 0.1), ("X", "D", 10000, 0.1),
        ("A", "Y", 50000, 0.9), ("Y", "Z", 60000, 0.95), ("Z", "D", 55000, 0.92),
    ])
    p = analyze_paths(nodes, edges, "A", "D")
    assert isinstance(p["narrative"], str) and "A" in p["narrative"]
    # most-layered route is the deepest chain (4 nodes / 3 hops)
    assert p["most_layered"]["hops"] == 3
    # a 3-hop layering path should trigger the layering rule
    rule_ids = {r["rule_id"] for r in p["triggered_rules"]}
    assert "AML020" in rule_ids


def test_narrate_flows_finds_cashout_and_layering():
    nodes, edges = _mk([
        ("SRC", "M1", 90000, 0.7), ("M1", "M2", 88000, 0.8),
        ("M2", "CASH_OUT_1", 86000, 0.9),
    ])
    r = narrate_flows(nodes, edges)
    assert r["available"] is True
    assert r["most_layered"]["hops"] == 3
    assert r["cashout_route_count"] >= 1
    co = r["cashout_routes"][0]
    assert co["destination"] == "CASH_OUT_1"
    assert co["is_cash"] is True
    assert "AML011" in {rr["rule_id"] for rr in co["triggered_rules"]}
    assert "CASH_OUT_1" in co["narrative"]


def test_narrate_flows_empty_is_safe():
    assert narrate_flows([], [])["available"] is False


def test_narrate_flows_investigator_story():
    # SRC fans out to 3 mules, they reconverge on HUB, then a layering chain to cash-out
    nodes, edges = _mk([
        ("SRC", "M1", 30000, 0.6), ("SRC", "M2", 30000, 0.6), ("SRC", "M3", 30000, 0.6),
        ("M1", "HUB", 29000, 0.7), ("M2", "HUB", 29000, 0.7), ("M3", "HUB", 29000, 0.7),
        ("HUB", "L1", 80000, 0.8), ("L1", "L2", 78000, 0.85), ("L2", "CASH_OUT_1", 76000, 0.9),
    ])
    r = narrate_flows(nodes, edges)
    assert r["available"] is True
    n = r["summary_narrative"]
    assert "originated" in n
    assert "fan-out" in n or "split" in n
    assert "cash-out" in n.lower()
    stage_names = {s["stage"] for s in r["stages"]}
    assert {"origin", "cashout"} <= stage_names
    assert isinstance(r["assessment"], str) and len(r["assessment"]) > 0
