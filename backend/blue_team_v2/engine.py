"""
BlueTeamV2Engine — the orchestrator.

Runs the full next-generation pipeline on a single TGIE component and returns a
rich ClusterAnalysis.  This is engine-internal intelligence; the *adapter*
projects it down to the TGIE-compatible verdict that existing consumers expect.

Pipeline:
    component → graph build → 18-factor node metrics → detectors (evidence)
             → score every node independently → aggregate cluster verdict
             → classify → narrate → ClusterAnalysis
"""
from __future__ import annotations

import time

from .ai.explanation_engine.explainer import explain_cluster
from .ai.fraud_reasoning.classifier import classify
from .core.graph_engine.builder import TransactionGraph
from .core.pattern_engine.orchestrator import PatternEngine
from .core.risk_engine.node_intelligence import RiskEngine
from .core.scoring_engine.scorer import ScoringEngine
from .types import (
    ClusterAnalysis,
    DEFAULT_THRESHOLDS,
    Thresholds,
    Verdict,
    action_to_verdict,
)

__version__ = "2.0.0"


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


class BlueTeamV2Engine:
    name = "blue_team_v2"
    version = __version__

    def __init__(self, thresholds: Thresholds | None = None) -> None:
        self._pattern = PatternEngine()
        self._scorer = ScoringEngine()
        # Defaults to the shipped constants → identical behaviour unless an
        # explicit (tightened) Thresholds is supplied by the self-play hardener.
        self._thr = thresholds or DEFAULT_THRESHOLDS

    def analyze_component(self, component: dict) -> ClusterAnalysis:
        t0 = time.perf_counter()
        tg = TransactionGraph(component)
        graph_id = tg.graph_id
        node_ids = list(component.get("node_ids") or tg.nodes)

        if tg.num_edges() == 0:
            return ClusterAnalysis(
                graph_id=graph_id, node_ids=node_ids, metrics={}, evidence=[],
                cluster=RiskEngine(tg).cluster_engine.assign()[0],
                cluster_risk=0.0, verdict=Verdict.CLEAN,
                action=self._thr.score_to_action(0.0), confidence=0.0,
                primary_classification="Legitimate Activity",
                timing_ms=(time.perf_counter() - t0) * 1000,
            )

        # 1) node intelligence + cluster roles
        metrics, cluster_intel, meta = RiskEngine(tg).compute()
        # 2) detectors → evidence (also writes pattern_participation back)
        evidence = self._pattern.run(tg, metrics, meta)
        # 3) score every node independently (now that participation is known)
        self._scorer.score_all(metrics)

        # 4) aggregate cluster risk: blend strongest evidence with node risk tail
        node_risks = [m.risk_score for m in metrics.values()]
        ev_severity = max((e.severity * (0.6 + 0.4 * e.confidence) for e in evidence), default=0.0)
        node_tail = _percentile(node_risks, 0.9)
        cluster_risk = max(ev_severity, 0.6 * node_tail + 0.4 * _percentile(node_risks, 0.75))
        cluster_risk = max(0.0, min(0.999, cluster_risk))

        action = self._thr.score_to_action(cluster_risk)
        verdict = action_to_verdict(action)

        # 5) confidence: evidence breadth + node corroboration
        ev_conf = max((e.confidence for e in evidence), default=0.0)
        corrob = min(1.0, len({e.pattern for e in evidence}) / 4.0)
        confidence = max(ev_conf * 0.7 + corrob * 0.3,
                         _percentile([m.confidence for m in metrics.values()], 0.9) * 0.6)
        confidence = max(0.0, min(0.99, confidence))

        primary, secondary = classify(evidence)

        analysis = ClusterAnalysis(
            graph_id=graph_id,
            node_ids=node_ids,
            metrics=metrics,
            evidence=evidence,
            cluster=cluster_intel,
            cluster_risk=cluster_risk,
            verdict=verdict,
            action=action,
            confidence=confidence,
            primary_classification=primary if verdict != Verdict.CLEAN else "Legitimate Activity",
            secondary_classification=secondary if verdict != Verdict.CLEAN else None,
            timing_ms=(time.perf_counter() - t0) * 1000,
        )
        analysis.narrative = explain_cluster(analysis)
        return analysis

    def analyze_components(self, components: list[dict]) -> list[ClusterAnalysis]:
        return [self.analyze_component(c) for c in components]

    def flagged_nodes(self, analysis: ClusterAnalysis) -> list[str]:
        """
        Nodes worth an analyst's attention.

        Always: any node scoring at/above the REVIEW band. Additionally, inside a
        cluster already judged SUSPICIOUS/FRAUD, a node that participates in a
        detected (amount-gated) pattern is implicated too — even if its own score
        sits in the LOG band — because it is structurally part of the ring (e.g. a
        peripheral mule receiving one split of a fan-out).
        """
        cluster_is_fraud = analysis.verdict in (Verdict.FRAUD, Verdict.SUSPICIOUS)
        flagged: list[str] = []
        for nid, m in analysis.metrics.items():
            if m.risk_score >= self._thr.review:
                flagged.append(nid)
            elif cluster_is_fraud and m.pattern_participation >= 1 and m.risk_score >= self._thr.log:
                flagged.append(nid)
        return flagged
