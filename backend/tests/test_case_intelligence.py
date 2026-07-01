"""Tests for case intelligence (P4) + recommendation engine (P11)."""
from blue_team_v2.engine import BlueTeamV2Engine
from case_intelligence import build_case_summary
from recommendation_engine import recommend
from rule_engine import extract_motifs


def _ring():
    nodes = [{"id": n, "account_type": "normal"} for n in ["SRC", "M1", "M2", "M3"]]
    nodes.append({"id": "CASH", "account_type": "cash"})
    edges = []
    for i, m in enumerate(["M1", "M2", "M3"]):
        edges.append({"source": "SRC", "target": m, "amount": 90000, "timestamp": f"2026-01-01T10:0{i}:00", "risk_score": 0.7})
        edges.append({"source": m, "target": "CASH", "amount": 88000, "timestamp": f"2026-01-01T11:0{i}:00", "risk_score": 0.9})
    return {"graph_id": "GRAPH_001", "node_ids": [n["id"] for n in nodes], "nodes": nodes, "edges": edges}


def _clean():
    nodes = [{"id": n} for n in ["P", "Q"]]
    edges = [{"source": "P", "target": "Q", "amount": 1500, "timestamp": "2026-01-01T10:00:00", "risk_score": 0.05}]
    return {"graph_id": "GRAPH_001", "node_ids": ["P", "Q"], "nodes": nodes, "edges": edges}


def test_case_summary_has_all_required_fields():
    s = build_case_summary(_ring())
    for key in ("case_summary", "verdict", "risk_score", "risk_level", "confidence",
                "total_transactions", "total_exposure", "total_suspicious_amount",
                "money_origin", "final_beneficiary", "estimated_layering_depth",
                "highest_risk_entity", "fraud_patterns", "recommended_actions"):
        assert key in s, f"missing {key}"


def test_case_summary_identifies_origin_and_beneficiary():
    s = build_case_summary(_ring())
    assert "SRC" in s["money_origin"]
    assert "CASH" in s["final_beneficiary"]
    assert s["total_transactions"] == 6
    assert s["total_exposure"] > 0
    assert s["estimated_layering_depth"] >= 1


def test_case_summary_flags_fraud_with_patterns():
    s = build_case_summary(_ring())
    assert s["verdict"] in ("FRAUD", "SUSPICIOUS")
    assert s["fraud_patterns"]
    assert s["highest_risk_entity"] is not None


def test_recommendations_are_self_explaining_and_prioritised():
    comp = _ring()
    analysis = BlueTeamV2Engine().analyze_component(comp)
    motifs = extract_motifs(comp, analysis=analysis)
    recs = recommend(analysis, motifs)
    assert recs
    for r in recs:
        assert r["action"] and r["reason"] and "priority" in r
    # prioritised descending
    priorities = [r["priority"] for r in recs]
    assert priorities == sorted(priorities, reverse=True)
    # a cash-out ring must recommend freezing and SAR escalation
    actions = {r["action"] for r in recs}
    assert "FREEZE_ACCOUNT" in actions
    assert "ESCALATE_SAR" in actions


def test_clean_cluster_only_monitors():
    analysis = BlueTeamV2Engine().analyze_component(_clean())
    recs = recommend(analysis, [])
    assert [r["action"] for r in recs] == ["MONITOR"]


def test_clean_cluster_summary_is_low_risk():
    s = build_case_summary(_clean())
    assert s["risk_level"] in ("LOW", "MEDIUM")
    assert s["verdict"] in ("CLEAN", "LOGGED")


def test_case_summary_extended_rollups():
    s = build_case_summary(_ring())
    for key in ("timeline", "largest_community", "highest_risk_community",
                "largest_layering_chain", "highest_betweenness_node",
                "most_connected_node", "money_trail_summary", "money_trail_assessment"):
        assert key in s, f"missing {key}"
    # timeline rolled up the 6 timestamped transactions
    assert s["timeline"]["available"] is True
    assert s["timeline"]["timed_transactions"] == 6
    # largest layering chain has a concrete node path
    assert s["largest_layering_chain"]["length"] >= 1
    assert "SRC" in s["largest_layering_chain"]["chain"]
    # the money-trail story is investigator prose
    assert isinstance(s["money_trail_summary"], str) and "originated" in s["money_trail_summary"]
