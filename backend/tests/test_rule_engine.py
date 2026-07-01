"""Tests for the AML rule + motif engine (rule_engine.py)."""
from rule_engine import (
    PATTERN_TO_RULES,
    RULES,
    extract_motifs,
    extract_topology_motifs,
    rules_for,
    severity_label,
)


def _component():
    # SRC fans out to 3 mules, all reconverge on CASH — a diamond/smurfing ring
    nodes = [{"id": n, "account_type": "normal"} for n in ["SRC", "M1", "M2", "M3"]]
    nodes.append({"id": "CASH", "account_type": "cash"})
    edges = []
    for i, m in enumerate(["M1", "M2", "M3"]):
        edges.append({"source": "SRC", "target": m, "amount": 90000, "timestamp": f"2026-01-01T10:0{i}:00", "risk_score": 0.7})
        edges.append({"source": m, "target": "CASH", "amount": 88000, "timestamp": f"2026-01-01T11:0{i}:00", "risk_score": 0.9})
    return {"graph_id": "GRAPH_001", "node_ids": [n["id"] for n in nodes], "nodes": nodes, "edges": edges}


def test_every_pattern_maps_to_a_valid_rule():
    for pattern, rule_ids in PATTERN_TO_RULES.items():
        assert rule_ids, f"{pattern} has no rule"
        for rid in rule_ids:
            assert rid in RULES, f"{rid} missing from catalogue"


def test_severity_labels():
    assert severity_label(0.9) == "CRITICAL"
    assert severity_label(0.7) == "HIGH"
    assert severity_label(0.5) == "MEDIUM"
    assert severity_label(0.1) == "LOW"


def test_rules_for_resolves_objects():
    rs = rules_for("diamond")
    assert rs and rs[0]["rule_id"] == "AML003"
    assert "name" in rs[0] and "description" in rs[0]


def test_extract_motifs_returns_self_describing_objects():
    motifs = extract_motifs(_component())
    assert motifs, "fraud ring should yield motifs"
    m = motifs[0]
    for key in ("motif_id", "pattern", "label", "confidence", "severity",
                "nodes", "edges", "triggered_rules", "evidence", "explanation"):
        assert key in m, f"motif missing {key}"
    # every motif must be traceable to at least one AML rule
    assert all(len(mo["triggered_rules"]) >= 1 for mo in motifs)


def test_motif_edges_are_internal_to_the_motif():
    motifs = extract_motifs(_component())
    for m in motifs:
        ns = set(m["nodes"])
        for e in m["edges"]:
            assert e["source"] in ns and e["target"] in ns


def test_motifs_sorted_strongest_first():
    motifs = extract_motifs(_component())
    scores = [m["severity_score"] for m in motifs]
    assert scores == sorted(scores, reverse=True)


def test_known_fraud_patterns_detected():
    patterns = {m["pattern"] for m in extract_motifs(_component())}
    # a fan-out → reconverge → cash ring must surface laundering-family motifs
    assert patterns & {"smurfing", "diamond", "mule_accounts", "cashout", "hybrid_network"}


def test_empty_component_yields_no_motifs():
    empty = {"graph_id": "GRAPH_001", "node_ids": [], "nodes": [], "edges": []}
    assert extract_motifs(empty) == []


# ── topology motifs (Bundle C) ────────────────────────────────────────────────
def _topo(edges):
    nodes = {}
    for s, t in edges:
        nodes.setdefault(s, {"id": s})
        nodes.setdefault(t, {"id": t})
    ed = [{"source": s, "target": t, "amount": 1000, "risk_score": 0.5,
           "timestamp": "2026-01-01T10:00:00"} for s, t in edges]
    return {"graph_id": "GRAPH_001", "node_ids": list(nodes), "nodes": list(nodes.values()), "edges": ed}


def test_star_hub_detected():
    comp = _topo([("HUB", f"L{i}") for i in range(6)])  # one hub → 6 leaves
    pats = {m["pattern"] for m in extract_topology_motifs(comp)}
    assert "star" in pats


def test_hourglass_detected():
    # P1,P2,P3 → W → S1,S2,S3  (converge then diverge through one waist)
    edges = [("P1", "W"), ("P2", "W"), ("P3", "W"), ("W", "S1"), ("W", "S2"), ("W", "S3")]
    motifs = extract_topology_motifs(_topo(edges))
    hg = next((m for m in motifs if m["pattern"] == "hourglass"), None)
    assert hg is not None
    assert "W" in hg["nodes"]
    assert hg["triggered_rules"]  # maps to AML023


def test_double_diamond_detected():
    # split A→{B,C}→D, then D→{E,F}→G  (two chained diamonds)
    edges = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"),
             ("D", "E"), ("D", "F"), ("E", "G"), ("F", "G")]
    motifs = extract_topology_motifs(_topo(edges))
    assert any(m["pattern"] == "double_diamond" for m in motifs)


def test_topology_motifs_are_internal_and_traceable():
    comp = _topo([("HUB", f"L{i}") for i in range(6)])
    for m in extract_topology_motifs(comp):
        ns = set(m["nodes"])
        assert all(e["source"] in ns and e["target"] in ns for e in m["edges"])
        assert len(m["triggered_rules"]) >= 1
