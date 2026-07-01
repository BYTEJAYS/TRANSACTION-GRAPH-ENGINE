"""
Cash-event ontology regression suite.

A CASH_IN / CASH_OUT transaction is NOT an account-to-account transfer — it is a
boundary where money entered or left the banking system. The cash endpoint must be
a first-class CASH EVENT node (is_account=False, terminal for cash-out) classified
by the EDGE RAIL, not by the node name. This is the bug where a cash-out called
DIAMOND_CASHOUT (name not starting CASH) rendered as a normal bank account.

Covers the 8 spec scenarios across graph builder, recovery and case management.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from graph_engine.graph_manager import TransactionGraphManager
from models.transaction import Transaction, PaymentRail
from recovery.engine import _is_cash_out, fund_state


def _build(edges):
    """edges = [(from, to, amount, rail)] → (manager, graph_state)."""
    async def run():
        mgr = TransactionGraphManager()
        for i, (s, t, amt, rail) in enumerate(edges):
            await mgr.add_transaction(Transaction(
                from_account=s, to_account=t, amount=amt,
                payment_rail=PaymentRail(rail), device_id="ATM",
                ip_address="0.0.0.0", geo_location="x",
                timestamp=datetime(2026, 7, 21, 13, i % 60),
            ))
        return mgr, await mgr.get_graph_state()
    return asyncio.run(run())


def _node(state, nid):
    return next(n for n in state["nodes"] if n["id"] == nid)


def _out_degree(state, nid):
    return sum(1 for e in state["edges"] if e["source"] == nid)


# ── Test 1 — account transfer: both are accounts ──────────────────────────────
def test_account_transfer_both_accounts():
    _, state = _build([("ACC_A", "ACC_B", 10000, "UPI")])
    for n in ("ACC_A", "ACC_B"):
        assert _node(state, n)["account_type"] != "cash"
        assert _node(state, n)["is_account"] is True
        assert _node(state, n)["is_cash_event"] is False


# ── Test 2 — cash IN from a non-CASH-named source ─────────────────────────────
def test_cash_in_event_named_arbitrarily():
    _, state = _build([("BRANCH_DEPOSIT_88", "ACC_1001", 500000, "CASH_IN")])
    src = _node(state, "BRANCH_DEPOSIT_88")
    assert src["account_type"] == "cash"
    assert src["cash_kind"] == "CASH_IN"
    assert src["is_account"] is False
    assert _node(state, "ACC_1001")["is_account"] is True  # recipient is a real account


# ── Test 3 — cash OUT to a non-CASH-named target (the reported bug) ───────────
def test_cash_out_event_named_diamond_cashout():
    _, state = _build([("DIAMOND2_MERGE", "DIAMOND_CASHOUT", 4500000, "CASH_OUT")])
    co = _node(state, "DIAMOND_CASHOUT")
    assert co["account_type"] == "cash", "rail-driven: cash-out target is a cash event, not an account"
    assert co["cash_kind"] == "CASH_OUT"
    assert co["is_account"] is False
    assert co["terminal"] is True
    assert _out_degree(state, "DIAMOND_CASHOUT") == 0, "cash-out is terminal (out_degree 0)"
    assert _node(state, "DIAMOND2_MERGE")["is_account"] is True


# ── Test 4 — double diamond + cash out: terminal & external ───────────────────
def test_double_diamond_with_cashout():
    _, state = _build([
        ("DIAMOND_SOURCE", "DIAMOND_LEFT", 4500000, "UPI"),
        ("DIAMOND_SOURCE", "DIAMOND_RIGHT", 4500000, "UPI"),
        ("DIAMOND_LEFT", "DIAMOND_MERGE", 2250000, "UPI"),
        ("DIAMOND_RIGHT", "DIAMOND_MERGE", 2250000, "UPI"),
        ("DIAMOND_MERGE", "DIAMOND2_MERGE", 4500000, "UPI"),
        ("DIAMOND2_MERGE", "DIAMOND_CASHOUT", 4500000, "CASH_OUT"),
    ])
    co = _node(state, "DIAMOND_CASHOUT")
    assert co["account_type"] == "cash" and co["terminal"] is True
    assert _out_degree(state, "DIAMOND_CASHOUT") == 0
    # every diamond node stays a real account
    for n in ("DIAMOND_SOURCE", "DIAMOND_LEFT", "DIAMOND_RIGHT", "DIAMOND_MERGE", "DIAMOND2_MERGE"):
        assert _node(state, n)["is_account"] is True


# ── Test 5 — multiple cash outs: each its own terminal event ──────────────────
def test_multiple_cashouts_each_terminal():
    _, state = _build([
        ("HUB", "M1", 100000, "UPI"), ("HUB", "M2", 100000, "UPI"),
        ("M1", "EXIT_ALPHA", 95000, "CASH_OUT"),
        ("M2", "EXIT_BETA", 95000, "CASH_OUT"),
    ])
    for ex in ("EXIT_ALPHA", "EXIT_BETA"):
        assert _node(state, ex)["account_type"] == "cash"
        assert _node(state, ex)["terminal"] is True
        assert _out_degree(state, ex) == 0


# ── Test 6 — cash identity is sticky; fraud never flips it to a normal account ─
def test_cash_identity_sticky_under_fraud():
    _, state = _build([
        ("MUL_9", "GOLDEN_EXIT", 990000, "CASH_OUT"),  # mule → cash-out
    ])
    co = _node(state, "GOLDEN_EXIT")
    assert co["account_type"] == "cash"   # NOT recoloured to a normal/mule account
    assert co["cash_kind"] == "CASH_OUT"
    # even if flagged, identity stays cash (frontend shows fraud as a halo, not red fill)


# ── Test 7 — recovery: cash-out reduces recoverable funds ─────────────────────
def test_recovery_treats_cashout_as_exited():
    assert _is_cash_out({"rail": "CASH_OUT"}) is True, "CASH_OUT rail recognised as cash-out"
    case = {
        "transactions": [
            {"from_account": "VICTIM", "to_account": "MULE", "amount": 1000000, "rail": "UPI"},
            {"from_account": "MULE", "to_account": "CASH_EXIT_X", "amount": 1000000, "rail": "CASH_OUT"},
        ],
    }
    fs = fund_state(case)
    assert fs["cashed_out"] == 1000000, "withdrawn amount counted as cashed-out"
    # the cash-out destination is NOT a freezable balance
    assert fs["in_network"] == 0, "no recoverable balance sits at a cash exit"
    assert fs["exited"] == 1000000


# ── Test 8 — case management: cash event not counted as a customer account ─────
def test_case_excludes_cash_event_from_account_count():
    from case_management.store import CaseStore
    store = CaseStore.__new__(CaseStore)  # avoid seeding; init just the bits we need
    import threading
    store._cases = {}
    store._lock = threading.RLock()
    store._seq = 0
    component = {
        "node_ids": ["VICTIM", "MULE", "DIAMOND_CASHOUT"],
        "nodes": [
            {"id": "VICTIM", "risk_score": 0.9, "is_flagged": True},
            {"id": "MULE", "risk_score": 0.8, "is_flagged": True},
            {"id": "DIAMOND_CASHOUT", "risk_score": 0.0, "account_type": "cash", "is_cash_event": True},
        ],
        "edges": [
            {"id": "e1", "source": "VICTIM", "target": "MULE", "amount": 900000, "payment_rail": "UPI"},
            {"id": "e2", "source": "MULE", "target": "DIAMOND_CASHOUT", "amount": 900000, "payment_rail": "CASH_OUT"},
        ],
    }
    verdict = {"flagged_nodes": ["VICTIM", "MULE"], "verdict": "FRAUD", "graph_id": "G1"}
    assessment = {"score": 88, "level": "Critical", "explanation": "test"}
    case = store.register_from_detection(verdict=verdict, component=component, assessment=assessment)
    assert case is not None
    assert case["account_count"] == 2, "cash event excluded from account count"
    assert case["primary_account"] != "DIAMOND_CASHOUT", "cash event is never the primary suspect"
    kinds = {ev["kind"] for ev in case["cash_events"]}
    assert kinds == {"CASH_OUT"}, "the cash-out is recorded as a separate cash event"
    assert case["cash_events"][0]["terminal"] is True
