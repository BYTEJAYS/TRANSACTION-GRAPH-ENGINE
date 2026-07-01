"""
Case Intelligence — the auto-generated investigation summary for one cluster.

Assembles a complete, evaluator-ready case file from the engines already in
place (V2 analysis, motif engine, recommendation engine, graph analytics):
exposure, suspicious amount, money origin → final beneficiary, layering depth,
fraud patterns, highest-risk entity, confidence, risk level, narrative and
recommended actions.

Reuses everything; computes nothing new on its own beyond simple aggregation.
"""
from __future__ import annotations

from typing import Any

import networkx as nx

from blue_team_v2.engine import BlueTeamV2Engine
from recommendation_engine import recommend
from rule_engine import extract_motifs, severity_label
from graph_engine.analytics import narrate_flows
from graph_engine.community_intelligence import analyze_communities
from graph_engine.timeline import summarize_timeline


def _risk_level(score: float) -> str:
    if score >= 0.83:
        return "CRITICAL"
    if score >= 0.62:
        return "HIGH"
    if score >= 0.38:
        return "MEDIUM"
    return "LOW"


def _longest_chain(G: nx.DiGraph) -> list[str]:
    """The actual longest directed chain of nodes (for 'largest layering chain')."""
    if G.number_of_nodes() == 0:
        return []
    try:
        if nx.is_directed_acyclic_graph(G):
            return nx.dag_longest_path(G)
    except Exception:
        pass
    best: list[str] = []
    nodes = list(G.nodes())
    if len(nodes) > 200:
        nodes = sorted(nodes, key=lambda x: G.out_degree(x), reverse=True)[:200]
    for s in nodes:
        try:
            for p in nx.single_source_shortest_path(G, s, cutoff=20).values():
                if len(p) > len(best):
                    best = p
        except Exception:
            continue
    return best


def _longest_chain_len(G: nx.DiGraph) -> int:
    if G.number_of_nodes() == 0:
        return 0
    try:
        if nx.is_directed_acyclic_graph(G):
            return len(nx.dag_longest_path(G))
    except Exception:
        pass
    best = 0
    nodes = list(G.nodes())
    if len(nodes) > 300:
        nodes = sorted(nodes, key=lambda x: G.out_degree(x), reverse=True)[:300]
    for s in nodes:
        try:
            best = max(best, max((len(p) for p in nx.single_source_shortest_path(G, s, cutoff=20).values()), default=0))
        except Exception:
            continue
    return best


def build_case_summary(component: dict) -> dict[str, Any]:
    """Generate the full case-intelligence summary for one connected component."""
    analysis = BlueTeamV2Engine().analyze_component(component)
    motifs = extract_motifs(component, analysis=analysis)
    edges = component.get("edges", [])
    graph_id = component.get("graph_id", "GRAPH_001")

    # money totals
    total_amount = sum(float(e.get("amount", 0) or 0) for e in edges)
    flagged_nodes = set(BlueTeamV2Engine().flagged_nodes(analysis))
    suspicious_amount = sum(
        float(e.get("amount", 0) or 0)
        for e in edges
        if e.get("source") in flagged_nodes or e.get("target") in flagged_nodes
    )

    # structure
    G = nx.DiGraph()
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s and t:
            G.add_edge(s, t)
    layering_depth = max(0, _longest_chain_len(G) - 1)

    # highest-risk entity
    highest = max(analysis.metrics.values(), key=lambda m: m.risk_score, default=None)

    ci = analysis.cluster
    # final beneficiary = cash-out if present, else the largest net receiver
    in_vol = {n: 0.0 for n in component.get("node_ids", [])}
    out_vol = dict(in_vol)
    for e in edges:
        a = float(e.get("amount", 0) or 0)
        if e.get("target") in in_vol:
            in_vol[e["target"]] += a
        if e.get("source") in out_vol:
            out_vol[e["source"]] += a
    final_beneficiary = ci.cashout or (
        [max(in_vol, key=lambda n: in_vol[n] - out_vol[n])] if in_vol else []
    )

    # ── extended investigation rollups (Bundle A) ────────────────────────────
    node_ids = component.get("node_ids", [])
    nodes_list = [{"id": n} for n in node_ids]

    # timeline rollup (span / velocity / night-weekend / bursts)
    timeline = summarize_timeline(edges)

    # community structure inside this case (cheap mode — this component is itself
    # usually one cluster; sub-communities are informational, so skip the nested
    # engine runs that deep mode would trigger).
    communities = analyze_communities(nodes_list, edges, top=10, deep=False).get("communities", [])
    largest_community = max(communities, key=lambda c: c["size"], default=None)
    highest_risk_community = communities[0] if communities else None  # already risk-sorted

    def _comm_brief(c: dict | None) -> dict | None:
        if not c:
            return None
        return {"community_id": c["community_id"], "size": c["size"],
                "leader": c["leader"], "role": c["role"],
                "risk_score": c["risk_score"], "risk_level": c["risk_level"]}

    # largest layering chain (the actual node path, not just its depth)
    largest_chain = _longest_chain(G)

    # influence leaders within the case
    n_nodes = G.number_of_nodes()
    try:
        betw = (nx.betweenness_centrality(G, normalized=True) if n_nodes <= 1200
                else nx.betweenness_centrality(G, k=min(300, n_nodes), normalized=True, seed=42))
    except Exception:
        betw = {}
    highest_betweenness = max(betw, key=betw.get, default=None) if betw else None
    most_connected = max(G.nodes(), key=lambda x: G.degree(x), default=None) if n_nodes else None

    # plain-language money-trail story (structural; no extra engine run)
    money_trail = narrate_flows(nodes_list, edges)

    return {
        "graph_id": graph_id,
        "case_summary": analysis.narrative,
        "verdict": analysis.verdict.value,
        "risk_score": round(analysis.cluster_risk * 100),
        "risk_level": _risk_level(analysis.cluster_risk),
        "confidence": round(analysis.confidence, 3),
        "primary_classification": analysis.primary_classification,
        "secondary_classification": analysis.secondary_classification,
        # totals
        "total_transactions": len(edges),
        "total_accounts": len(component.get("node_ids", [])),
        "total_exposure": round(total_amount, 2),
        "total_suspicious_amount": round(suspicious_amount, 2),
        # money trail
        "money_origin": ci.origin,
        "final_beneficiary": final_beneficiary,
        "estimated_layering_depth": layering_depth,
        # entities
        "highest_risk_entity": (
            {"account": highest.node_id, "risk": round(highest.risk_score, 3),
             "role": highest.cluster_role.value} if highest else None
        ),
        # patterns
        "fraud_patterns": sorted({m["pattern"] for m in motifs}),
        "motif_count": len(motifs),
        "top_motifs": [
            {"pattern": m["pattern"], "label": m["label"], "severity": m["severity"],
             "confidence": m["confidence"], "explanation": m["explanation"]}
            for m in motifs[:5]
        ],
        "severity": severity_label(analysis.cluster_risk),
        # ── extended investigation rollups (Bundle A) ──
        "timeline": timeline,
        "community_count": len(communities),
        "largest_community": _comm_brief(largest_community),
        "highest_risk_community": _comm_brief(highest_risk_community),
        "largest_layering_chain": {
            "chain": largest_chain,
            "length": max(0, len(largest_chain) - 1),
        },
        "top_influencer": highest_betweenness,        # highest betweenness (key relay)
        "highest_betweenness_node": highest_betweenness,
        "most_connected_node": most_connected,
        "money_trail_summary": money_trail.get("summary_narrative"),
        "money_trail_assessment": money_trail.get("assessment"),
        # actions
        "recommended_actions": recommend(analysis, motifs),
    }
