"""
Blue Team V2 test suite.

Run:  pytest blue_team_v2/tests -q
   or: python -m pytest backend/blue_team_v2/tests -q   (from repo root, backend on path)
"""
from __future__ import annotations

import asyncio

import pytest

from blue_team_v2.adapter import analyze_all_components, analyze_component_sync
from blue_team_v2.engine import BlueTeamV2Engine
from blue_team_v2.simulation.generators import Simulator
from blue_team_v2.types import Verdict

V1_KEYS = {"graph_id", "status", "verdict", "risk_score", "flagged",
           "flagged_nodes", "suspicious_reason", "transactions_scored", "nodes", "mode"}


# ── output-contract / backward-compatibility ──────────────────────────────────
def test_output_is_v1_compatible():
    comp, _ = Simulator().layering()
    out = analyze_component_sync(comp)
    assert V1_KEYS.issubset(out.keys()), "must emit every V1 verdict key"
    assert out["verdict"] in {v.value for v in Verdict}
    assert isinstance(out["flagged_nodes"], list)
    assert isinstance(out["risk_score"], float)
    assert "v2" in out  # additive richer block


def test_empty_component_is_clean():
    out = analyze_component_sync({"graph_id": "G", "node_ids": [], "nodes": [], "edges": []})
    assert out["verdict"] == "CLEAN"
    assert out["flagged_nodes"] == []


# ── core requirement: no blanket scoring ──────────────────────────────────────
def test_nodes_score_independently():
    comp, _ = Simulator().hybrid()
    out = analyze_component_sync(comp)
    scores = list(out["v2"]["node_risk_scores"].values())
    assert len(set(round(s, 2) for s in scores)) > 3, "nodes must NOT share one blanket score"
    assert max(scores) - min(scores) > 0.3, "must differentiate origin from periphery"


# ── detection per archetype ───────────────────────────────────────────────────
@pytest.mark.parametrize("maker,expected_pattern", [
    ("layering", "layering"),
    ("smurfing", "smurfing"),
    ("fan_out", "fan_out"),
    ("fan_in", "fan_in"),
    ("circular", "circular_flow"),
    ("mule_network", "mule_accounts"),
    ("cashout_network", "cashout"),
    ("synthetic_ring", "synthetic_networks"),
])
def test_archetype_detected(maker, expected_pattern):
    comp, gt = getattr(Simulator(), maker)()
    out = analyze_component_sync(comp)
    assert out["verdict"] in ("FRAUD", "SUSPICIOUS"), f"{maker} should be flagged"
    patterns = out["v2"]["cluster_intelligence"]["patterns_detected"]
    assert expected_pattern in patterns, f"{maker} should detect {expected_pattern}, got {patterns}"


def test_normal_is_not_flagged():
    sim = Simulator(seed=3)
    flagged = 0
    for i in range(12):
        comp, _ = sim.normal(gid=f"N{i}", n_accounts=sim.rng.randint(4, 9))
        out = analyze_component_sync(comp)
        if out["verdict"] in ("FRAUD", "SUSPICIOUS"):
            flagged += 1
    assert flagged <= 2, f"normal clusters should rarely flag, got {flagged}/12"


# ── evidence + explainability ─────────────────────────────────────────────────
def test_evidence_and_explanations_present():
    comp, _ = Simulator().mule_network()
    eng = BlueTeamV2Engine()
    analysis = eng.analyze_component(comp)
    assert analysis.evidence, "fraud must produce evidence, not just a score"
    for ev in analysis.evidence:
        assert ev.nodes and 0 <= ev.severity <= 1 and ev.description
    assert analysis.narrative
    # contributions sum sanity per node
    for m in analysis.metrics.values():
        if m.contributions:
            assert abs(sum(m.contributions.values()) - 1.0) < 0.06


# ── cluster intelligence hierarchy ────────────────────────────────────────────
def test_cluster_hierarchy_built():
    comp, _ = Simulator().hybrid()
    out = analyze_component_sync(comp)
    h = out["v2"]["cluster_intelligence"]["hierarchy"]
    assert h["origin"], "hybrid network must have an origin"
    assert h["cashout"] or h["sinks"], "hybrid network must terminate somewhere"


# ── isolation: each component analysed independently ──────────────────────────
def test_components_are_isolated():
    sim = Simulator()
    c1, _ = sim.circular(gid="A")
    c2, _ = sim.normal(gid="B", n_accounts=5)
    results = asyncio.run(analyze_all_components([c1, c2]))
    by_id = {r["graph_id"]: r for r in results}
    # the circular cluster's nodes must never leak into the normal cluster's verdict
    assert set(by_id["A"]["nodes"]).isdisjoint(set(by_id["B"]["nodes"]))


# ── scalability smoke ─────────────────────────────────────────────────────────
def test_scales_to_2000_nodes():
    comp, _ = Simulator(seed=1).scale_test(2000)
    out = analyze_component_sync(comp)
    assert out["verdict"] in {v.value for v in Verdict}
    assert out["v2"]["timing_ms"] < 15000  # generous ceiling
