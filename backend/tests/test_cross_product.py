"""Tests for the cross-product knowledge layer (Phases 1/4/9/10/11)."""
from knowledge import (
    KB,
    EntityType,
    classify_entity,
    classify_node,
    cross_product_report,
    detect_xp_signals,
)


# ── synthetic datasets ────────────────────────────────────────────────────────
def _edges(specs):
    """specs: (src, tgt, amount, rail, hour[, device])."""
    out = []
    for i, s in enumerate(specs):
        src, tgt, amt, rail = s[0], s[1], s[2], s[3]
        hour = s[4] if len(s) > 4 else 10
        dev = s[5] if len(s) > 5 else ""
        out.append({"source": src, "target": tgt, "amount": amt, "payment_rail": rail,
                    "timestamp": f"2026-01-01T{hour:02d}:{i % 60:02d}:00", "device_id": dev})
    return out


def _component(node_ids, specs):
    return {"graph_id": "GRAPH_001", "node_ids": list(node_ids),
            "nodes": [{"id": n} for n in node_ids], "edges": _edges(specs)}


# salary → 2 wallets → merchant → cash-out, all on one device, structured amounts
CROSS_PRODUCT_FRAUD = _component(
    ["SAL_001", "WALLET_1", "WALLET_2", "MERCHANT_9", "CASH_OUT_1"],
    [("SAL_001", "WALLET_1", 48000, "UPI", 10, "DEV9"),
     ("SAL_001", "WALLET_2", 47000, "IMPS", 10, "DEV9"),
     ("WALLET_1", "MERCHANT_9", 47500, "UPI", 11, "DEV9"),
     ("WALLET_2", "MERCHANT_9", 46500, "RTGS", 11, "DEV9"),
     ("MERCHANT_9", "CASH_OUT_1", 92000, "CASH_OUT", 12, "DEV9")],
)

# legitimate single-product activity: a few normal savings transfers, distinct devices
LEGIT = _component(
    ["ACC_A", "ACC_B", "ACC_C"],
    [("ACC_A", "ACC_B", 2500, "UPI", 9, "DEVA"),
     ("ACC_B", "ACC_C", 1800, "UPI", 14, "DEVB")],
)


# ── knowledge base ──────────────────────────────────────────────────────────
def test_kb_inventory():
    s = KB.summary()
    assert s["counts"]["xp_rules"] == 15
    assert s["counts"]["products"] >= 10
    assert "wallet_layering" in KB.typologies
    assert KB.recovery_action("freeze_wallet")["action"] == "FREEZE_WALLET"


# ── entity taxonomy (Phase 1/9) ───────────────────────────────────────────────
def test_entity_classification():
    assert classify_entity({"id": "WALLET_1"}) == EntityType.WALLET
    assert classify_entity({"id": "SAL_001"}) == EntityType.SALARY_ACCOUNT
    assert classify_entity({"id": "CASH_OUT_1"}) == EntityType.CASH_ENDPOINT
    assert classify_entity({"id": "X", "account_type": "merchant"}) == EntityType.MERCHANT
    assert classify_entity({"id": "RANDOM"}) == EntityType.ACCOUNT  # generic fallback
    meta = classify_node({"id": "UPI_7"})
    assert meta["entity_type"] == "upi_id" and meta["entity_category"] == "payment"


# ── XP detection (Phase 4/11) ─────────────────────────────────────────────────
def test_xp_detects_cross_product_fraud():
    xp = {s["xp_id"] for s in detect_xp_signals(CROSS_PRODUCT_FRAUD)}
    assert "XP009" in xp   # shared device across accounts
    assert "XP004" in xp   # wallet layering
    assert "XP012" in xp   # structuring just below thresholds across rails


def test_xp_quiet_on_legit_activity():
    # legitimate low-value single-product activity must not trip XP rules
    assert detect_xp_signals(LEGIT) == []


def test_shared_device_needs_three_accounts():
    # a device on only two accounts should NOT fire XP009
    comp = _component(["A", "B"], [("A", "B", 100, "UPI", 9, "DEVX")])
    assert not any(s["xp_id"] == "XP009" for s in detect_xp_signals(comp))


# ── unified cross-product report (Phase 8-lite) ────────────────────────────────
def test_cross_product_report_fraud():
    r = cross_product_report(CROSS_PRODUCT_FRAUD)
    assert r["is_cross_product"] is True
    assert r["xp_rule_count"] >= 3
    assert any(t["typology"] == "wallet_layering" for t in r["matched_typologies"])
    actions = {a["action"] for a in r["recovery_actions"]}
    assert actions & {"FREEZE_WALLET", "LIMIT_WALLET"}            # wallet recovery
    assert all("why" in a and "risk_reduction" in a for a in r["recovery_actions"])
    assert r["regulatory_hooks"]                                  # cited frameworks
    # entity taxonomy exposed for graph semantics
    assert r["entities"]["WALLET_1"]["entity_category"] == "digital"


def test_cross_product_report_legit_is_quiet():
    r = cross_product_report(LEGIT)
    assert r["is_cross_product"] is False
    assert r["xp_signals"] == []


def test_empty_component_safe():
    assert detect_xp_signals({"graph_id": "G", "node_ids": [], "nodes": [], "edges": []}) == []


# ── increment 2: heterogeneous graph, scenarios, identity XP, customer risk ───
from knowledge import HeteroGraph, EntityType as ET, compute_customer_risk, scenarios


def test_hetero_builder_emits_standard_component():
    g = HeteroGraph("G1")
    g.customer("CUST_1")
    g.product("SAV_1", ET.SAVINGS_ACCOUNT, owner="CUST_1")
    g.has_device("SAV_1", "DEV_1")
    g.transfer("SAV_1", "ACC_2", 5000, "UPI", "2026-01-01T10:00:00", "DEV_1")
    comp = g.component()
    assert comp["graph_id"] == "G1"
    assert {"CUST_1", "SAV_1", "DEV_1", "ACC_2"} <= set(comp["node_ids"])
    rels = {e.get("relationship_type") for e in comp["edges"]}
    assert {"OWNS", "HAS_DEVICE", "TRANSFERRED"} <= rels


def test_each_fraud_scenario_trips_its_signature_rule():
    expected = {
        "wallet_layering": "XP004",
        "shared_device_ring": "XP009",
        "loan_laundering": "XP003",
        "shared_identity_ring": "XP011",
    }
    for name, xp in expected.items():
        comp = scenarios.generate(name)
        fired = {s["xp_id"] for s in detect_xp_signals(comp)}
        assert xp in fired, f"{name} should trip {xp}, got {fired}"


def test_legit_scenario_is_quiet_no_false_positive():
    comp = scenarios.generate("legit_customer")
    assert detect_xp_signals(comp) == []
    r = cross_product_report(comp)
    assert r["is_cross_product"] is False


def test_shared_identity_detects_pan_and_phone():
    comp = scenarios.generate("shared_identity_ring")
    fired = {s["xp_id"] for s in detect_xp_signals(comp)}
    assert {"XP010", "XP011"} <= fired


def test_customer_risk_propagates_from_products_and_identity():
    comp = scenarios.generate("shared_device_ring")
    cr = compute_customer_risk(comp)
    assert cr["available"] is True
    assert cr["customers"], "device ring should raise customer risk"
    top = cr["customers"][0]
    assert top["risk_level"] in ("HIGH", "CRITICAL")
    assert top["triggered_rules"]                       # XP rules cited
    assert top["propagation_path"]                      # explains how risk reached the customer
    assert top["confidence"] > 0
    # devices surface as their own risk entities
    assert any(d["entity"] == "DEV_RING" for d in cr["devices"])


def test_customer_risk_quiet_on_legit():
    cr = compute_customer_risk(scenarios.generate("legit_customer"))
    assert cr["available"] is False
    assert cr["customers"] == []


# ── increment 3: live correlation, investigation report, red-team eval ────────
from knowledge.blue_team_xp import correlate
from knowledge.investigation import build_customer_investigation
from knowledge.red_team import evaluate_blue_team


def test_correlate_is_defensive_and_summarises():
    c = correlate(scenarios.generate("wallet_layering"))
    assert c["is_cross_product"] is True
    assert any(r["xp_id"] == "XP004" for r in c["xp_rules"])
    assert c["recovery_actions"]
    # never raises and stays quiet on junk input
    assert correlate({"graph_id": "G", "nodes": [], "edges": []})["is_cross_product"] is False


def test_customer_investigation_report_sections():
    rep = build_customer_investigation(scenarios.generate("wallet_layering"), "CUST_100")
    assert rep["customer"] == "CUST_100"
    owned = {p["product"] for p in rep["products_owned"]}
    assert {"SAL_100", "WALLET_1", "WALLET_2"} <= owned
    assert rep["device_intelligence"]                       # DEV_A surfaced
    assert rep["cross_product"]["xp_rules"]                 # XP rules listed
    assert rep["recommendations"]                           # recovery actions
    assert isinstance(rep["narrative"], str) and "CUST_100" in rep["narrative"]
    for section in ("money_trails", "timeline", "fraud_motifs", "connected_products"):
        assert section in rep


def test_investigation_pivots_from_account_to_owner():
    # passing an owned product id resolves to its owning customer
    rep = build_customer_investigation(scenarios.generate("wallet_layering"), "WALLET_1")
    assert rep["customer"] == "CUST_100"


def test_red_team_eval_full_coverage_no_false_positives():
    ev = evaluate_blue_team()
    assert ev["attacks_fully_detected"] == ev["total_attacks"]   # every attack caught
    assert ev["rule_coverage"] == 1.0
    assert ev["clean_on_legitimate"] is True                     # no FP on legit
    assert ev["false_positive_count"] == 0


# ── increment 4: live heterogeneous ingestion (augmenter) ─────────────────────
from knowledge import augment_component, record_account, empty_context


def test_augment_is_passthrough_without_context():
    comp = LEGIT
    assert augment_component(comp, None) is comp
    assert augment_component(comp, empty_context()) is comp


def test_augment_adds_ownership_and_identity_edges():
    # money-only component (as the live graph produces it)
    comp = {"graph_id": "G", "node_ids": ["ACC_1", "ACC_2"],
            "nodes": [{"id": "ACC_1"}, {"id": "ACC_2"}],
            "edges": [{"source": "ACC_1", "target": "ACC_2", "amount": 5000,
                       "payment_rail": "UPI", "timestamp": "2026-01-01T10:00:00"}]}
    ctx = empty_context()
    record_account(ctx, "ACC_1", entity_type="savings_account", customer="CUST_1",
                   phone="9990001111", pan="ABCDE1234F", device="DEV_1")
    het = augment_component(comp, ctx)
    rels = {e.get("relationship_type") for e in het["edges"]}
    assert {"OWNS", "HAS_PHONE", "HAS_PAN", "HAS_DEVICE"} <= rels
    assert "CUST_1" in het["node_ids"]
    acc1 = next(n for n in het["nodes"] if n["id"] == "ACC_1")
    assert acc1["entity_type"] == "savings_account"
    # original component is untouched
    assert all("relationship_type" not in e for e in comp["edges"])


def test_shared_phone_via_ingestion_context_trips_xp010():
    # two accounts transacting, sharing one mobile number → XP010 after augmentation
    comp = {"graph_id": "G", "node_ids": ["ACC_1", "ACC_2", "SINK"],
            "nodes": [{"id": "ACC_1"}, {"id": "ACC_2"}, {"id": "SINK"}],
            "edges": [{"source": "ACC_1", "target": "SINK", "amount": 5000, "payment_rail": "UPI",
                       "timestamp": "2026-01-01T10:00:00"},
                      {"source": "ACC_2", "target": "SINK", "amount": 6000, "payment_rail": "UPI",
                       "timestamp": "2026-01-01T10:05:00"}]}
    ctx = empty_context()
    record_account(ctx, "ACC_1", phone="9990001111")
    record_account(ctx, "ACC_2", phone="9990001111")   # same phone → shared identity
    fired = {s["xp_id"] for s in detect_xp_signals(augment_component(comp, ctx))}
    assert "XP010" in fired


def test_own_device_across_own_accounts_is_not_shared_device():
    # one customer, own device on their own two accounts + a merchant payment
    g = HeteroGraph("OWN")
    g.customer("C")
    g.product("SAV_A", ET.SAVINGS_ACCOUNT, owner="C")
    g.product("SAV_B", ET.SAVINGS_ACCOUNT, owner="C")
    g.has_device("SAV_A", "D")
    g.has_device("SAV_B", "D")
    g.add_entity("MERCH", ET.MERCHANT)
    g.transfer("SAV_A", "SAV_B", 1000, "IMPS", "2026-01-01T10:00:00", "D")
    g.transfer("SAV_B", "MERCH", 200, "UPI", "2026-01-01T11:00:00", "D")
    assert not any(s["xp_id"] == "XP009" for s in detect_xp_signals(g.component()))
