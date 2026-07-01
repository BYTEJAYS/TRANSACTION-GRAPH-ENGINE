"""
AML Rule + Motif engine.

The Blue Team V2 detectors already produce rich `Evidence` (pattern, nodes,
severity, confidence, structured data). What an investigator — and a Union Bank
evaluator — needs on top of that is:

  1. a NAMED, reusable rule catalogue (AML001, AML002 …) every finding maps to,
     so an alert can be traced to a specific, auditable rule; and
  2. explicit FRAUD MOTIF objects: each detected structure returned as a
     self-describing object carrying its nodes, the sub-graph edges that form it,
     the rule(s) it triggered, supporting evidence, and a plain-language
     explanation.

This module is a thin, algorithmic projection over the existing detector
output — it adds no new hard-coded detection. It reuses `BlueTeamV2Engine`.
"""
from __future__ import annotations

from typing import Any

# ── Reusable AML rule catalogue ──────────────────────────────────────────────
# severity is the INTRINSIC weight of the rule; the firing motif's measured
# severity/confidence still come from the detector evidence.
RULES: dict[str, dict[str, Any]] = {
    "AML001": {"name": "Fan-Out Distribution", "category": "Layering", "severity": "HIGH",
               "description": "One account disperses funds to many recipients in a short window."},
    "AML002": {"name": "Fan-In Collection", "category": "Integration", "severity": "HIGH",
               "description": "Many accounts funnel funds into a single collector."},
    "AML003": {"name": "Diamond Split-Reconverge", "category": "Layering", "severity": "HIGH",
               "description": "Funds split across intermediaries then reconverge on one node."},
    "AML004": {"name": "Nested Layering", "category": "Layering", "severity": "CRITICAL",
               "description": "Multiple sequential forwarding hops obscure the money trail."},
    "AML005": {"name": "Circular Layering / Round-Tripping", "category": "Layering", "severity": "CRITICAL",
               "description": "Funds return to an originating account through a cycle."},
    "AML006": {"name": "Smurfing", "category": "Placement", "severity": "HIGH",
               "description": "A large value is broken into many small structured transfers."},
    "AML007": {"name": "Structuring / Threshold Avoidance", "category": "Placement", "severity": "HIGH",
               "description": "Amounts sit just below regulatory reporting thresholds."},
    "AML008": {"name": "Money Mule / Pass-Through", "category": "Layering", "severity": "HIGH",
               "description": "Account receives and rapidly forwards near-equal value."},
    "AML009": {"name": "Bridge / Articulation Relay", "category": "Structure", "severity": "MEDIUM",
               "description": "A cut-vertex links otherwise separate sub-networks."},
    "AML010": {"name": "High-Velocity Transfers", "category": "Behaviour", "severity": "HIGH",
               "description": "Value moves through the account faster than baseline."},
    "AML011": {"name": "Cash-Out", "category": "Integration", "severity": "CRITICAL",
               "description": "Funds exit the banking network to cash/external rails."},
    "AML012": {"name": "Dormant Account Activation", "category": "Behaviour", "severity": "MEDIUM",
               "description": "A long-inactive account suddenly transacts at volume."},
    "AML013": {"name": "Synthetic Identity Network", "category": "Structure", "severity": "CRITICAL",
               "description": "A cluster of accounts shows fabricated-identity signatures."},
    "AML014": {"name": "Hub Concentration", "category": "Structure", "severity": "HIGH",
               "description": "A single hub intermediates a disproportionate share of flow."},
    "AML015": {"name": "Scatter-Gather", "category": "Layering", "severity": "HIGH",
               "description": "Funds scatter to many accounts then gather to few."},
    "AML016": {"name": "Off-Hours / Night Activity", "category": "Behaviour", "severity": "LOW",
               "description": "Material activity concentrated in night-time hours."},
    "AML017": {"name": "Weekend Activity", "category": "Behaviour", "severity": "LOW",
               "description": "Material activity concentrated on weekends."},
    "AML018": {"name": "Temporal Spike / Burst", "category": "Behaviour", "severity": "MEDIUM",
               "description": "A sudden burst of transactions in a tight window."},
    "AML019": {"name": "Hybrid Laundering Network", "category": "Composite", "severity": "CRITICAL",
               "description": "Several independent laundering techniques co-occur in one cluster."},
    "AML020": {"name": "Layering Depth", "category": "Layering", "severity": "HIGH",
               "description": "Deep mid-chain forwarding consistent with the layering stage."},
    "AML021": {"name": "Uniform-Amount Repetition", "category": "Placement", "severity": "MEDIUM",
               "description": "Repeated identical amounts indicate automated structuring."},
    "AML022": {"name": "Star / Wheel Hub", "category": "Structure", "severity": "HIGH",
               "description": "A single hub radiates to many leaf accounts (star); rim links between them form a wheel."},
    "AML023": {"name": "Hourglass Convergence-Divergence", "category": "Layering", "severity": "HIGH",
               "description": "Many accounts converge on one waist account that then diverges to many — a fan-in then fan-out through a single chokepoint."},
    "AML024": {"name": "Double-Diamond Layering", "category": "Layering", "severity": "CRITICAL",
               "description": "Two split-reconverge diamonds chained in sequence — repeated layering to obscure the trail."},
}

# Detector pattern name → triggered rule id(s).
PATTERN_TO_RULES: dict[str, list[str]] = {
    "fan_out": ["AML001"],
    "fan_in": ["AML002"],
    "diamond": ["AML003"],
    "nested_layering": ["AML004"],
    "circular_flow": ["AML005"],
    "round_tripping": ["AML005"],
    "smurfing": ["AML006"],
    "structuring": ["AML007"],
    "mule_accounts": ["AML008"],
    "bridge_accounts": ["AML009"],
    "velocity": ["AML010"],
    "cashout": ["AML011"],
    "cash_laundering": ["AML011"],
    "dormant_accounts": ["AML012"],
    "synthetic_networks": ["AML013"],
    "hub_network": ["AML014"],
    "scatter_gather": ["AML015"],
    "night_activity": ["AML016"],
    "weekend_activity": ["AML017"],
    "temporal_spike": ["AML018"],
    "hybrid_network": ["AML019"],
    "layering": ["AML020"],
    "uniform_amount": ["AML021"],
    "star": ["AML022"],
    "wheel": ["AML022", "AML005"],     # wheel = star hub + a rim cycle
    "hourglass": ["AML023", "AML002", "AML001"],
    "double_diamond": ["AML024", "AML003"],
}

# Canonical investigator-facing motif label per detector pattern.
MOTIF_LABEL: dict[str, str] = {
    "fan_out": "Fan-Out", "fan_in": "Fan-In", "diamond": "Diamond",
    "nested_layering": "Nested Layering", "circular_flow": "Circular Layering",
    "round_tripping": "Round-Tripping", "smurfing": "Smurfing",
    "structuring": "Structuring", "mule_accounts": "Money Mule",
    "bridge_accounts": "Bridge Relay", "velocity": "Velocity Pattern",
    "cashout": "Cash-Out", "cash_laundering": "Cash Laundering",
    "dormant_accounts": "Dormant Activation", "synthetic_networks": "Synthetic Network",
    "hub_network": "Hub", "scatter_gather": "Scatter-Gather",
    "night_activity": "Night Activity", "weekend_activity": "Weekend Activity",
    "temporal_spike": "Temporal Spike", "hybrid_network": "Hybrid Network",
    "layering": "Layering", "uniform_amount": "Round-Amount Pattern",
    "star": "Star Hub", "wheel": "Wheel", "hourglass": "Hourglass",
    "double_diamond": "Double Diamond",
}


def severity_label(score: float) -> str:
    if score >= 0.85:
        return "CRITICAL"
    if score >= 0.65:
        return "HIGH"
    if score >= 0.40:
        return "MEDIUM"
    return "LOW"


def rules_for(pattern: str) -> list[dict[str, Any]]:
    """Resolve the AML rule object(s) a detector pattern triggers."""
    out = []
    for rid in PATTERN_TO_RULES.get(pattern, []):
        meta = RULES.get(rid)
        if meta:
            out.append({"rule_id": rid, **meta})
    return out


def _edges_among(nodes: set[str], comp_edges: list[dict]) -> list[dict]:
    """The sub-graph edges that actually form a motif (both endpoints inside it)."""
    out = []
    for e in comp_edges:
        if e.get("source") in nodes and e.get("target") in nodes:
            out.append({
                "source": e.get("source"), "target": e.get("target"),
                "amount": e.get("amount", 0), "payment_rail": e.get("payment_rail"),
                "timestamp": e.get("timestamp", ""), "risk_score": e.get("risk_score", 0),
            })
    return out


def extract_topology_motifs(component: dict) -> list[dict[str, Any]]:
    """
    Detect higher-order graph TOPOLOGY motifs the per-pattern detectors don't
    name explicitly: Star / Wheel hubs, Hourglass (fan-in→fan-out through one
    waist) and Double-Diamond (two chained split-reconverge diamonds). Pure
    structural projection over the component graph; each motif is returned in the
    same self-describing shape as `extract_motifs`. Fires only on clear
    structure, so small/empty components yield nothing.
    """
    import networkx as nx

    comp_edges = component.get("edges", [])
    graph_id = component.get("graph_id", "GRAPH_001")
    G = nx.DiGraph()
    for e in comp_edges:
        s, t = e.get("source"), e.get("target")
        if s and t and s != t:
            G.add_edge(s, t)
    if G.number_of_nodes() < 4:
        return []
    UG = G.to_undirected()
    motifs: list[dict[str, Any]] = []

    def _add(pattern: str, nodes: set[str], severity: float, confidence: float, explanation: str):
        idx = sum(1 for m in motifs if m["pattern"] == pattern) + 1
        motifs.append({
            "motif_id": f"{graph_id}-{pattern}-{idx}",
            "graph_id": graph_id,
            "pattern": pattern,
            "label": MOTIF_LABEL.get(pattern, pattern.replace("_", " ").title()),
            "title": MOTIF_LABEL.get(pattern, pattern),
            "confidence": round(confidence, 3),
            "severity": severity_label(severity),
            "severity_score": round(severity, 3),
            "nodes": sorted(nodes),
            "edges": _edges_among(nodes, comp_edges),
            "triggered_rules": rules_for(pattern),
            "evidence": {"node_count": len(nodes)},
            "explanation": explanation,
        })

    # ── Star / Wheel: a hub with ≥4 leaf spokes ──
    for c in G.nodes():
        spokes = set(UG.neighbors(c))
        if len(spokes) < 4:
            continue
        leaves = [s for s in spokes if UG.degree(s) <= 2]
        if len(leaves) < 4:
            continue
        rim = sum(1 for a in spokes for b in spokes if a < b and UG.has_edge(a, b))
        nodes = {c} | spokes
        if rim >= max(3, len(spokes) // 2):
            _add("wheel", nodes, 0.72, 0.7,
                 f"{c} is the hub of a wheel: {len(spokes)} spokes with {rim} rim link(s) between them.")
        else:
            _add("star", nodes, 0.6, 0.7,
                 f"{c} is a star hub radiating to {len(leaves)} leaf account(s).")

    # ── Hourglass: a waist with ≥2 distinct sources and ≥2 distinct sinks ──
    for w in G.nodes():
        preds, succs = set(G.predecessors(w)), set(G.successors(w))
        if len(preds) >= 2 and len(succs) >= 2 and preds.isdisjoint(succs):
            nodes = preds | {w} | succs
            _add("hourglass", nodes, 0.7, 0.75,
                 f"{len(preds)} account(s) converge on {w}, which then diverges to {len(succs)} account(s).")

    # ── Double-Diamond: an upstream diamond reconverges on a waist that then
    #    splits into a downstream diamond (split→merge[=waist]→split→merge). ──
    waists = [n for n in G.nodes() if G.in_degree(n) >= 2 and G.out_degree(n) >= 2]
    for mid in waists:
        preds, succs = set(G.predecessors(mid)), set(G.successors(mid))
        # upstream: a split ancestor that feeds ≥2 of the waist's predecessors
        up = next((a for a in nx.ancestors(G, mid)
                   if a != mid and G.out_degree(a) >= 2
                   and sum(1 for p in preds if p in nx.descendants(G, a)) >= 2), None)
        # downstream: a merge descendant that collects ≥2 of the waist's successors
        down = next((m2 for m2 in nx.descendants(G, mid)
                     if m2 != mid and G.in_degree(m2) >= 2
                     and sum(1 for s in succs if s in nx.ancestors(G, m2)) >= 2), None)
        if up and down:
            nodes = {up, mid, down} | preds | succs
            _add("double_diamond", nodes, 0.86, 0.7,
                 f"Two chained split-reconverge diamonds: {up}→{mid} then {mid}→{down}.")
            break

    return motifs


def extract_motifs(component: dict, analysis: Any = None) -> list[dict[str, Any]]:
    """
    Run the V2 detectors over a component and return explicit motif objects.

    Each motif is self-describing: pattern, label, confidence, severity, the
    nodes + sub-graph edges forming it, the AML rule(s) it triggered, structured
    supporting evidence, and a plain-language explanation.

    `analysis` may be a pre-computed ClusterAnalysis to avoid re-running the
    engine (the case-intelligence layer passes one in).
    """
    if analysis is None:
        from blue_team_v2.engine import BlueTeamV2Engine
        analysis = BlueTeamV2Engine().analyze_component(component)
    comp_edges = component.get("edges", [])
    graph_id = component.get("graph_id", "GRAPH_001")

    motifs: list[dict[str, Any]] = []
    per_pattern: dict[str, int] = {}
    for ev in analysis.evidence:
        idx = per_pattern.get(ev.pattern, 0) + 1
        per_pattern[ev.pattern] = idx
        node_set = set(ev.nodes)
        motifs.append({
            "motif_id": f"{graph_id}-{ev.pattern}-{idx}",
            "graph_id": graph_id,
            "pattern": ev.pattern,
            "label": MOTIF_LABEL.get(ev.pattern, ev.pattern.replace("_", " ").title()),
            "title": ev.title,
            "confidence": round(ev.confidence, 3),
            "severity": severity_label(ev.severity),
            "severity_score": round(ev.severity, 3),
            "nodes": ev.nodes,
            "edges": _edges_among(node_set, comp_edges),
            "triggered_rules": rules_for(ev.pattern),
            "evidence": ev.data,
            "explanation": ev.description,
        })
    # Higher-order topology motifs (Star/Wheel/Hourglass/Double-Diamond) the
    # per-pattern detectors don't name explicitly — additive, same schema.
    motifs.extend(extract_topology_motifs(component))
    # strongest first
    motifs.sort(key=lambda m: (m["severity_score"], m["confidence"]), reverse=True)
    return motifs
