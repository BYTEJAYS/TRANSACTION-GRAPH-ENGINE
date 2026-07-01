"""
Cluster Analysis — investigator-facing summary object for a cluster: the role
hierarchy, the dominant flow path, and the headline metrics the UB AI assistant
can quote back to the user.
"""
from __future__ import annotations

from ...types import ClusterAnalysis


def summarize(analysis: ClusterAnalysis) -> dict:
    ci = analysis.cluster
    return {
        "graph_id": analysis.graph_id,
        "verdict": analysis.verdict.value,
        "cluster_risk": round(analysis.cluster_risk * 100, 1),
        "confidence": round(analysis.confidence * 100, 1),
        "primary_classification": analysis.primary_classification,
        "secondary_classification": analysis.secondary_classification,
        "node_count": len(analysis.node_ids),
        "hierarchy": {
            "origin": ci.origin,
            "collection": ci.collection,
            "distribution": ci.distribution,
            "bridges": ci.bridges,
            "mules": ci.mules,
            "cashout": ci.cashout,
            "sinks": ci.sinks,
            "terminals": ci.terminals,
            "circular": ci.circular,
            "layering": ci.layering,
        },
        "patterns_detected": sorted({e.pattern for e in analysis.evidence}),
        "evidence_count": len(analysis.evidence),
        "narrative": analysis.narrative,
        "top_evidence": [
            {"pattern": e.pattern, "title": e.title, "severity": round(e.severity, 3),
             "confidence": round(e.confidence, 3), "nodes": e.nodes[:10]}
            for e in sorted(analysis.evidence, key=lambda e: e.severity, reverse=True)[:5]
        ],
    }
