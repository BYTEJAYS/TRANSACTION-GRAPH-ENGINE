"""
Blue Team Oracle — the coupling layer between Red and Blue.

Runs the real Blue Team engine on an attack and returns a structured detection.
Crucially it evaluates at the OPERATION level: it analyses every component the
attack produced (exactly as the deployed system would, one component at a time)
and then aggregates. An attack succeeds only if EVERY component is judged benign
(≤ LOGGED) while the laundering objective is still met — this is what exposes the
cross-component blindness (B1) instead of hiding it.

Decision D2: V2 is the primary target. V1 can be added as a secondary target
behind the same interface to empirically demonstrate B4/B5/B6.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import config  # noqa: F401  (side effect: puts backend/ on sys.path)
from .attack_graph import AttackGraph, Component
from .blue_config import BlueConfig

# Numeric severity of each verdict, for continuous optimisation.
VERDICT_SCORE = {"CLEAN": 0.0, "LOGGED": 0.33, "SUSPICIOUS": 0.66, "FRAUD": 1.0}
_BENIGN_VERDICTS = {"CLEAN", "LOGGED"}


@dataclass
class Detection:
    """Blue Team judgement of a single component."""
    graph_id: str
    verdict: str
    cluster_risk: float
    confidence: float
    flagged_nodes: list[str] = field(default_factory=list)
    evidence_patterns: list[str] = field(default_factory=list)
    node_risk: dict[str, float] = field(default_factory=dict)

    @property
    def score(self) -> float:
        return VERDICT_SCORE.get(self.verdict, 1.0)

    @property
    def flagged(self) -> bool:
        return self.verdict in ("SUSPICIOUS", "FRAUD")


@dataclass
class OperationDetection:
    """Aggregated judgement across every component of one operation."""
    per_component: list[Detection]
    # optional OPERATION-level verdict from a cross-component signal (coordination, §19).
    # This is the only judgement that can see across components — the B1 capability.
    coordination_verdict: str = "CLEAN"

    @property
    def worst_verdict(self) -> str:
        return max([d.verdict for d in self.per_component] + [self.coordination_verdict],
                   key=lambda v: VERDICT_SCORE.get(v, 1.0), default="CLEAN")

    @property
    def detection_score(self) -> float:
        """Operation severity = worst component severity (the analyst sees all)."""
        return max([d.score for d in self.per_component]
                   + [VERDICT_SCORE.get(self.coordination_verdict, 0.0)], default=0.0)

    @property
    def max_cluster_risk(self) -> float:
        return max((d.cluster_risk for d in self.per_component), default=0.0)

    @property
    def flagged(self) -> bool:
        return any(d.flagged for d in self.per_component) \
            or self.coordination_verdict in ("SUSPICIOUS", "FRAUD")

    @property
    def evaded(self) -> bool:
        """True iff no component AND the cross-component signal flagged SUSPICIOUS/FRAUD."""
        return (all(d.verdict in _BENIGN_VERDICTS for d in self.per_component)
                and self.coordination_verdict in _BENIGN_VERDICTS)

    @property
    def evidence_patterns(self) -> set[str]:
        out: set[str] = set()
        for d in self.per_component:
            out.update(d.evidence_patterns)
        return out

    @property
    def total_flagged_nodes(self) -> int:
        return sum(len(d.flagged_nodes) for d in self.per_component)


class BlueTeamOracle:
    """Thin, fast, in-process wrapper over the real Blue Team engine."""

    def __init__(self, target: str | None = None,
                 blue_config: BlueConfig | None = None,
                 calibrator=None, provenance=None, behavioral=None,
                 coordination=None, relationship=None) -> None:
        self.target = (target or config.TARGET_ENGINE or "v2").lower()
        self.blue_config = blue_config or BlueConfig()
        # optional learned detector-level calibration (DetectorCalibrator) that
        # adds fraud–benign margin on top of the native V2 risk; None → native V2.
        self.calibrator = calibrator
        # optional ProvenanceScorer: attenuates trusted (KYC-established) clusters
        # and floors unverified-account value — the signal §13 showed was missing.
        self.provenance = provenance
        # optional BehavioralScorer: re-floors verified accounts operating outside
        # their own baseline (the conduit/account-takeover counter, §16/§17). Runs
        # AFTER provenance because it catches what provenance is forced to trust.
        self.behavioral = behavioral
        # optional CoordinationScorer: the only OPERATION-level (cross-component) signal,
        # which catches the fragmented mule mesh the per-component stack cannot (§18/§19).
        # Requires cross-session linkage — the B1 capability V2 lacks.
        self.coordination = coordination
        # optional RelationshipScorer: floors value moving between verified accounts with no
        # established counterparty history — the corporate-seizure counter (§20). Per-component.
        self.relationship = relationship
        self.calls = 0
        if self.target == "v2":
            # Couple through the OFFICIAL Blue Team V2 red-team interface rather
            # than reaching into engine internals — RedTeamTarget wraps the exact
            # same BlueTeamV2Engine, so behaviour is unchanged but the coupling is
            # now the one stable, documented contract (blue_team_v2.red_team_interface).
            from blue_team_v2.red_team_interface import RedTeamTarget
            self._target = RedTeamTarget(
                thresholds=self.blue_config.to_v2_thresholds())
        else:  # pragma: no cover - V1 is RETIRED (production runs V2); kept as a hook only
            raise NotImplementedError(
                "V1 is retired — Blue Team V2 is the production engine and the only "
                "supported oracle target. Set target='v2'."
            )

    # ── single component ──
    def detect_component(self, component: Component) -> Detection:
        self.calls += 1
        a = self._target.analyze(component)
        risk = float(a.cluster_risk)
        verdict = a.verdict.value
        if (self.calibrator is not None or self.provenance is not None
                or self.behavioral is not None or self.relationship is not None):
            from blue_team_v2.types import action_to_verdict
            if self.calibrator is not None:
                risk = self.calibrator.adjust(a, risk)            # learned factor margin
            if self.provenance is not None:
                risk = self.provenance.adjust(component, risk)    # KYC/history signal
            if self.behavioral is not None:
                risk = self.behavioral.adjust(component, risk)    # verified-conduit signal
            if self.relationship is not None:
                risk = self.relationship.adjust(component, risk)  # counterparty-history signal
            action = self.blue_config.to_v2_thresholds().score_to_action(risk)
            verdict = action_to_verdict(action).value
        return Detection(
            graph_id=a.graph_id,
            verdict=verdict,
            cluster_risk=risk,
            confidence=float(a.confidence),
            flagged_nodes=self._target.flagged_nodes(a),
            evidence_patterns=sorted({e.pattern for e in a.evidence}),
            node_risk={nid: round(m.risk_score, 4) for nid, m in a.metrics.items()},
        )

    # ── whole operation ──
    def detect(self, attack: AttackGraph) -> OperationDetection:
        dets = [self.detect_component(c) for c in attack.components]
        coord_verdict = "CLEAN"
        if self.coordination is not None:
            from blue_team_v2.types import action_to_verdict
            risk = self.coordination.operation_risk(attack.components)
            if risk > 0:
                action = self.blue_config.to_v2_thresholds().score_to_action(risk)
                coord_verdict = action_to_verdict(action).value
        return OperationDetection(per_component=dets, coordination_verdict=coord_verdict)
