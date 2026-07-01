"""
Unified Output Adapter — projects Blue Team V2's rich intelligence down to the
exact TGIE verdict schema that existing consumers (graph rendering, risk badges,
fraud labels, hover panels, AI assistant, analytics dashboard, cluster view)
already understand.

The public functions here are signature-compatible with the V1 adapter
(`blue_team.adapter`) so V2 can be swapped in without touching any caller:

    async def analyze_all_components(components, blue_team_url, api_key) -> list[dict]
    async def analyze_component(component, blue_team_url, api_key) -> dict

`blue_team_url` / `api_key` are accepted for drop-in parity but unused — V2 runs
fully in-process, so there is no external service to call.

The returned dict carries every key V1 emits, PLUS an additive `v2` block of
richer intelligence.  Additive keys are safe: existing consumers read by known
key and ignore the rest.
"""
from __future__ import annotations

from .ai.cluster_analysis.analyzer import summarize
from .ai.explanation_engine.explainer import contributor_summary, explain_node
from .engine import BlueTeamV2Engine, __version__
from .types import ClusterAnalysis, Verdict

# one engine instance is cheap + stateless across calls
_ENGINE = BlueTeamV2Engine()


def _v1_verdict(analysis: ClusterAnalysis) -> dict:
    """The exact per-component schema produced by blue_team.adapter."""
    flagged_nodes = _ENGINE.flagged_nodes(analysis)
    suspicious_reason = None
    if analysis.verdict != Verdict.CLEAN:
        top = sorted(analysis.evidence, key=lambda e: e.severity, reverse=True)
        suspicious_reason = top[0].pattern if top else analysis.primary_classification
    return {
        "graph_id": analysis.graph_id,
        "status": "analyzed",
        "verdict": analysis.verdict.value,
        "risk_score": round(analysis.cluster_risk, 4),
        "flagged": analysis.verdict in (Verdict.FRAUD, Verdict.SUSPICIOUS),
        "flagged_nodes": flagged_nodes,
        "suspicious_reason": suspicious_reason,
        "transactions_scored": 0,  # set by caller from component edges
        "nodes": analysis.node_ids,
        "mode": "blue_team_v2",
    }


def _v2_block(analysis: ClusterAnalysis) -> dict:
    """Additive richer intelligence — ignored by V1 consumers, used by V2 UI."""
    return {
        "engine": "blue_team_v2",
        "version": __version__,
        "confidence": round(analysis.confidence, 4),
        "primary_classification": analysis.primary_classification,
        "secondary_classification": analysis.secondary_classification,
        "narrative": analysis.narrative,
        "cluster_intelligence": summarize(analysis),
        "contributors": contributor_summary(analysis.evidence, analysis.cluster_risk),
        "evidence": [e.to_dict() for e in analysis.evidence],
        "node_intelligence": {
            nid: explain_node(m) for nid, m in analysis.metrics.items()
        },
        "node_risk_scores": {
            nid: round(m.risk_score, 4) for nid, m in analysis.metrics.items()
        },
        "timing_ms": round(analysis.timing_ms, 2),
    }


def analyze_component_sync(component: dict) -> dict:
    """Synchronous single-component analysis returning V1 schema + v2 block."""
    analysis = _ENGINE.analyze_component(component)
    out = _v1_verdict(analysis)
    out["transactions_scored"] = len(component.get("edges", []))
    out["v2"] = _v2_block(analysis)
    return out


def analyze_all_components_sync(components: list[dict]) -> list[dict]:
    return [analyze_component_sync(c) for c in (components or [])]


# ── async drop-in API (matches blue_team.adapter signatures) ──────────────────
async def analyze_component(component: dict, blue_team_url: str = "", api_key: str = "") -> dict:
    return analyze_component_sync(component)


async def analyze_all_components(
    components: list[dict],
    blue_team_url: str = "",
    api_key: str = "",
) -> list[dict]:
    return analyze_all_components_sync(components)
