"""
Cross-Bank Intelligence regression suite.

The module is a PLUG-IN enrichment layer: it answers "has this entity behaved
suspiciously at OTHER banks?" via fingerprint-based entity resolution + a cross-bank
risk registry. It must (a) detect the cross-bank behaviours, (b) stay quiet on benign
single-bank traffic, (c) NEVER mutate the graph, and (d) feed risk_engine only as a
capped factor that can never alone create a case.
"""
from __future__ import annotations

import copy

from cross_bank_intelligence import analyze_component, CrossBankRiskRegistry
from cross_bank_intelligence.entity_resolution import resolve_entities
from cross_bank_intelligence.fingerprints import build_fingerprints


def _fresh_registry():
    # Isolated registry seeded with one known phone → no global-state leakage.
    return CrossBankRiskRegistry(seed=[{
        "fingerprint": "PHONE_KNOWN_1", "kind": "phone",
        "banks_seen": ["SBI", "HDFC", "ICICI"], "accounts_seen": 9,
        "known_fraud_cases": 2, "risk_score": 84,
    }])


def _comp(nodes, edges):
    return {"node_ids": nodes, "nodes": [{"id": n} for n in nodes], "edges": edges}


# ── 1. benign single-bank traffic stays quiet ─────────────────────────────────
def test_benign_single_bank_quiet():
    c = _comp(["X", "Y"], [{"source": "X", "target": "Y", "amount": 5000, "payment_rail": "UPI"}])
    r = analyze_component(c, None, registry=_fresh_registry())
    assert r["available"] is False
    assert r["cross_bank_risk"] == 0
    assert r["cross_bank_patterns"] == []


# ── 2. multi-bank layering detected ───────────────────────────────────────────
def test_multi_bank_layering():
    c = _comp(["A", "B", "C", "D"], [
        {"source": "A", "target": "B", "amount": 1500000, "payment_rail": "RTGS"},
        {"source": "B", "target": "C", "amount": 1450000, "payment_rail": "NEFT"},
        {"source": "C", "target": "D", "amount": 1400000, "payment_rail": "IMPS"},
    ])
    ec = {"banks": {"A": "SBI", "B": "HDFC", "C": "ICICI", "D": "AXIS"}, "links": [], "owns": {}, "types": {}}
    r = analyze_component(c, ec, registry=_fresh_registry())
    assert "multi_bank_layering" in r["cross_bank_patterns"]
    assert r["linked_banks"] >= 4
    assert r["cross_bank_risk"] > 0


# ── 3. same device across multiple banks ──────────────────────────────────────
def test_same_device_multi_bank():
    c = _comp(["A", "B"], [{"source": "A", "target": "B", "amount": 90000, "payment_rail": "IMPS"}])
    ec = {"banks": {"A": "HDFC", "B": "SBI"}, "owns": {}, "types": {},
          "links": [["A", "DEV_X", "HAS_DEVICE"], ["B", "DEV_X", "HAS_DEVICE"]]}
    r = analyze_component(c, ec, registry=_fresh_registry())
    assert "same_device_multi_bank" in r["cross_bank_patterns"]
    assert r["shared_devices"] >= 1


# ── 4. same phone across many accounts ────────────────────────────────────────
def test_same_phone_multiple_accounts():
    nodes = ["m1", "m2", "m3", "agg"]
    edges = [{"source": m, "target": "agg", "amount": 80000, "payment_rail": "UPI"} for m in ["m1", "m2", "m3"]]
    ec = {"banks": {}, "owns": {}, "types": {},
          "links": [[m, "PHONE_SHARED", "HAS_PHONE"] for m in nodes]}
    r = analyze_component(_comp(nodes, edges), ec, registry=_fresh_registry())
    assert "same_phone_multiple_accounts" in r["cross_bank_patterns"]


# ── 5. known suspicious entity (registry hit) ─────────────────────────────────
def test_known_suspicious_entity():
    c = _comp(["A", "B"], [{"source": "A", "target": "B", "amount": 100000, "payment_rail": "IMPS"}])
    ec = {"banks": {"A": "UNION_BANK", "B": "UNION_BANK"}, "owns": {}, "types": {},
          "links": [["A", "PHONE_KNOWN_1", "HAS_PHONE"]]}
    r = analyze_component(c, ec, registry=_fresh_registry())
    assert "known_suspicious_entity" in r["cross_bank_patterns"]
    assert r["known_suspicious_entities"] >= 1
    assert r["accounts"]["A"]["known_suspicious"] is True
    assert r["accounts"]["A"]["cross_bank_risk"] >= 80


# ── 6. same device, different KYC names ───────────────────────────────────────
def test_same_device_different_names():
    c = _comp(["A", "B"], [{"source": "A", "target": "B", "amount": 50000, "payment_rail": "UPI"}])
    ec = {"banks": {}, "owns": {"A": "Rahul", "B": "Aman"}, "types": {},
          "links": [["A", "DEV_Z", "HAS_DEVICE"], ["B", "DEV_Z", "HAS_DEVICE"]]}
    r = analyze_component(c, ec, registry=_fresh_registry())
    assert "same_device_different_names" in r["cross_bank_patterns"]


# ── 7. entity resolution links accounts by shared fingerprint ─────────────────
def test_entity_resolution_links_shared_fingerprint():
    c = _comp(["A", "B", "C"], [])
    ec = {"banks": {}, "owns": {}, "types": {},
          "links": [["A", "DEV_1", "HAS_DEVICE"], ["B", "DEV_1", "HAS_DEVICE"]]}
    fp = build_fingerprints(c, ec)
    clusters = resolve_entities(fp)
    assert set(clusters["A"]) == {"A", "B"}     # A and B resolve to one entity
    assert clusters["C"] == ["C"]               # C is separate


# ── 8. risk_engine factor is CAPPED — cross-bank never alone creates a case ────
def test_cross_bank_factor_capped_in_risk_engine():
    from risk_engine import assess
    # structurally trivial transfer + a KNOWN cross-bank entity → cross-bank adds
    # at most its weight (10); the case threshold (70) is never reached on this alone.
    c = _comp(["A", "B"], [{"source": "A", "target": "B", "amount": 20000, "payment_rail": "UPI"}])
    c["entity_context"] = {"banks": {"A": "UNION_BANK", "B": "SBI"}, "owns": {}, "types": {},
                           "links": [["A", "PHONE_9800000001", "HAS_PHONE"]]}  # default-registry known
    a = assess(c)
    cb = next((f for f in a["factors"] if f["key"] == "cross_bank"), None)
    if cb:
        assert cb["points"] <= 10            # capped at the weight
    assert a["should_create_case"] is False  # cross-bank alone cannot trip a case


# ── 9. the module NEVER mutates the graph snapshot ────────────────────────────
def test_graph_snapshot_untouched():
    c = _comp(["A", "B", "C"], [
        {"source": "A", "target": "B", "amount": 100000, "payment_rail": "IMPS"},
        {"source": "B", "target": "C", "amount": 95000, "payment_rail": "NEFT"},
    ])
    ec = {"banks": {"A": "SBI", "B": "HDFC", "C": "ICICI"}, "owns": {}, "types": {},
          "links": [["A", "PHONE_KNOWN_1", "HAS_PHONE"]]}
    before = copy.deepcopy(c)
    analyze_component(c, ec, registry=_fresh_registry())
    assert c == before, "cross-bank analysis must not mutate the component"


# ── 10. registry accumulates live sightings (the Kafka seam) ──────────────────
def test_registry_accumulates_sightings():
    reg = CrossBankRiskRegistry(seed=[])
    assert reg.is_known("DEV_NEW") is False
    reg.register_sighting("DEV_NEW", "device", "SBI")
    reg.register_sighting("DEV_NEW", "device", "HDFC", fraud=True)
    e = reg.lookup("DEV_NEW")
    assert e is not None
    assert set(e["banks_seen"]) == {"SBI", "HDFC"}
    assert e["known_fraud_cases"] == 1
    assert e["risk_score"] > 0
