"""
First-class Cash In / Cash Out — unit + regression tests.

Verifies that CASH_IN / CASH_OUT transactions are accepted, create REAL graph
nodes and edges, stay fully connected, are classified as cash, participate in
graph algorithms, and are included in analytics — without breaking the existing
UPI / IMPS / NEFT / RTGS rails or the legacy off-graph CASH rail.

Runs WITHOUT pytest:   python backend/tests/test_cash_transactions.py
Runs WITH pytest too:  pytest backend/tests/test_cash_transactions.py
"""
import asyncio
import os
import sys

# Make `backend/` importable whether run from repo root or the tests dir.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import networkx as nx  # noqa: E402
from datetime import datetime  # noqa: E402
from models.transaction import Transaction, PaymentRail, AccountType  # noqa: E402
from graph_engine.graph_manager import TransactionGraphManager  # noqa: E402


def _txn(frm: str, to: str, amount: float, rail: str) -> Transaction:
    """Build a Transaction exactly as the ingestion route does."""
    return Transaction(
        from_account=frm,
        to_account=to,
        amount=amount,
        payment_rail=PaymentRail(rail),
        timestamp=datetime.utcnow(),
        device_id="TEST",
        ip_address="0.0.0.0",
        geo_location="Test",
    )


async def _build(chain):
    mgr = TransactionGraphManager()
    for frm, to, amt, rail in chain:
        await mgr.add_transaction(_txn(frm, to, amt, rail))
    state = await mgr.get_graph_state()
    return mgr, state


def _node(state, nid):
    return next((n for n in state["nodes"] if n["id"] == nid), None)


# ── 1. Single cash deposit ──────────────────────────────────────────────────
def test_single_cash_deposit():
    mgr, state = asyncio.run(_build([("CASH_SOURCE", "ACC_1001", 500000, "CASH_IN")]))
    assert "CASH_SOURCE" in mgr._graph and "ACC_1001" in mgr._graph, "both nodes created"
    assert mgr._graph.has_edge("CASH_SOURCE", "ACC_1001"), "deposit edge created"
    assert _node(state, "CASH_SOURCE")["account_type"] == "cash", "source classified as cash"
    assert _node(state, "ACC_1001")["cash_inflows"] == 500000, "deposit counted as cash inflow"


# ── 2. Single cash withdrawal ───────────────────────────────────────────────
def test_single_cash_withdrawal():
    mgr, state = asyncio.run(_build([("ACC_3001", "CASH_EXIT", 475000, "CASH_OUT")]))
    assert "CASH_EXIT" in mgr._graph and "ACC_3001" in mgr._graph, "both nodes created"
    assert mgr._graph.has_edge("ACC_3001", "CASH_EXIT"), "withdrawal edge created"
    assert _node(state, "CASH_EXIT")["account_type"] == "cash", "exit classified as cash"
    assert _node(state, "ACC_3001")["cash_outflows"] == 475000, "withdrawal counted as cash outflow"


# ── 3. Deposit → Transfer → Withdrawal (full connectivity) ──────────────────
def test_deposit_transfer_withdrawal_chain():
    chain = [
        ("CASH_SOURCE", "ACC_1001", 500000, "CASH_IN"),
        ("ACC_1001", "ACC_2001", 490000, "UPI"),
        ("ACC_2001", "ACC_3001", 480000, "IMPS"),
        ("ACC_3001", "CASH_EXIT", 475000, "CASH_OUT"),
    ]
    mgr, state = asyncio.run(_build(chain))
    assert mgr._graph.number_of_nodes() == 5, "all 5 nodes present"
    assert nx.has_path(mgr._graph, "CASH_SOURCE", "CASH_EXIT"), "end-to-end path exists"
    path = nx.shortest_path(mgr._graph, "CASH_SOURCE", "CASH_EXIT")
    assert path == ["CASH_SOURCE", "ACC_1001", "ACC_2001", "ACC_3001", "CASH_EXIT"], "connected chain"
    # single connected component → first-class cash participation
    assert nx.number_weakly_connected_components(mgr._graph) == 1, "one connected component"


# ── 4. Multiple cash deposits (fan-out hub) ─────────────────────────────────
def test_multiple_cash_deposits():
    chain = [
        ("CASH_SOURCE", "ACC_1", 100000, "CASH_IN"),
        ("CASH_SOURCE", "ACC_2", 100000, "CASH_IN"),
        ("CASH_SOURCE", "ACC_3", 100000, "CASH_IN"),
    ]
    mgr, _ = asyncio.run(_build(chain))
    assert mgr._graph.out_degree("CASH_SOURCE") == 3, "CASH_SOURCE is a fan-out hub (shared node)"
    assert "CASH_SOURCE" in mgr._graph and mgr._graph.number_of_nodes() == 4, "no duplicate source node"


# ── 5. Layered cash laundering ──────────────────────────────────────────────
def test_layered_cash_laundering():
    chain = [
        ("CASH_SOURCE", "MUL_1", 300000, "CASH_IN"),
        ("MUL_1", "MUL_2", 290000, "UPI"),
        ("MUL_2", "MUL_3", 280000, "NEFT"),
        ("MUL_3", "CASH_EXIT", 270000, "CASH_OUT"),
    ]
    mgr, state = asyncio.run(_build(chain))
    assert nx.has_path(mgr._graph, "CASH_SOURCE", "CASH_EXIT"), "laundering path traceable"
    total_volume = state["stats"].get("total_volume") if state.get("stats") else None
    # analytics include cash legs
    assert mgr._total_volume == 300000 + 290000 + 280000 + 270000, "cash legs included in volume"
    assert _node(state, "MUL_1")["account_type"] == "mule", "mule still classified (no regression)"


# ── 6. Cash deposit → fraud ring → cash withdrawal ──────────────────────────
def test_cash_into_ring_out():
    chain = [
        ("CASH_SOURCE", "A", 200000, "CASH_IN"),
        ("A", "B", 190000, "UPI"),
        ("B", "C", 180000, "UPI"),
        ("C", "A", 170000, "UPI"),       # ring A→B→C→A
        ("C", "CASH_EXIT", 160000, "CASH_OUT"),
    ]
    mgr, _ = asyncio.run(_build(chain))
    cycles = [c for c in nx.simple_cycles(mgr._graph)]
    assert any(set(c) == {"A", "B", "C"} for c in cycles), "fraud ring detected"
    assert nx.has_path(mgr._graph, "CASH_SOURCE", "CASH_EXIT"), "cash endpoints connected through ring"


# ── 7. REGRESSION: existing rails unaffected ────────────────────────────────
def test_regression_non_cash_rails():
    chain = [
        ("ACC_A", "ACC_B", 50000, "UPI"),
        ("ACC_B", "ACC_C", 40000, "IMPS"),
        ("ACC_C", "ACC_D", 30000, "NEFT"),
        ("ACC_D", "ACC_E", 20000, "RTGS"),
    ]
    mgr, state = asyncio.run(_build(chain))
    assert mgr._graph.number_of_nodes() == 5, "normal nodes created"
    for nid in ("ACC_A", "ACC_B", "ACC_C", "ACC_D", "ACC_E"):
        assert _node(state, nid)["account_type"] == "normal", f"{nid} stays normal (no cash misclassification)"
    edge = mgr._edges[next(iter(mgr._edges))]
    assert edge["payment_rail"] in ("UPI", "IMPS", "NEFT", "RTGS"), "rails preserved"


def test_regression_legacy_cash_rail_enum():
    # The legacy off-graph CASH rail must still be a valid enum value.
    assert PaymentRail("CASH") == PaymentRail.CASH
    assert AccountType.CASH.value == "cash"


# ── Minimal runner (no pytest dependency) ───────────────────────────────────
if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)
