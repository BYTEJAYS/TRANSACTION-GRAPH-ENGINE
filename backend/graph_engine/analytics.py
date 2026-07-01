"""
Graph analytics engine — server-computed network intelligence.

Exposes the structural analytics an investigator needs but that the live graph
payload never carried: influence ranking (PageRank / HITS / eigenvector),
density and component structure, bridges / cut vertices, fund-flow rankings
(who aggregates, who distributes, top sources and beneficiaries), and path
intelligence (shortest, highest-risk and largest-value money paths).

Like the layout engine it is pure and additive: it takes the plain node/edge
dicts `get_graph_state()` already returns and computes on demand. No business
logic leaks to the frontend — the frontend only renders these results.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

import networkx as nx


# ── construction ─────────────────────────────────────────────────────────────
def _build(nodes: list[dict], edges: list[dict]) -> nx.DiGraph:
    """Weighted directed graph; edges aggregate amount, transfer count, max risk."""
    G = nx.DiGraph()
    for n in nodes:
        nid = n.get("id")
        if nid is not None:
            G.add_node(str(nid))
    for e in edges:
        s, t = str(e.get("source", "")), str(e.get("target", ""))
        if not s or not t or s == t:
            continue
        amt = float(e.get("amount", 0) or 0)
        risk = float(e.get("risk_score", 0) or 0)
        if G.has_edge(s, t):
            G[s][t]["amount"] += amt
            G[s][t]["count"] += 1
            G[s][t]["risk"] = max(G[s][t]["risk"], risk)
        else:
            G.add_edge(s, t, amount=amt, count=1, risk=risk)
    return G


def _rank(value_map: dict[str, float], top: int = 10, ndigits: int = 4) -> list[dict]:
    """Top-N accounts by value, descending, deterministic on ties (account id)."""
    ranked = sorted(value_map.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"account": n, "value": round(v, ndigits)} for n, v in ranked[:top] if v > 0]


# ── full analytics ───────────────────────────────────────────────────────────
def compute_analytics(nodes: list[dict], edges: list[dict], top: int = 10) -> dict[str, Any]:
    """Compute the full analytics bundle for a graph snapshot."""
    G = _build(nodes, edges)
    n, m = G.number_of_nodes(), G.number_of_edges()
    if n == 0:
        return {"summary": {"node_count": 0, "edge_count": 0}, "available": False}

    UG = G.to_undirected()

    # ── influence / centrality ──
    try:
        pagerank = nx.pagerank(G, weight="amount")
    except Exception:
        pagerank = {x: 0.0 for x in G.nodes()}
    try:
        hubs, authorities = nx.hits(G, max_iter=500, normalized=True)
    except Exception:
        hubs = authorities = {x: 0.0 for x in G.nodes()}
    try:
        eigen = nx.eigenvector_centrality_numpy(G, weight="amount") if m else {x: 0.0 for x in G.nodes()}
    except Exception:
        eigen = {x: 0.0 for x in G.nodes()}
    betweenness = (nx.betweenness_centrality(G, normalized=True)
                   if n <= 1500
                   else nx.betweenness_centrality(G, k=min(400, n), normalized=True, seed=42))

    # ── component structure ──
    scc = list(nx.strongly_connected_components(G))
    wcc = list(nx.weakly_connected_components(G))
    try:
        bridges = [[u, v] for u, v in nx.bridges(UG)]
    except Exception:
        bridges = []
    try:
        articulation = sorted(nx.articulation_points(UG))
    except Exception:
        articulation = []

    # ── degree distribution ──
    deg_hist = Counter(dict(G.degree()).values())
    degree_distribution = {str(k): v for k, v in sorted(deg_hist.items())}

    # ── fund-flow rankings ──
    in_vol = {x: sum(d["amount"] for _, _, d in G.in_edges(x, data=True)) for x in G.nodes()}
    out_vol = {x: sum(d["amount"] for _, _, d in G.out_edges(x, data=True)) for x in G.nodes()}
    # aggregators collect from many (fan-in × inflow); distributors split to many
    aggregation = {x: in_vol[x] * G.in_degree(x) for x in G.nodes()}
    distribution = {x: out_vol[x] * G.out_degree(x) for x in G.nodes()}
    influence = {x: 0.5 * pagerank.get(x, 0) + 0.3 * authorities.get(x, 0) + 0.2 * betweenness.get(x, 0)
                 for x in G.nodes()}

    return {
        "available": True,
        "summary": {
            "node_count": n,
            "edge_count": m,
            "density": round(nx.density(G), 5),
            "reciprocity": round(nx.reciprocity(G) or 0.0, 4) if m else 0.0,
            "avg_degree": round(2 * m / n, 3),
            "strongly_connected_components": len(scc),
            "weakly_connected_components": len(wcc),
            "largest_scc_size": max((len(c) for c in scc), default=0),
            "cycle_count": sum(1 for c in scc if len(c) > 1),
            "bridge_count": len(bridges),
            "articulation_point_count": len(articulation),
        },
        "influence_ranking": _rank(influence, top),
        "centrality": {
            "pagerank": _rank(pagerank, top),
            "hubs": _rank(hubs, top),
            "authorities": _rank(authorities, top),
            "eigenvector": _rank(eigen, top),
            "betweenness": _rank(betweenness, top),
        },
        "fund_flow": {
            "top_sources": _rank(out_vol, top, ndigits=2),
            "top_beneficiaries": _rank(in_vol, top, ndigits=2),
            "top_aggregators": _rank(aggregation, top, ndigits=2),
            "top_distributors": _rank(distribution, top, ndigits=2),
        },
        "structure": {
            "bridges": bridges[:50],
            "articulation_points": articulation[:50],
            "degree_distribution": degree_distribution,
        },
    }


# ── path intelligence ────────────────────────────────────────────────────────
def analyze_paths(
    nodes: list[dict],
    edges: list[dict],
    source: str,
    target: str,
    cutoff: int = 8,
    max_paths: int = 500,
) -> dict[str, Any]:
    """
    Money-path intelligence between two accounts:
      shortest        — fewest hops
      highest_risk    — maximises total edge risk along the path
      largest_amount  — maximises total transferred value along the path
      bottleneck      — path whose weakest (smallest) hop is largest (max-flow-ish)
    """
    G = _build(nodes, edges)
    if source not in G or target not in G:
        return {"available": False, "reason": "source or target not in graph"}

    try:
        shortest = nx.shortest_path(G, source, target)
    except nx.NetworkXNoPath:
        return {"available": True, "connected": False, "source": source, "target": target}

    def _edges(path):
        return [G[path[i]][path[i + 1]] for i in range(len(path) - 1)]

    def _summ(path):
        es = _edges(path)
        return {
            "path": path,
            "hops": len(path) - 1,
            "total_amount": round(sum(e["amount"] for e in es), 2),
            "min_amount": round(min((e["amount"] for e in es), default=0), 2),
            "total_risk": round(sum(e["risk"] for e in es), 4),
            "avg_risk": round(sum(e["risk"] for e in es) / len(es), 4) if es else 0.0,
        }

    # Enumerate simple paths up to a bounded length/count, then optimise.
    best_risk = best_amount = best_bottleneck = None
    seen = 0
    for path in nx.all_simple_paths(G, source, target, cutoff=cutoff):
        es = _edges(path)
        total_risk = sum(e["risk"] for e in es)
        total_amt = sum(e["amount"] for e in es)
        bottleneck = min((e["amount"] for e in es), default=0)
        if best_risk is None or total_risk > sum(e["risk"] for e in _edges(best_risk)):
            best_risk = path
        if best_amount is None or total_amt > sum(e["amount"] for e in _edges(best_amount)):
            best_amount = path
        if best_bottleneck is None or bottleneck > min((e["amount"] for e in _edges(best_bottleneck)), default=0):
            best_bottleneck = path
        seen += 1
        if seen >= max_paths:
            break

    # Most-layered route = the simple path with the most hops (deepest layering).
    best_layered = max(
        (p for p in (shortest, best_risk, best_amount, best_bottleneck) if p),
        key=len, default=shortest,
    )

    shortest_s = _summ(shortest)
    risk_s = _summ(best_risk) if best_risk else None
    amount_s = _summ(best_amount) if best_amount else None

    return {
        "available": True,
        "connected": True,
        "source": source,
        "target": target,
        "paths_examined": seen,
        "shortest": shortest_s,
        "highest_risk": risk_s,
        "largest_amount": amount_s,
        "most_layered": _summ(best_layered) if best_layered else None,
        "bottleneck": _summ(best_bottleneck) if best_bottleneck else None,
        "triggered_rules": _path_rules(amount_s or shortest_s, target),
        "narrative": _path_narrative(source, target, shortest_s, risk_s, amount_s),
    }


# ── path narratives (plain-language money-trail descriptions) ──────────────────
def _money(x: float) -> str:
    return f"₹{x:,.0f}"


def _path_rules(summ: dict | None, target: str | None = None) -> list[dict]:
    """Infer the AML rule(s) a path's shape triggers (layering depth, cash-out)."""
    from rule_engine import rules_for

    if not summ:
        return []
    patterns: list[str] = []
    if summ.get("hops", 0) >= 3:
        patterns.append("layering")          # AML020 — deep mid-chain forwarding
    if summ.get("hops", 0) >= 4:
        patterns.append("nested_layering")   # AML004
    if target and str(target).upper().startswith("CASH"):
        patterns.append("cashout")           # AML011
    out, seen = [], set()
    for p in patterns:
        for rule in rules_for(p):
            if rule["rule_id"] not in seen:
                seen.add(rule["rule_id"])
                out.append(rule)
    return out


def _path_narrative(source, target, shortest, risk, amount) -> str:
    """One-paragraph plain-language description of how money moves source→target."""
    parts = [
        f"The shortest route from {source} to {target} is {shortest['hops']} hop(s) "
        f"(via {' → '.join(shortest['path'])}), moving {_money(shortest['total_amount'])}."
    ]
    if amount and amount["path"] != shortest["path"]:
        parts.append(
            f"The largest-value route carries {_money(amount['total_amount'])} over "
            f"{amount['hops']} hop(s), indicating funds are routed through "
            f"{amount['hops'] - 1} intermediary account(s) rather than sent directly."
        )
    if risk and risk["path"] != shortest["path"]:
        parts.append(
            f"The highest-risk route ({' → '.join(risk['path'])}) has an average edge "
            f"risk of {risk['avg_risk']:.2f}, suggesting a deliberate layering path."
        )
    return " ".join(parts)


# ── graph-level money-flow narration ───────────────────────────────────────────
def _is_cash(node_id: str) -> bool:
    return str(node_id).upper().startswith(("CASH", "CASH_OUT", "CASH_IN"))


def narrate_flows(nodes: list[dict], edges: list[dict], max_routes: int = 5) -> dict[str, Any]:
    """
    Graph-level money-trail narration: the most-layered route (deepest chain of
    forwarding hops) and the cash-out routes (highest-value paths from an entry
    source to a terminal / cash-out sink), each with hop count, value, triggered
    AML rules and a plain-language narrative.

    Deterministic and bounded; safe on empty input.
    """
    G = _build(nodes, edges)
    if G.number_of_nodes() == 0:
        return {"available": False, "reason": "empty graph"}

    sources = [n for n in G.nodes() if G.in_degree(n) == 0 and G.out_degree(n) > 0]
    sinks = [n for n in G.nodes() if G.out_degree(n) == 0 and G.in_degree(n) > 0]
    cash_sinks = [n for n in G.nodes() if _is_cash(n)]
    terminal_sinks = sorted(set(sinks) | set(cash_sinks))

    def _edges(path):
        return [G[path[i]][path[i + 1]] for i in range(len(path) - 1)]

    def _summ(path):
        es = _edges(path)
        return {
            "path": path,
            "hops": len(path) - 1,
            "total_amount": round(sum(e["amount"] for e in es), 2),
            "avg_risk": round(sum(e["risk"] for e in es) / len(es), 4) if es else 0.0,
        }

    # ── most-layered route: longest chain of forwarding hops ──
    most_layered = None
    try:
        if nx.is_directed_acyclic_graph(G):
            lp = nx.dag_longest_path(G)
            most_layered = lp if len(lp) > 1 else None
        else:
            # cycles present: search bounded simple paths from each source
            best = []
            for s in (sources or sorted(G.nodes())[:20]):
                for t in (terminal_sinks or sorted(G.nodes())[:20]):
                    if s == t:
                        continue
                    try:
                        for p in nx.all_simple_paths(G, s, t, cutoff=12):
                            if len(p) > len(best):
                                best = p
                    except nx.NetworkXNoPath:
                        continue
            most_layered = best or None
    except Exception:
        most_layered = None

    # ── cash-out routes: highest-value source→terminal path per sink ──
    cashout_routes = []
    for sink in terminal_sinks[: max_routes * 2]:
        best_path, best_val = None, -1.0
        for s in (sources or sorted(G.nodes())[:15]):
            if s == sink:
                continue
            try:
                for p in nx.all_simple_paths(G, s, sink, cutoff=10):
                    val = sum(e["amount"] for e in _edges(p))
                    if val > best_val:
                        best_val, best_path = val, p
            except nx.NetworkXNoPath:
                continue
        if best_path:
            summ = _summ(best_path)
            cashout_routes.append({
                **summ,
                "destination": sink,
                "is_cash": _is_cash(sink),
                "triggered_rules": _path_rules(summ, sink),
                "narrative": (
                    f"{_money(summ['total_amount'])} reaches {sink} "
                    f"{'(cash-out)' if _is_cash(sink) else '(terminal account)'} "
                    f"over {summ['hops']} hop(s) via {' → '.join(best_path)}."
                ),
            })
    cashout_routes.sort(key=lambda r: r["total_amount"], reverse=True)
    cashout_routes = cashout_routes[:max_routes]

    layered_summ = _summ(most_layered) if most_layered else None
    layered_block = None
    if layered_summ:
        layered_block = {
            **layered_summ,
            "triggered_rules": _path_rules(layered_summ, most_layered[-1]),
            "narrative": (
                f"The deepest layering chain runs {layered_summ['hops']} hop(s): "
                f"{' → '.join(most_layered)}, forwarding {_money(layered_summ['total_amount'])} "
                f"through {max(0, layered_summ['hops'] - 1)} intermediary account(s)."
            ),
        }

    story = _compose_investigation_narrative(
        G, sources, terminal_sinks, most_layered, layered_summ,
    )

    return {
        "available": True,
        "source_count": len(sources),
        "sink_count": len(terminal_sinks),
        "most_layered": layered_block,
        "cashout_routes": cashout_routes,
        "cashout_route_count": len(cashout_routes),
        "summary_narrative": story["narrative"],
        "stages": story["stages"],
        "assessment": story["assessment"],
    }


def _compose_investigation_narrative(
    G: nx.DiGraph,
    sources: list[str],
    terminal_sinks: list[str],
    most_layered: list[str] | None,
    layered_summ: dict | None,
) -> dict[str, Any]:
    """
    Build an investigator-report-style money story from the graph's structure:
    origin → split (fan-out) → re-aggregation (fan-in) → topology → layering /
    shell chain → recycling → exit (cash-out) → assessment. Each stage that is
    present contributes one plain-language sentence and a structured entry.
    """
    out_vol = {n: sum(d["amount"] for _, _, d in G.out_edges(n, data=True)) for n in G.nodes()}
    sentences: list[str] = []
    stages: list[dict] = []

    # ── Stage 1 — Origin ──
    originated = round(sum(out_vol[s] for s in sources), 2)
    if sources:
        head = sources[:3]
        more = f" and {len(sources) - 3} other source(s)" if len(sources) > 3 else ""
        sentences.append(
            f"Funds originated from {', '.join(sorted(head))}{more}, "
            f"introducing {_money(originated)} into the network.")
        stages.append({"stage": "origin", "accounts": sorted(sources)[:10],
                       "amount": originated})

    # ── Stage 2 — Split / fan-out ──
    fan_out = max(G.nodes(), key=lambda n: G.out_degree(n), default=None)
    if fan_out is not None and G.out_degree(fan_out) >= 3:
        k = G.out_degree(fan_out)
        sentences.append(f"From {fan_out} the funds were split across {k} accounts (fan-out distribution).")
        stages.append({"stage": "fan_out", "account": fan_out, "ways": k})

    # ── Stage 3 — Re-aggregation / collection ──
    collector = max(G.nodes(), key=lambda n: G.in_degree(n), default=None)
    if collector is not None and G.in_degree(collector) >= 3:
        k = G.in_degree(collector)
        sentences.append(f"They were re-aggregated through {collector}, which collected from {k} accounts.")
        stages.append({"stage": "collection", "account": collector, "sources": k})

    # ── Topology — diamond (split then reconverge) ──
    has_diamond = (fan_out is not None and collector is not None
                   and G.out_degree(fan_out) >= 2 and G.in_degree(collector) >= 2
                   and fan_out != collector and nx.has_path(G, fan_out, collector))
    if has_diamond:
        sentences.append("The network formed a split-reconverge (diamond) laundering topology.")
        stages.append({"stage": "topology", "pattern": "diamond",
                       "from": fan_out, "to": collector})

    # ── Stage 4/5 — Layering / shell chain ──
    if layered_summ and layered_summ["hops"] >= 3 and most_layered:
        shells = max(0, layered_summ["hops"] - 1)
        sentences.append(
            f"The money then travelled through a {layered_summ['hops']}-hop layering chain "
            f"({' → '.join(most_layered)}), passing {shells} intermediary / shell entit"
            f"{'y' if shells == 1 else 'ies'}.")
        stages.append({"stage": "layering", "depth": layered_summ["hops"],
                       "chain": most_layered, "shells": shells})

    # ── Recycling — cycle present ──
    has_cycle = not nx.is_directed_acyclic_graph(G)
    if has_cycle:
        sentences.append("One branch recycled funds back through a cycle (round-tripping).")
        stages.append({"stage": "recycle", "pattern": "circular_flow"})

    # ── Stage 6 — Exit / cash-out ──
    cash_exits = sorted(s for s in terminal_sinks if _is_cash(s))
    if cash_exits:
        sentences.append(f"Funds exited the banking network via {', '.join(cash_exits[:5])} (cash-out).")
        stages.append({"stage": "cashout", "accounts": cash_exits[:10]})
    elif terminal_sinks:
        sentences.append(f"Funds settled at terminal account(s) {', '.join(sorted(terminal_sinks)[:5])}.")
        stages.append({"stage": "exit", "accounts": sorted(terminal_sinks)[:10]})

    # ── Assessment ──
    deep = bool(layered_summ and layered_summ["hops"] >= 3)
    signals = sum([deep, has_cycle, bool(cash_exits), has_diamond])
    if signals >= 3:
        assessment = "This behaviour strongly matches multi-stage money laundering."
    elif signals == 2:
        assessment = "This behaviour is consistent with structured layering activity."
    elif signals == 1:
        assessment = "This behaviour shows isolated indicators warranting review."
    else:
        assessment = "No strong multi-stage laundering structure is evident from the flow alone."
    sentences.append(assessment)

    return {"narrative": " ".join(sentences), "stages": stages, "assessment": assessment}
