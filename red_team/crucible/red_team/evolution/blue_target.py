from __future__ import annotations
"""
Blue target for the evolution engine — the RICH verdict view of Blue Team V2.

`sandbox/v2_target.V2BlueTeam` returns only the 4-float ensemble (the MockBlueTeam
contract). The evolution loop needs to know *why* a pattern was caught, so this
adapter goes through V2's `RedTeamTarget.judge_component()` and exposes the full
`ComponentVerdict` (verdict, risk, confidence, evidence patterns, flagged nodes,
per-node risk) as a stable local dataclass.

Coupling is one-way (Red imports Blue). It reuses `sandbox.v2_target` for backend
path resolution so there is a single place that knows where `blue_team_v2` lives.
This module READS Blue's judgement only — it never mutates the engine.
"""
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from red_team.sandbox.v2_target import _resolve_backend_path

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome

logger = logging.getLogger(__name__)

# V2 verdicts that count as "Blue caught it".
_FLAGGED_VERDICTS = frozenset({"SUSPICIOUS", "FRAUD"})


@dataclass
class BlueVerdict:
    """Blue Team V2's judgement of one fraud component — engine-agnostic shape."""
    graph_id: str
    verdict: str
    risk: float
    confidence: float
    evidence_patterns: list[str] = field(default_factory=list)
    flagged_nodes: list[str] = field(default_factory=list)
    node_risk: dict[str, float] = field(default_factory=dict)
    ensemble: list[float] = field(default_factory=list)

    @property
    def detected(self) -> bool:
        return self.verdict in _FLAGGED_VERDICTS


def _load_v2():
    import os
    import sys

    backend = _resolve_backend_path()
    if backend is None:
        raise RuntimeError(
            "blue_team_v2 not found. Set CRUCIBLE_V2_BACKEND to the TGIE 'backend' dir."
        )
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from blue_team_v2.red_team_interface import RedTeamTarget, to_component
    return RedTeamTarget, to_component


class BlueTeamV2Target:
    """Live Blue Team V2 wrapped to return rich verdicts for the evolution loop."""

    def __init__(self) -> None:
        RedTeamTarget, to_component = _load_v2()
        self._target = RedTeamTarget()
        self._to_component = to_component
        self.version = getattr(self._target, "version", "unknown")

    def to_component(self, transactions: list[dict], graph_id: str = "RT_ATTACK") -> dict[str, Any]:
        return self._to_component(transactions, graph_id)

    def judge_component(self, component: dict[str, Any]) -> BlueVerdict:
        cv = self._target.judge_component(component)
        ens = self._target.ensemble_scores(component) if component.get("edges") else []
        return BlueVerdict(
            graph_id=cv.graph_id,
            verdict=cv.verdict,
            risk=float(cv.risk),
            confidence=float(cv.confidence),
            evidence_patterns=list(cv.evidence_patterns),
            flagged_nodes=list(cv.flagged_nodes),
            node_risk=dict(cv.node_risk),
            ensemble=ens,
        )

    def judge(self, genome: "FraudGenome", graph_id: str | None = None) -> BlueVerdict:
        gid = graph_id or f"rt_{genome.genome_id[:8]}"
        comp = self.to_component(genome.to_transaction_list(), gid)
        if not comp.get("edges"):
            return BlueVerdict(graph_id=gid, verdict="CLEAN", risk=0.0, confidence=1.0)
        return self.judge_component(comp)
