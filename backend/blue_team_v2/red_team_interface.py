"""
Red Team Coupling Interface — the official, stable contract the TGIE Red Team
uses to attack Blue Team V2.

This is the V2 equivalent of how the Red Team coupled to V1 (the union-bank
`MockBlueTeam.score()` clone, plus the production `analyze_*` adapter). It gives
adversarial code ONE import surface so it never has to reach into the engine /
types / adapter internals, and it provides exactly the shapes each Red Team
subsystem needs.

Isolation contract (one-directional): this module imports only from within
`blue_team_v2`. It NEVER imports `red_team` — Red depends on Blue, never the
reverse — so the production engine stays completely decoupled from the attacker.

Three coupling modes, covering both Red Team subsystems:

  • component / operation detection   → adversarial `BlueTeamOracle`
        judge_component(c)  -> ComponentVerdict      (verdict + risk + evidence + node risk)
        judge_operation(cs) -> OperationVerdict       (cross-component aggregate / evaded?)
        analyze(c)          -> ClusterAnalysis        (raw, for learned signal-layering)

  • per-detector ENSEMBLE scores       → crucible `MockBlueTeam.score()`
        ensemble_scores(c)  -> [champion, challenger_1, challenger_2, challenger_3]
        score_transactions(txns) -> same, from a flat txn list (genome bridge)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .engine import BlueTeamV2Engine, __version__
from .types import ClusterAnalysis, DEFAULT_THRESHOLDS, Thresholds, Verdict

Component = dict[str, Any]

# Numeric severity of each verdict, for continuous optimisation / ordering.
VERDICT_SCORE = {"CLEAN": 0.0, "LOGGED": 0.33, "SUSPICIOUS": 0.66, "FRAUD": 1.0}
_BENIGN = ("CLEAN", "LOGGED")
_FLAGGED = ("SUSPICIOUS", "FRAUD")


# ── stable, engine-agnostic result shapes ─────────────────────────────────────
@dataclass
class ComponentVerdict:
    """Blue Team V2's judgement of a single component, flattened to a stable schema."""
    graph_id: str
    verdict: str
    risk: float
    confidence: float
    flagged_nodes: list[str] = field(default_factory=list)
    evidence_patterns: list[str] = field(default_factory=list)
    node_risk: dict[str, float] = field(default_factory=dict)

    @property
    def score(self) -> float:
        return VERDICT_SCORE.get(self.verdict, 1.0)

    @property
    def flagged(self) -> bool:
        return self.verdict in _FLAGGED

    @property
    def benign(self) -> bool:
        return self.verdict in _BENIGN


@dataclass
class OperationVerdict:
    """Aggregate judgement across every component of one attack operation."""
    per_component: list[ComponentVerdict]

    @property
    def worst_verdict(self) -> str:
        return max((d.verdict for d in self.per_component),
                   key=lambda v: VERDICT_SCORE.get(v, 1.0), default="CLEAN")

    @property
    def detection_score(self) -> float:
        return max((d.score for d in self.per_component), default=0.0)

    @property
    def max_risk(self) -> float:
        return max((d.risk for d in self.per_component), default=0.0)

    @property
    def flagged(self) -> bool:
        return any(d.flagged for d in self.per_component)

    @property
    def evaded(self) -> bool:
        """True iff NO component was flagged SUSPICIOUS/FRAUD (the attack slipped through)."""
        return all(d.benign for d in self.per_component)

    @property
    def evidence_patterns(self) -> set[str]:
        out: set[str] = set()
        for d in self.per_component:
            out.update(d.evidence_patterns)
        return out

    @property
    def total_flagged_nodes(self) -> int:
        return sum(len(d.flagged_nodes) for d in self.per_component)


# ── transaction-list → V2 component bridge (the genome connector) ─────────────
def to_component(transactions: list[dict], graph_id: str = "RT_ATTACK") -> Component:
    """Build a V2 component from a flat transaction list.

    Accepts either Blue-Team edge keys (`source`/`target`) or the Red Team's
    genome keys (`from_account`/`to_account`) so `genome.to_transaction_list()`
    plugs straight in. Field-name flexible, amount/timestamp/rail tolerant.
    """
    edges: list[dict] = []
    for i, t in enumerate(transactions or []):
        src = t.get("source") or t.get("from_account")
        dst = t.get("target") or t.get("to_account")
        if not src or not dst:
            continue
        edges.append({
            "id": str(t.get("id", f"rt_e{i}")),
            "source": str(src),
            "target": str(dst),
            "amount": float(t.get("amount", 0) or 0),
            "timestamp": t.get("timestamp", ""),
            "payment_rail": t.get("payment_rail", t.get("rail", "IMPS")),
        })
    ids = sorted({e["source"] for e in edges} | {e["target"] for e in edges})
    nodes = [{"id": n, "risk_score": 0.0, "account_type": "normal",
              "transaction_count": 0, "detected_patterns": []} for n in ids]
    return {"graph_id": graph_id, "node_ids": ids, "nodes": nodes, "edges": edges}


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


# ── the attackable target ─────────────────────────────────────────────────────
class RedTeamTarget:
    """Blue Team V2 exposed as a stable, attackable target.

    Wraps a single `BlueTeamV2Engine` (optionally with tightened thresholds from
    the self-play hardener). The engine is NOT modified — it is the exact same
    object the deployed system runs, so attacks here transfer to production.
    """
    version = __version__

    def __init__(self, thresholds: Thresholds | None = None) -> None:
        self._thr = thresholds or DEFAULT_THRESHOLDS
        self._engine = BlueTeamV2Engine(thresholds=self._thr)
        self.calls = 0

    # raw access — for advanced red-team signal layering that needs the full analysis
    def analyze(self, component: Component) -> ClusterAnalysis:
        self.calls += 1
        return self._engine.analyze_component(component)

    def flagged_nodes(self, analysis: ClusterAnalysis) -> list[str]:
        return self._engine.flagged_nodes(analysis)

    # ── adversarial-oracle shape ──
    def judge_component(self, component: Component) -> ComponentVerdict:
        a = self.analyze(component)
        return ComponentVerdict(
            graph_id=a.graph_id,
            verdict=a.verdict.value,
            risk=float(a.cluster_risk),
            confidence=float(a.confidence),
            flagged_nodes=self._engine.flagged_nodes(a),
            evidence_patterns=sorted({e.pattern for e in a.evidence}),
            node_risk={nid: round(m.risk_score, 4) for nid, m in a.metrics.items()},
        )

    def judge_operation(self, components: list[Component]) -> OperationVerdict:
        return OperationVerdict([self.judge_component(c) for c in components])

    # ── crucible ensemble shape ──
    def ensemble_scores(self, component: Component) -> list[float]:
        """[champion, challenger_1, challenger_2, challenger_3] risk scores in [0,1].

        The champion is the DEPLOYED cluster risk (what production decides on); the
        challengers are three principled internal views of the same component:
          • strongest single piece of evidence (structural worst case),
          • mean evidence severity (averaged structural signal),
          • 90th-percentile node risk (the node-intelligence view).
        Variance across them is high exactly where V2 is internally UNCERTAIN — the
        soft spots an ensemble-disagreement attacker should probe.
        """
        a = self.analyze(component)
        champ = float(a.cluster_risk)
        sev = [float(e.severity) for e in a.evidence] or [0.0]
        node = [float(m.risk_score) for m in a.metrics.values()] or [0.0]
        return [
            round(max(0.0, min(1.0, champ)), 4),
            round(max(sev), 4),
            round(sum(sev) / len(sev), 4),
            round(_percentile(node, 0.9), 4),
        ]

    def score_transactions(self, transactions: list[dict],
                           graph_id: str = "RT_ATTACK") -> list[float]:
        """Genome bridge: flat txn list → component → ensemble_scores.

        Matches the crucible `MockBlueTeam.score()` contract directly on
        `genome.to_transaction_list()`. An empty/edge-less attack returns the
        same near-zero ensemble the clone used so callers behave identically.
        """
        comp = to_component(transactions, graph_id)
        if not comp["edges"]:
            return [0.05, 0.05, 0.04, 0.06]
        return self.ensemble_scores(comp)


# ── module-level stable surface (shared default target) ───────────────────────
_DEFAULT_TARGET = RedTeamTarget()


def target(thresholds: Thresholds | None = None) -> RedTeamTarget:
    """A fresh attackable target (own engine instance + optional tightened thresholds)."""
    return RedTeamTarget(thresholds) if thresholds is not None else _DEFAULT_TARGET


def judge_component(component: Component) -> ComponentVerdict:
    return _DEFAULT_TARGET.judge_component(component)


def judge_operation(components: list[Component]) -> OperationVerdict:
    return _DEFAULT_TARGET.judge_operation(components)


def ensemble_scores(component: Component) -> list[float]:
    return _DEFAULT_TARGET.ensemble_scores(component)


def score_transactions(transactions: list[dict], graph_id: str = "RT_ATTACK") -> list[float]:
    return _DEFAULT_TARGET.score_transactions(transactions, graph_id)
