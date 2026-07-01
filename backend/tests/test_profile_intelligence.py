"""
Profile Intelligence — proves the Blue Team evaluates behaviour RELATIVE to the
customer profile: the same transaction is routine for one customer and alarming for
another, false positives drop for legitimate high-volume customers, and every
decision is explainable.
"""
from __future__ import annotations

from profile_intelligence import (AccountFeatures, assess_component, evaluate,
                                   get_profile, infer_profile)
from risk_engine import assess


def _comp(profiles=None):
    """A business-scale fan-out: ₹25L to three recipients."""
    c = {
        "graph_id": "G1",
        "node_ids": ["ACC_1", "ACC_2", "ACC_3", "ACC_4"],
        "nodes": [{"id": "ACC_1", "account_type": "savings"}, {"id": "ACC_2"},
                  {"id": "ACC_3"}, {"id": "ACC_4"}],
        "edges": [
            {"source": "ACC_1", "target": "ACC_2", "amount": 2500000, "payment_rail": "RTGS", "timestamp": "2026-01-01T10:00:00"},
            {"source": "ACC_1", "target": "ACC_3", "amount": 2400000, "payment_rail": "RTGS", "timestamp": "2026-01-01T10:01:00"},
            {"source": "ACC_1", "target": "ACC_4", "amount": 2300000, "payment_rail": "RTGS", "timestamp": "2026-01-01T10:02:00"},
        ],
    }
    if profiles:
        c["customer_profiles"] = profiles
    return c


# ── the headline property: same behaviour, different profile, different risk ──
def test_same_amount_is_normal_for_business_abnormal_for_salaried():
    bo = evaluate(get_profile("business_owner"), AccountFeatures("A", max_txn=2500000, out_deg=3))
    sal = evaluate(get_profile("salaried_employee"), AccountFeatures("A", max_txn=2500000, out_deg=3))
    assert bo["deviation"] < 0.1 and bo["mitigation"] > 0.3      # routine for a business
    assert sal["deviation"] > 0.4 and sal["adjustment_pct"] > 0  # alarming for an employee
    assert sal["adjustment_pct"] > bo["adjustment_pct"]


def test_risk_engine_is_profile_relative():
    sal = assess(_comp({"ACC_1": "salaried_employee"}))
    biz = assess(_comp({"ACC_1": "business_owner"}))
    # identical transactions → the salaried account is materially riskier
    assert sal["score"] > biz["score"]
    assert any(f["key"] == "profile_deviation" for f in sal["factors"])


def test_large_amount_alone_does_not_inflate_business_risk():
    """'Large transactions alone should NOT increase risk' — for a Business Owner the
    amount factor is dampened by the profile mitigation."""
    biz = assess(_comp({"ACC_1": "business_owner"}))
    amount_factor = next((f for f in biz["factors"] if f["key"] == "amount"), None)
    # the ₹25L amount is recognised as routine → amount contributes little or nothing
    assert amount_factor is None or amount_factor["points"] <= 5


# ── profile evaluation signals ───────────────────────────────────────────────
def test_student_receiving_from_many_sources_is_flagged():
    e = evaluate(get_profile("student"), AccountFeatures("S", in_deg=12, max_txn=40000))
    assert e["deviation"] > 0.1
    assert any("sources" in r for r in e["reasons"])


def test_farmer_seasonal_amount_within_envelope_is_not_flagged():
    e = evaluate(get_profile("farmer"), AccountFeatures("F", max_txn=180000, in_deg=2))
    assert e["deviation"] < 0.1   # ₹1.8L harvest credit is within a farmer's envelope


def test_cash_unexpected_for_salaried_raises_deviation():
    e = evaluate(get_profile("salaried_employee"),
                 AccountFeatures("A", max_txn=120000, cash=True))
    assert e["deviation"] > 0.0
    assert any("Cash" in r for r in e["reasons"])


# ── inference ────────────────────────────────────────────────────────────────
def test_inference_explicit_override_wins():
    key, conf, _ = infer_profile(AccountFeatures("A", out_deg=20), explicit="farmer")
    assert key == "farmer" and conf == 1.0


def test_inference_account_type_prior():
    key, _, _ = infer_profile(AccountFeatures("A", account_type="salary_account"))
    assert key == "salaried_employee"


def test_inference_distributor_behaviour():
    key, _, _ = infer_profile(AccountFeatures("A", out_deg=10, total_out=50_00_000, max_txn=8_00_000))
    assert key == "business_owner"


# ── explainability + shape ───────────────────────────────────────────────────
def test_assessment_is_explainable():
    r = assess_component(_comp({"ACC_1": "salaried_employee"}))
    assert r["available"] is True
    assert r["explanation"] and "Salaried Employee" in r["explanation"]
    acc = r["accounts"]["ACC_1"]
    assert acc["expected"] and acc["current"] and acc["reasons"]
    assert -100 <= acc["adjustment_pct"] <= 100


def test_graceful_with_no_data():
    r = assess_component({"graph_id": "G", "node_ids": [], "nodes": [], "edges": []})
    assert r["available"] is False
    assert r["component_deviation"] == 0.0 and r["amount_mitigation"] == 0.0
