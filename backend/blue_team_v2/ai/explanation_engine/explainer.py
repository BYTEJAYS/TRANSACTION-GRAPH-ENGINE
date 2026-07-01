"""
Explanation Engine — turns scores + factors + evidence into human-readable
"why", for both individual nodes and the whole cluster.

Every explanation is faithful: contributor percentages come straight from the
scoring engine's normalized contribution map, so the numbers always add up.
"""
from __future__ import annotations

from ...types import ClusterAnalysis, Evidence, NodeMetrics

_ROLE_PHRASE = {
    "origin": "the funding origin of this network",
    "collection": "a collection hub aggregating funds from many senders",
    "distribution": "a distribution hub splitting funds to many recipients",
    "bridge": "a bridge linking otherwise separate sub-networks",
    "mule": "a money mule forwarding received funds onward",
    "cashout": "a cash-out endpoint where value exits the network",
    "sink": "a value sink absorbing inbound funds",
    "terminal": "a terminal leaf node",
    "circular": "part of a circular fund loop",
    "layering": "a mid-chain layering relay",
    "pass_through": "a pass-through relay",
    "peripheral": "a peripheral participant",
    "normal": "an ordinary participant",
}


def explain_node(m: NodeMetrics) -> dict:
    """Structured, explainable record for one node (TGIE hover-panel friendly)."""
    contributors = [
        {"factor": label, "share": round(share * 100, 1)}
        for label, share in m.contributions.items()
    ]
    role_phrase = _ROLE_PHRASE.get(m.cluster_role.value, "a participant")
    if contributors:
        top = contributors[0]
        why = (
            f"Risk {m.risk_score*100:.0f}% (confidence {m.confidence*100:.0f}%). "
            f"Structurally {role_phrase}. Primary driver: {top['factor']} "
            f"({top['share']:.0f}% of score)"
        )
        if len(contributors) > 1:
            why += f", followed by {contributors[1]['factor']} ({contributors[1]['share']:.0f}%)."
        else:
            why += "."
    else:
        why = (
            f"Risk {m.risk_score*100:.0f}% (confidence {m.confidence*100:.0f}%). "
            f"Structurally {role_phrase}; no anomalous factors detected."
        )

    return {
        "node_id": m.node_id,
        "risk_score": round(m.risk_score * 100, 1),
        "confidence": round(m.confidence * 100, 1),
        "role": m.cluster_role.value,
        "explanation": why,
        "contributors": contributors,
        "patterns": m.patterns,
        "fraud_distance": None if m.fraud_distance >= 999 else m.fraud_distance,
    }


def explain_cluster(analysis: ClusterAnalysis) -> str:
    """One-paragraph investigator narrative for the whole cluster."""
    ci = analysis.cluster
    n = len(analysis.node_ids)
    parts: list[str] = []
    parts.append(
        f"Cluster {analysis.graph_id} contains {n} accounts and is classified as "
        f"{analysis.primary_classification} "
        f"(risk {analysis.cluster_risk*100:.0f}%, confidence {analysis.confidence*100:.0f}%)."
    )
    if ci.origin:
        parts.append(f"Funds originate at {', '.join(ci.origin[:3])}.")
    flow_bits = []
    if ci.distribution:
        flow_bits.append(f"distributed via {len(ci.distribution)} hub(s)")
    if ci.layering:
        flow_bits.append(f"layered through {len(ci.layering)} relay(s)")
    if ci.bridges:
        flow_bits.append(f"bridged by {', '.join(ci.bridges[:2])}")
    if ci.mules:
        flow_bits.append(f"{len(ci.mules)} mule account(s)")
    if flow_bits:
        parts.append("They are " + ", ".join(flow_bits) + ".")
    if ci.cashout:
        parts.append(f"Value exits at cash-out point(s) {', '.join(ci.cashout[:3])}.")
    elif ci.sinks:
        parts.append(f"Value settles in sink(s) {', '.join(ci.sinks[:3])}.")

    top_ev = sorted(analysis.evidence, key=lambda e: e.severity, reverse=True)[:3]
    if top_ev:
        parts.append("Key evidence: " + "; ".join(e.title for e in top_ev) + ".")
    return " ".join(parts)


def contributor_summary(evidence: list[Evidence], cluster_risk: float) -> list[dict]:
    """
    Cluster-level contributor breakdown (the '35% Velocity / 21% Proximity …'
    view) derived from aggregated evidence severity per pattern family.
    """
    if not evidence:
        return []
    by_family: dict[str, float] = {}
    for ev in evidence:
        by_family[ev.pattern] = by_family.get(ev.pattern, 0.0) + ev.severity * ev.confidence
    total = sum(by_family.values())
    if total <= 0:
        return []
    out = [
        {"pattern": fam, "share": round(v / total * 100, 1)}
        for fam, v in sorted(by_family.items(), key=lambda x: x[1], reverse=True)
    ]
    return out
