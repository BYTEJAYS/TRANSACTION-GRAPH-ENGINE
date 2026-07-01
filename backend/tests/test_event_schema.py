"""
Enterprise event schema + normalization — proves BOTH formats work, normalize to
one internal model, validate correctly, and feed the intelligence engines.
"""
from __future__ import annotations

import pytest

from models.normalize import normalize_payload

# ── the legacy lightweight format (must keep working unchanged) ───────────────
LEGACY = [
    {"from_account": "ACC_1001", "to_account": "ACC_2001", "amount": 500, "payment_rail": "UPI", "timestamp": "2026-05-15T02:30:00"},
    {"from_account": "ACC_2001", "to_account": "ACC_3001", "amount": 500, "payment_rail": "IMPS", "timestamp": "2026-05-15T02:30:30"},
]

# ── the enterprise envelope (schema 2.0) ──────────────────────────────────────
ENTERPRISE = {
    "schema_version": "2.0",
    "dataset_id": "UB-DEMO-001",
    "investigation_id": "INV-2026-114",
    "source_system": "CBS",
    "transactions": [
        {
            "transaction_id": "TXN-1",
            "from_account": "ACC_1001", "to_account": "MERCH_9",
            "amount": 2500000, "product": "rtgs",
            "payment": {"rail": "RTGS", "channel": "internet_banking", "currency": "INR",
                        "direction": "external", "domestic": True, "narration": "vendor payment"},
            "from_party": {
                "customer": {"customer_id": "CUST_1", "profile": "business_owner",
                             "segment": "sme", "kyc_risk": "low", "branch": "Mumbai-Fort"},
                "account": {"account_category": "current", "account_status": "active", "current_balance": 9000000},
                "device": {"device_id": "DEV_1", "device_reputation": "good", "proxy_or_vpn": False},
                "geo": {"city": "Mumbai", "state": "MH", "country": "IN"},
                "network": {"pan": "PAN_ABC", "mobile_number": "PHONE_99"},
            },
            "to_party": {"customer": {"profile": "retail_merchant"},
                         "account": {"account_category": "merchant"}},
            "merchant": {"merchant_id": "M_9", "mcc": "5732", "risk_rating": "low"},
            "recovery": {"settlement_status": "pending", "reversible": True, "recovery_priority": "high"},
            "context": {"scenario_id": "vendor-payment", "synthetic": True},
        }
    ],
}


# ── backward compatibility ────────────────────────────────────────────────────
def test_legacy_list_still_works():
    b = normalize_payload(LEGACY)
    assert len(b.transactions) == 2
    assert b.transactions[0].from_account == "ACC_1001"
    assert b.transactions[0].payment_rail == "UPI"
    assert b.transactions[1].payment_rail == "IMPS"
    assert b.batch_meta["schema_version"] == "1.0-legacy"
    assert b.customer_profiles == {}   # nothing declared → inference runs downstream


def test_legacy_with_optional_flat_fields():
    payload = [{"from_account": "A", "to_account": "B", "amount": 100, "payment_rail": "UPI",
                "from_customer": "CUST_X", "device_id": "DEV_X", "from_pan": "PAN_X"}]
    b = normalize_payload(payload)
    t = b.transactions[0]
    assert t.from_customer == "CUST_X" and t.device_id == "DEV_X" and t.from_pan == "PAN_X"


# ── enterprise envelope ───────────────────────────────────────────────────────
def test_envelope_normalizes_to_internal_model():
    b = normalize_payload(ENTERPRISE)
    assert b.batch_meta["dataset_id"] == "UB-DEMO-001"
    assert b.batch_meta["investigation_id"] == "INV-2026-114"
    t = b.transactions[0]
    # nested → flat internal model
    assert t.from_account == "ACC_1001" and t.payment_rail == "RTGS"
    assert t.from_customer == "CUST_1"           # from_party.customer.customer_id
    assert t.device_id == "DEV_1"                # from_party.device.device_id
    assert t.from_pan == "PAN_ABC"               # from_party.network.pan
    assert t.from_entity_type == "current_account"  # account_category mapped


def test_envelope_extracts_customer_profiles_for_profile_intelligence():
    b = normalize_payload(ENTERPRISE)
    assert b.customer_profiles["ACC_1001"] == "business_owner"
    assert b.customer_profiles["MERCH_9"] == "retail_merchant"


def test_envelope_collects_account_intelligence():
    b = normalize_payload(ENTERPRISE)
    ai = b.account_intel["ACC_1001"]
    assert ai["profile"] == "business_owner" and ai["kyc_risk"] == "low"
    assert ai["account_category"] == "current" and ai["geo"] == "Mumbai, MH, IN"
    assert "rtgs" in ai["products"]
    m9 = b.account_intel["MERCH_9"]
    assert m9["merchant"]["merchant_id"] == "M_9"
    assert m9["recovery"]["settlement_status"] == "pending"


# ── the two formats produce the SAME core internal model ──────────────────────
def test_both_formats_yield_equivalent_core():
    legacy = normalize_payload([{"from_account": "A", "to_account": "B", "amount": 1000,
                                 "payment_rail": "RTGS", "timestamp": "2026-01-01T00:00:00"}])
    env = normalize_payload({"schema_version": "2.0", "transactions": [
        {"from_account": "A", "to_account": "B", "amount": 1000,
         "payment": {"rail": "RTGS"}, "timestamp": "2026-01-01T00:00:00"}]})
    lt, et = legacy.transactions[0], env.transactions[0]
    assert (lt.from_account, lt.to_account, lt.amount, lt.payment_rail) == \
           (et.from_account, et.to_account, et.amount, et.payment_rail)


# ── validation (Phase 13) ─────────────────────────────────────────────────────
def test_rejects_negative_amount():
    with pytest.raises(Exception):
        normalize_payload([{"from_account": "A", "to_account": "B", "amount": -5, "payment_rail": "UPI"}])


def test_rejects_duplicate_transaction_ids():
    with pytest.raises(ValueError):
        normalize_payload([
            {"transaction_id": "T1", "from_account": "A", "to_account": "B", "amount": 1},
            {"transaction_id": "T1", "from_account": "B", "to_account": "C", "amount": 1},
        ])


def test_unknown_rail_is_warned_not_rejected():
    b = normalize_payload([{"from_account": "A", "to_account": "B", "amount": 1, "payment_rail": "DOGECOIN"}])
    assert b.transactions[0].payment_rail == "DOGECOIN"
    assert any("Unknown payment rail" in w for w in b.warnings)


def test_invalid_timestamp_is_warned_not_fatal():
    b = normalize_payload([{"from_account": "A", "to_account": "B", "amount": 1, "timestamp": "not-a-date"}])
    assert b.transactions[0].timestamp is None
    assert any("Invalid timestamp" in w for w in b.warnings)


def test_rejects_non_list_non_envelope():
    with pytest.raises(ValueError):
        normalize_payload("just a string")


def test_product_implies_rail_when_rail_absent():
    b = normalize_payload({"transactions": [
        {"from_account": "A", "to_account": "B", "amount": 1, "product": "neft"}]})
    assert b.transactions[0].payment_rail == "NEFT"
