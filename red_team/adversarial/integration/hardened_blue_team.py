"""
HardenedBlueTeam — the §16–§21 context signals, connected to the REAL blue_team_v2 engine.

This is the deployable form of the engagement's result: a drop-in over `blue_team_v2` that runs
the actual `BlueTeamV2Engine` and then layers the five context signals on top —

    per-component:  provenance (KYC) → behavioural (baseline) → relationship (counterparty history)
    operation-level: coordination (cross-component linked crowd)

It returns the EXACT V1 verdict schema produced by `blue_team_v2.adapter` (`graph_id / status /
verdict / risk_score / flagged / flagged_nodes / suspicious_reason / nodes / mode`), plus an
additive `hardening` block showing each signal's contribution — so existing TGiE consumers (graph
rendering, risk badges, the API) keep working unchanged while the verdict is now context-aware.

It does NOT modify `blue_team_v2` (the isolation contract): the engine is wrapped, not edited, and
the context registries are injected from the bank's records (here, the simulator world) rather than
hard-coded. `default_world()` builds a self-contained local world for trying it out.
"""
from __future__ import annotations

from dataclasses import dataclass

from .. import config  # noqa: F401 — puts backend/ on sys.path
from ..common.behavioral import BehavioralRegistry, BehavioralScorer, build_customer_profiles
from ..common.coordination import CoordinationScorer
from ..common.provenance import ProvenanceRegistry, ProvenanceScorer
from ..common.relationships import (RelationshipRegistry, RelationshipScorer,
                                    build_relationship_circles)


@dataclass
class World:
    """The bank's records the context signals draw on (injected, not hard-coded)."""
    profiles: dict
    circles: dict
    behav_reg: BehavioralRegistry
    rel_reg: RelationshipRegistry


def default_world() -> World:
    profiles = build_customer_profiles()
    circles = build_relationship_circles(profiles)
    breg = BehavioralRegistry(profiles)
    rreg = RelationshipRegistry(dict(circles), profiles, {})
    return World(profiles, circles, breg, rreg)


class HardenedBlueTeam:
    """Real blue_team_v2 engine + the five context signals, V1-schema compatible."""

    def __init__(self, world: World | None = None, *, maturity: bool = True) -> None:
        from blue_team_v2.engine import BlueTeamV2Engine
        from blue_team_v2.types import DEFAULT_THRESHOLDS
        self.world = world or default_world()
        self.engine = BlueTeamV2Engine()                       # the real, untouched engine
        self._thr = DEFAULT_THRESHOLDS
        self.provenance = ProvenanceScorer(ProvenanceRegistry(self.world.behav_reg.universe))
        self.behavioural = BehavioralScorer(self.world.behav_reg)
        self.relationship = RelationshipScorer(self.world.rel_reg, maturity=maturity)
        self.coordination = CoordinationScorer(self.world.behav_reg)

    # ── per-component: native engine + the three per-component context signals ──
    def _verdict(self, risk: float) -> str:
        from blue_team_v2.types import action_to_verdict
        return action_to_verdict(self._thr.score_to_action(risk)).value

    def _component_risk(self, component: dict):
        a = self.engine.analyze_component(component)
        native = float(a.cluster_risk)
        # provenance + behavioural is the "FP-fixed" stack: it clears legitimate verified
        # activity (which native over-flags) but, for that same reason, lets a seized-verified
        # scheme through — the §17-C hole. Relationship is what then closes it.
        pre_rel = self.behavioural.adjust(component, self.provenance.adjust(component, native))
        risk = self.relationship.adjust(component, pre_rel)
        return a, native, pre_rel, risk

    def analyze_component(self, component: dict) -> dict:
        a, native, pre_rel, risk = self._component_risk(component)
        verdict = self._verdict(risk)
        top = sorted(a.evidence, key=lambda e: e.severity, reverse=True)
        reason = (top[0].pattern if top else a.primary_classification) if verdict != "CLEAN" else None
        return {
            "graph_id": a.graph_id,
            "status": "analyzed",
            "verdict": verdict,
            "risk_score": round(risk, 4),
            "flagged": verdict in ("FRAUD", "SUSPICIOUS"),
            "flagged_nodes": self.engine.flagged_nodes(a),
            "suspicious_reason": reason,
            "transactions_scored": len(component.get("edges", [])),
            "nodes": a.node_ids,
            "mode": "blue_team_v2+hardened",
            "hardening": {
                "native_risk": round(native, 4),
                "native_verdict": a.verdict.value,
                "pre_relationship_risk": round(pre_rel, 4),
                "pre_relationship_verdict": self._verdict(pre_rel),
                "hardened_risk": round(risk, 4),
                "provenance_unverified_ratio": round(self.provenance.unverified_value_ratio(component), 3),
                "behavioural_conduit_anomaly": round(self.behavioural.conduit_anomaly(component), 3),
                "relationship_novel_ratio": round(self.relationship.novel_value_ratio(component), 3),
            },
        }

    # ── operation-level: adds the cross-component coordination signal ──
    def analyze_operation(self, components: list[dict]) -> dict:
        from blue_team_v2.types import Verdict, action_to_verdict
        per = [self.analyze_component(c) for c in components]
        coord_risk = self.coordination.operation_risk(components)
        coord_verdict = (action_to_verdict(self._thr.score_to_action(coord_risk)).value
                         if coord_risk > 0 else "CLEAN")
        order = {"CLEAN": 0, "LOGGED": 1, "SUSPICIOUS": 2, "FRAUD": 3}
        worst = max([p["verdict"] for p in per] + [coord_verdict], key=lambda v: order.get(v, 3))
        return {
            "operation_verdict": worst,
            "flagged": worst in ("FRAUD", "SUSPICIOUS"),
            "coordination_verdict": coord_verdict,
            "coordination_risk": round(coord_risk, 4),
            "num_components": len(components),
            "components": per,
        }


def native_verdict(engine, component: dict) -> dict:
    """The deployed blue_team_v2 verdict for the same component, for side-by-side comparison."""
    from blue_team_v2.adapter import analyze_component_sync
    return analyze_component_sync(component)
