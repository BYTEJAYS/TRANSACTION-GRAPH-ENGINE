"""
Community intelligence — per-cluster network roll-up.

Detects the graph's communities (greedy modularity) and, for each one, derives
the operational facts an investigator asks of a sub-network: who leads it
(highest internal influence), where money ENTERS it (accounts funded from
outside), where it EXITS (accounts paying outside / cashing out), how much value
stays inside vs crosses the boundary, and how risky the community is.

Pure and additive: it reads the plain node/edge dicts `get_graph_state()`
returns and computes on demand. No detection logic leaks to the frontend.
"""
from __future__ import annotations

from typing import Any

import networkx as nx
from networkx.algorithms.community import greedy_modularity_communities


def _build(nodes: list[dict], edges: list[dict]) -> nx.DiGraph:
    G = nx.DiGraph()
    for node in nodes:
        nid = node.get("id")
        if nid is not None:
            G.add_node(str(nid))
    for e in edges:
        s, t = str(e.get("source", "")), str(e.get("target", ""))
        if not s or not t or s == t:
            continue
        amt = float(e.get("amount", 0) or 0)
        risk = float(e.get("risk_score", 0) or 0)
        flagged = bool(e.get("is_flagged", False))
        if G.has_edge(s, t):
            G[s][t]["amount"] += amt
            G[s][t]["count"] += 1
            G[s][t]["risk"] = max(G[s][t]["risk"], risk)
            G[s][t]["flagged"] = G[s][t]["flagged"] or flagged
        else:
            G.add_edge(s, t, amount=amt, count=1, risk=risk, flagged=flagged)
    return G


def _risk_level(score: float) -> str:
    if score >= 0.75:
        return "CRITICAL"
    if score >= 0.55:
        return "HIGH"
    if score >= 0.35:
        return "MEDIUM"
    return "LOW"


def _is_cash(node_id: str) -> bool:
    u = node_id.upper()
    return u.startswith("CASH") or "CASH_OUT" in u or "CASH_IN" in u


def _enrich_community(result: dict, members: set[str], edges: list[dict]) -> None:
    """
    Deep per-community intelligence, in place. Synthesizes the community as a
    component and runs the V2 engine + motif engine over it (no duplicate
    detection logic), then attaches: dominant fraud pattern, total exposure,
    suspicious amount, average layering depth, origin accounts, final
    beneficiaries, highest-risk node, an authoritative cluster risk, and a
    plain-language reasoning line. Best-effort: leaves the cheap fields intact
    if the engine cannot analyse the sub-network.
    """
    from blue_team_v2.engine import BlueTeamV2Engine
    from rule_engine import extract_motifs

    internal = [e for e in edges
                if str(e.get("source")) in members and str(e.get("target")) in members]
    if not internal:
        return
    component = {
        "graph_id": f"COMM_{result['community_id']:03d}",
        "nodes": [{"id": n} for n in members],
        "edges": internal,
    }
    try:
        engine = BlueTeamV2Engine()
        analysis = engine.analyze_component(component)
        motifs = extract_motifs(component, analysis=analysis)
    except Exception:
        return

    flagged = set(engine.flagged_nodes(analysis))
    suspicious_amount = sum(
        float(e.get("amount", 0) or 0) for e in internal
        if str(e.get("source")) in flagged or str(e.get("target")) in flagged
    )
    # dominant pattern = the strongest motif (extract_motifs returns strongest first)
    dominant = motifs[0] if motifs else None
    # average layering depth across members (depth from the cluster origin)
    depths = [m.layer_distance for m in analysis.metrics.values()]
    avg_layer = round(sum(depths) / len(depths), 2) if depths else 0.0
    highest = max(analysis.metrics.values(), key=lambda m: m.risk_score, default=None)
    ci = analysis.cluster
    origins = sorted(set(ci.origin) & members)
    beneficiaries = sorted((set(ci.cashout) | set(ci.sinks) | set(ci.terminals)) & members)

    result["risk_score"] = round(analysis.cluster_risk, 4)
    result["risk_level"] = _risk_level(analysis.cluster_risk)
    result["confidence"] = round(analysis.confidence, 3)
    result["verdict"] = analysis.verdict.value
    result["primary_classification"] = analysis.primary_classification
    result["dominant_pattern"] = (
        {"pattern": dominant["pattern"], "label": dominant["label"],
         "severity": dominant["severity"], "confidence": dominant["confidence"]}
        if dominant else None
    )
    result["fraud_patterns"] = sorted({m["pattern"] for m in motifs})
    result["motif_count"] = len(motifs)
    result["total_exposure"] = round(
        result["internal_amount"] + result["inbound_amount"] + result["outbound_amount"], 2)
    result["suspicious_amount"] = round(suspicious_amount, 2)
    result["avg_layering_depth"] = avg_layer
    result["origins"] = origins
    result["beneficiaries"] = beneficiaries
    result["highest_risk_node"] = (
        {"account": highest.node_id, "risk": round(highest.risk_score, 3),
         "role": highest.cluster_role.value} if highest else None
    )
    result["reasoning"] = analysis.narrative


def analyze_communities(
    nodes: list[dict], edges: list[dict], top: int = 25, deep: bool = True,
) -> dict[str, Any]:
    """
    Per-community intelligence for a graph snapshot.

    Returns each community's size, members, leader, entry points (funded from
    outside), exit points (paying outside / cashing out), internal vs boundary
    money volume, a 0–1 risk score with level, and the dominant role of the
    cluster (collector / distributor / relay / mixed). When `deep` is set, the
    top communities are additionally analysed with the V2 + motif engines to add
    dominant pattern, exposure, suspicious amount, layering depth, origins,
    beneficiaries, highest-risk node and reasoning. Communities are returned
    strongest-risk first. Deterministic; safe on empty input.
    """
    G = _build(nodes, edges)
    if G.number_of_nodes() == 0:
        return {"available": False, "community_count": 0, "communities": []}

    UG = G.to_undirected()
    try:
        raw = greedy_modularity_communities(UG, weight="amount")
        communities = [set(map(str, c)) for c in raw]
    except Exception:
        communities = [set(map(str, c)) for c in nx.weakly_connected_components(G)]

    # influence inside each community = PageRank restricted to the induced subgraph
    membership = {n: i for i, comm in enumerate(communities) for n in comm}

    results = []
    for cid, members in enumerate(communities):
        sub = G.subgraph(members)
        try:
            pr = nx.pagerank(sub, weight="amount") if sub.number_of_edges() else {n: 0.0 for n in members}
        except Exception:
            pr = {n: 0.0 for n in members}
        leader = max(members, key=lambda n: (pr.get(n, 0.0), G.degree(n), n)) if members else None

        internal_amount = sum(d["amount"] for u, v, d in G.edges(members, data=True)
                              if u in members and v in members)
        boundary_in = boundary_out = 0.0
        entry_points: dict[str, float] = {}
        exit_points: dict[str, float] = {}
        risk_sum = flagged = edge_n = 0.0

        for u, v, d in G.edges(data=True):
            u_in, v_in = u in members, v in members
            if u_in and v_in:
                risk_sum += d["risk"]; flagged += 1 if d["flagged"] else 0; edge_n += 1
            elif v_in and not u_in:                 # money flowing INTO the community
                boundary_in += d["amount"]
                entry_points[v] = entry_points.get(v, 0.0) + d["amount"]
            elif u_in and not v_in:                 # money flowing OUT of the community
                boundary_out += d["amount"]
                exit_points[u] = exit_points.get(u, 0.0) + d["amount"]

        # cash-out members are exits even when terminal inside the community
        for n in members:
            if _is_cash(n) or (n in G and G.out_degree(n) == 0 and G.in_degree(n) > 0):
                exit_points.setdefault(n, sum(d["amount"] for _, _, d in G.in_edges(n, data=True)))

        avg_risk = (risk_sum / edge_n) if edge_n else 0.0
        flagged_share = (flagged / edge_n) if edge_n else 0.0
        # community risk blends mean internal edge risk with the flagged share
        comm_risk = round(min(1.0, 0.7 * avg_risk + 0.3 * flagged_share), 4)

        in_deg = sum(G.in_degree(n) for n in members)
        out_deg = sum(G.out_degree(n) for n in members)
        if boundary_in > boundary_out * 1.5:
            role = "collector"
        elif boundary_out > boundary_in * 1.5:
            role = "distributor"
        elif any(_is_cash(n) for n in members):
            role = "cash-out"
        elif internal_amount > (boundary_in + boundary_out):
            role = "relay"
        else:
            role = "mixed"

        def _rank(d: dict[str, float], k: int = 5) -> list[dict]:
            return [{"account": a, "amount": round(v, 2)}
                    for a, v in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]

        results.append({
            "community_id": cid,
            "size": len(members),
            "members": sorted(members),
            "leader": leader,
            "role": role,
            "entry_points": _rank(entry_points),
            "exit_points": _rank(exit_points),
            "internal_amount": round(internal_amount, 2),
            "inbound_amount": round(boundary_in, 2),
            "outbound_amount": round(boundary_out, 2),
            "internal_edges": int(edge_n),
            "in_degree": in_deg,
            "out_degree": out_deg,
            "flagged_share": round(flagged_share, 4),
            "risk_score": comm_risk,
            "risk_level": _risk_level(comm_risk),
        })

    results.sort(key=lambda c: (c["risk_score"], c["size"]), reverse=True)
    shown = results[:top]

    # Deep-enrich only the communities we return (bounds engine runs to `top`),
    # then re-sort by the authoritative engine risk.
    if deep:
        for r in shown:
            _enrich_community(r, set(r["members"]), edges)
        shown.sort(key=lambda c: (c["risk_score"], c["size"]), reverse=True)

    return {
        "available": True,
        "community_count": len(results),
        "node_membership": membership,
        "communities": shown,
    }
