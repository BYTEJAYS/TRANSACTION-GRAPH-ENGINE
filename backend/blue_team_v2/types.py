"""
Blue Team V2 — shared data model.

These dataclasses/enums are the lingua franca passed between every engine in
the V2 pipeline.  They are intentionally rich (far richer than the V1 verdict
schema) — the *adapter* layer is responsible for projecting them back down to
the TGIE-compatible verdict that existing consumers expect.

Nothing in this module imports from the rest of blue_team_v2, so it can be
imported anywhere without circular-import risk.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field, asdict
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────────────────
class ClusterRole(str, enum.Enum):
    """The structural role a node plays inside its laundering cluster."""
    ORIGIN = "origin"                # where illicit funds enter the network
    COLLECTION = "collection"        # aggregates funds from many sources (fan-in)
    DISTRIBUTION = "distribution"    # splits funds to many destinations (fan-out)
    BRIDGE = "bridge"                # articulation point linking sub-clusters
    MULE = "mule"                    # receives + quickly forwards (pass + role)
    CASHOUT = "cashout"              # funds exit to cash / external rail
    SINK = "sink"                    # absorbs funds, low/no outflow
    TERMINAL = "terminal"            # leaf endpoint of a flow
    CIRCULAR = "circular"            # participates in a cycle
    LAYERING = "layering"            # deep mid-chain forwarding hop
    PASS_THROUGH = "pass_through"    # in≈out, single hop relay
    PERIPHERAL = "peripheral"        # loosely attached receiver
    NORMAL = "normal"                # no suspicious structural role


class Verdict(str, enum.Enum):
    """TGIE-compatible verdict labels (must match V1 exactly)."""
    CLEAN = "CLEAN"
    LOGGED = "LOGGED"
    SUSPICIOUS = "SUSPICIOUS"
    FRAUD = "FRAUD"


class Action(str, enum.Enum):
    PASS = "PASS"
    LOG = "LOG"
    REVIEW = "REVIEW"
    HIGH_RISK = "HIGH_RISK"


# Risk thresholds — mirror V1 so shadow comparisons are apples-to-apples.
THRESHOLD_LOG = 0.38
THRESHOLD_REVIEW = 0.62
THRESHOLD_HIGH_RISK = 0.83


def score_to_action(score: float) -> Action:
    if score >= THRESHOLD_HIGH_RISK:
        return Action.HIGH_RISK
    if score >= THRESHOLD_REVIEW:
        return Action.REVIEW
    if score >= THRESHOLD_LOG:
        return Action.LOG
    return Action.PASS


@dataclass(frozen=True)
class Thresholds:
    """Decision thresholds as overridable data.

    Defaults reproduce the shipped module-level constants exactly, so an engine
    constructed without an explicit ``Thresholds`` behaves identically to before.
    The adversarial self-play loop supplies a tightened instance to *harden* the
    detector (lower ``review`` re-flags near-threshold evasions) and measures the
    benign false-positive cost of doing so — without mutating shipped constants.
    """
    log: float = THRESHOLD_LOG
    review: float = THRESHOLD_REVIEW
    high_risk: float = THRESHOLD_HIGH_RISK

    def score_to_action(self, score: float) -> Action:
        if score >= self.high_risk:
            return Action.HIGH_RISK
        if score >= self.review:
            return Action.REVIEW
        if score >= self.log:
            return Action.LOG
        return Action.PASS


DEFAULT_THRESHOLDS = Thresholds()


def action_to_verdict(action: Action) -> Verdict:
    return {
        Action.HIGH_RISK: Verdict.FRAUD,
        Action.REVIEW: Verdict.SUSPICIOUS,
        Action.LOG: Verdict.LOGGED,
        Action.PASS: Verdict.CLEAN,
    }[action]


# ──────────────────────────────────────────────────────────────────────────────
# Node intelligence
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class NodeMetrics:
    """
    The 18-factor independent analysis computed for *every* node.

    Raw factors are stored alongside their normalized [0,1] contribution so the
    explanation engine can attribute the final score back to human-readable
    drivers without recomputing anything.
    """
    node_id: str

    # 1–6 volumetric / flow
    transaction_velocity: float = 0.0       # value moved per minute (active window)
    transaction_frequency: int = 0          # total adjacent transactions
    incoming_volume: float = 0.0
    outgoing_volume: float = 0.0
    fan_in_count: int = 0                    # unique predecessors
    fan_out_count: int = 0                   # unique successors

    # 7–9 centrality
    degree_centrality: float = 0.0
    betweenness_centrality: float = 0.0
    closeness_centrality: float = 0.0

    # 10–13 structural fraud position
    fraud_distance: float = 999.0            # hops to nearest fraud origin (0 = is origin)
    layer_distance: int = 0                  # depth from the cluster origin
    circular_participation: bool = False
    burst_activity: float = 0.0              # 0..1 burstiness of inter-arrival times

    # 14–18 behavioural / inherited
    historical_behavior: float = 0.0         # prior risk carried in on the node
    risk_inheritance: float = 0.0            # risk diffused from neighbours
    pattern_participation: int = 0           # # of detector patterns node appears in
    bridge_importance: float = 0.0           # articulation / cut importance 0..1
    cluster_role: ClusterRole = ClusterRole.NORMAL

    # ── derived ──
    pass_through_ratio: float = 0.0          # min(in,out)/max(in,out) value balance
    dormancy_reactivation: float = 0.0       # 0..1 sudden wake-up signal

    # ── output ──
    risk_score: float = 0.0                  # final independent score 0..1
    confidence: float = 0.0                  # 0..1 confidence in the score
    contributions: dict[str, float] = field(default_factory=dict)  # factor → share of score
    patterns: list[str] = field(default_factory=list)              # pattern names touching node

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["cluster_role"] = self.cluster_role.value
        return d


# ──────────────────────────────────────────────────────────────────────────────
# Evidence (detector output)
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class Evidence:
    """A single piece of fraud evidence produced by a detector."""
    pattern: str                         # canonical pattern name, e.g. "layering"
    title: str                           # short human title
    description: str                     # plain-language explanation of the finding
    nodes: list[str]                     # node ids implicated
    severity: float                      # 0..1 how damning
    confidence: float                    # 0..1 detector confidence
    data: dict[str, Any] = field(default_factory=dict)  # structured supporting facts

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────────────
# Cluster intelligence
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class ClusterIntelligence:
    """Auto-generated structural hierarchy of one laundering cluster."""
    graph_id: str
    origin: list[str] = field(default_factory=list)
    collection: list[str] = field(default_factory=list)
    distribution: list[str] = field(default_factory=list)
    bridges: list[str] = field(default_factory=list)
    mules: list[str] = field(default_factory=list)
    cashout: list[str] = field(default_factory=list)
    sinks: list[str] = field(default_factory=list)
    terminals: list[str] = field(default_factory=list)
    circular: list[str] = field(default_factory=list)
    layering: list[str] = field(default_factory=list)
    roles: dict[str, str] = field(default_factory=dict)   # node_id → role value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────────────
# Full analysis result (per cluster/component)
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class ClusterAnalysis:
    """Everything V2 knows about one connected component."""
    graph_id: str
    node_ids: list[str]
    metrics: dict[str, NodeMetrics]               # node_id → metrics
    evidence: list[Evidence]
    cluster: ClusterIntelligence
    cluster_risk: float = 0.0                     # aggregated cluster risk 0..1
    verdict: Verdict = Verdict.CLEAN
    action: Action = Action.PASS
    confidence: float = 0.0
    primary_classification: str = "Legitimate Activity"
    secondary_classification: str | None = None
    narrative: str = ""
    timing_ms: float = 0.0

    def flagged_nodes(self) -> list[str]:
        return [nid for nid, m in self.metrics.items()
                if m.risk_score >= THRESHOLD_REVIEW]

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_ids": self.node_ids,
            "metrics": {k: v.to_dict() for k, v in self.metrics.items()},
            "evidence": [e.to_dict() for e in self.evidence],
            "cluster": self.cluster.to_dict(),
            "cluster_risk": round(self.cluster_risk, 4),
            "verdict": self.verdict.value,
            "action": self.action.value,
            "confidence": round(self.confidence, 4),
            "primary_classification": self.primary_classification,
            "secondary_classification": self.secondary_classification,
            "narrative": self.narrative,
            "timing_ms": round(self.timing_ms, 2),
        }
