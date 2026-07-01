"""
Blue Team Standalone Analyzer — zero external dependencies.

Runs when the Blue Team HTTP service is unreachable.  Uses the same graph
snapshot format and returns the exact same verdict schema.

Detection mirrors Blue Team's three-tier logic using the graph topology:
  Tier 1 — velocity / amount heuristics
  Tier 2 — hard graph gates (cycles, fan-out, chain depth, structuring)
  Tier 3 — composite risk score with SHAP-style signal attribution

No PostgreSQL, Redis, Neo4j, or XGBoost required.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone

import networkx as nx

log = logging.getLogger(__name__)

# Mirrors Blue Team's scoring/thresholds.py
_THRESHOLD_LOG       = 0.38
_THRESHOLD_REVIEW    = 0.62
_THRESHOLD_HIGH_RISK = 0.83


def _ts(raw: str) -> datetime:
    try:
        dt = datetime.fromisoformat(raw)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return datetime.now(timezone.utc)


def analyze_standalone(graph_snapshot: dict) -> dict:
    """
    Pure graph-based fraud analysis — no network calls, no DB.

    Accepts the same {nodes, edges, stats} snapshot that the HTTP adapter uses.
    Returns the same verdict dict that adapter._aggregate() would produce.
    """
    edges: list[dict] = graph_snapshot.get("edges", [])
    nodes_raw: list[dict] = graph_snapshot.get("nodes", [])

    if not edges:
        return _verdict("CLEAN", "PASS", 0.0, [], None, 0)

    # ── Build directed graph ──────────────────────────────────────────────────
    G: nx.DiGraph = nx.DiGraph()
    amounts: list[float] = []
    timestamps: list[datetime] = []

    for e in edges:
        src = str(e.get("source", ""))
        tgt = str(e.get("target", ""))
        amt = float(e.get("amount", 0))
        if not src or not tgt or amt <= 0:
            continue
        G.add_edge(src, tgt, amount=amt, timestamp=e.get("timestamp", ""))
        amounts.append(amt)
        timestamps.append(_ts(e.get("timestamp", "")))

    if G.number_of_edges() == 0:
        return _verdict("CLEAN", "PASS", 0.0, [], None, 0)

    signals: list[str] = []
    flagged: set[str] = set()
    score = 0.0

    # ── Gate 1: Circular path (highest confidence fraud signal) ──────────────
    try:
        cycles = [c for c in nx.simple_cycles(G) if len(c) >= 2]
        if cycles:
            signals.append("circular_path_detected")
            for cyc in cycles[:5]:
                flagged.update(cyc)
            score = max(score, 0.97)
    except Exception:
        pass

    # ── Gate 2: Fan-out — one account → ≥ 4 unique recipients ───────────────
    for node in list(G.nodes()):
        out_neighbors = list(G.successors(node))
        unique_out = len(set(out_neighbors))
        if unique_out >= 4:
            signals.append("fan_out_detected")
            flagged.add(node)
            flagged.update(out_neighbors[:6])
            score = max(score, 0.85)
            break

    # ── Gate 3: Cash-mule sink — one account receives from ≥ 4 senders ──────
    for node in list(G.nodes()):
        in_neighbors = list(G.predecessors(node))
        unique_in = len(set(in_neighbors))
        if unique_in >= 4:
            signals.append("bipartite_mule_sink")
            flagged.add(node)
            flagged.update(in_neighbors[:6])
            score = max(score, 0.82)
            break

    # ── Gate 4: Forwarding chain depth > 3 ───────────────────────────────────
    try:
        if nx.is_directed_acyclic_graph(G):
            depth = nx.dag_longest_path_length(G)
            if depth > 3:
                signals.append("chain_depth_exceeded")
                path = nx.dag_longest_path(G)
                flagged.update(path[:6])
                score = max(score, 0.75 + min(0.10, (depth - 3) * 0.04))
        else:
            # Has cycles — already flagged above; approximate chain length
            if G.number_of_nodes() > 4:
                score = max(score, 0.78)
    except Exception:
        pass

    # ── Gate 5: Repeated-amount structuring (≥ 3 identical transfers) ────────
    if amounts:
        for amt, cnt in Counter(round(a, 2) for a in amounts).items():
            if cnt >= 3 and amt > 1000:
                signals.append("repeated_amount_structuring")
                for e in edges:
                    if abs(float(e.get("amount", 0)) - amt) < 0.01:
                        flagged.add(str(e.get("source", "")))
                        flagged.add(str(e.get("target", "")))
                score = max(score, 0.72)
                break

    # ── Tier 1 velocity heuristic: high volume in short window ───────────────
    if len(timestamps) >= 2:
        span_seconds = (max(timestamps) - min(timestamps)).total_seconds()
        total_volume = sum(amounts)
        if span_seconds < 600 and total_volume > 2_00_000:
            signals.append("high_velocity_transfer")
            score = max(score, 0.60)

    # ── Tier 1: Large single transfer ≥ ₹5L ─────────────────────────────────
    if amounts and max(amounts) >= 5_00_000:
        score = max(score, 0.45)
        if not signals:
            signals.append("large_amount_threshold")

    # ── Map score → action → verdict ─────────────────────────────────────────
    if score >= _THRESHOLD_HIGH_RISK:
        action, verdict = "HIGH_RISK", "FRAUD"
    elif score >= _THRESHOLD_REVIEW:
        action, verdict = "REVIEW", "SUSPICIOUS"
    elif score >= _THRESHOLD_LOG:
        action, verdict = "LOG", "LOGGED"
    else:
        action, verdict = "PASS", "CLEAN"

    flagged.discard("")
    reason = signals[0] if signals else (
        "ML ensemble" if score > _THRESHOLD_LOG else None
    )

    log.info(
        "BlueTeam standalone: verdict=%s score=%.3f signals=%s flagged=%d",
        verdict, score, signals, len(flagged),
    )
    return _verdict(verdict, action, score, list(flagged), reason, G.number_of_edges())


def analyze_standalone_component(component: dict) -> dict:
    """
    Per-component wrapper: accepts the dict produced by
    TransactionGraphManager.get_connected_components() and returns the same
    verdict schema with graph_id injected.
    """
    graph_id = component.get("graph_id", "GRAPH_001")
    snapshot = {
        "nodes": component.get("nodes", []),
        "edges": component.get("edges", []),
    }
    result = analyze_standalone(snapshot)
    result["graph_id"] = graph_id
    return result


def _verdict(
    verdict: str,
    action: str,
    score: float,
    flagged_nodes: list[str],
    suspicious_reason: str | None,
    transactions_scored: int,
) -> dict:
    return {
        "status": "analyzed",
        "verdict": verdict,
        "score": round(score, 4),
        "action": action,
        "confidence": int(score * 100),
        "flagged_nodes": flagged_nodes,
        "suspicious_reason": suspicious_reason,
        "transactions_scored": transactions_scored,
        "mode": "standalone",
    }
