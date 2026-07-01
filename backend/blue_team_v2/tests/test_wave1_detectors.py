"""
Phase 4 Wave 1 — golden fixtures + fire/no-fire precision tests.

For each new topology pattern we synthesise a minimal labelled component and
assert (a) the matching detector fires, and (b) a benign component produces no
Wave-1 evidence (the precision guard). Runs the real engine path:
    TransactionGraph -> RiskEngine.compute() -> PatternEngine.run()
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from blue_team_v2.core.graph_engine.builder import TransactionGraph
from blue_team_v2.core.risk_engine.node_intelligence import RiskEngine
from blue_team_v2.core.pattern_engine.orchestrator import PatternEngine

BASE = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)  # a Monday 10:00


def _next_saturday(d: datetime) -> datetime:
    return d + timedelta(days=(5 - d.weekday()) % 7)


def edge(src, tgt, amt, mins=0, rail="UPI", hour=None, day=None):
    ts = BASE + timedelta(minutes=mins)
    if hour is not None:
        ts = ts.replace(hour=hour)
    if day is not None:
        ts = ts.replace(day=day)
    return {"source": src, "target": tgt, "amount": amt, "payment_rail": rail,
            "timestamp": ts.isoformat()}


def comp(edges, gid="G"):
    ids = {x for e in edges for x in (e["source"], e["target"])}
    return {"graph_id": gid, "nodes": [{"id": i} for i in ids], "edges": edges}


def patterns_for(component) -> set[str]:
    tg = TransactionGraph(component)
    metrics, _cluster, meta = RiskEngine(tg).compute()
    evidence = PatternEngine().run(tg, metrics, meta)
    return {e.pattern for e in evidence}


# ── fixtures: (name, component) ──────────────────────────────────────────────
def fx_diamond():
    return comp([edge("A", "B", 500_000, 0), edge("A", "C", 500_000, 1),
                 edge("B", "D", 480_000, 5), edge("C", "D", 480_000, 6)])


def fx_round_tripping():
    return comp([edge("A", "B", 300_000, 0), edge("B", "C", 295_000, 10),
                 edge("C", "A", 295_000, 20)])


def fx_hub():
    e = []
    for i in range(5):
        e.append(edge(f"S{i}", "H", 120_000, i))
    for i in range(5):
        e.append(edge("H", f"R{i}", 110_000, 10 + i))
    return comp(e)


def fx_scatter_gather():
    e = [edge(f"S{i}", "R", 100_000, i) for i in range(4)]
    e += [edge("R", f"D{i}", 95_000, 10 + i) for i in range(4)]
    return comp(e)


def fx_structuring():
    return comp([edge("S", f"R{i}", 8_60_000, i) for i in range(4)])  # just under ₹10L


def fx_cash_laundering():
    e = [edge("CASH_SRC", "N", 6_00_000, 0, rail="CASH_IN")]
    e += [edge("N", f"D{i}", 1_80_000, 5 + i) for i in range(3)]
    return comp(e)


def fx_night():
    return comp([edge("X", f"Y{i}", 80_000, i, hour=2) for i in range(5)])


def fx_weekend():
    sat = _next_saturday(BASE).day
    return comp([edge("X", f"Y{i}", 80_000, i, day=sat) for i in range(5)])


def fx_temporal_spike():
    # 6 large transfers all within ~15 min, then nothing else
    return comp([edge(f"A{i}", f"B{i}", 90_000, i * 2) for i in range(6)])


def fx_uniform():
    return comp([edge(f"A{i}", f"B{i}", 50_000, i) for i in range(5)])


def fx_nested():
    # primary 5-hop chain A→B→C→D→E→F; interior relay C spawns a 3-hop branch C→G→H→I.
    # Both sub-branches from C are 3 hops, so nested fires regardless of which the
    # longest-path picks as primary.
    chain = [edge("A", "B", 400_000, 0), edge("B", "C", 380_000, 5),
             edge("C", "D", 360_000, 10), edge("D", "E", 340_000, 15),
             edge("E", "F", 320_000, 20)]
    branch = [edge("C", "G", 200_000, 8), edge("G", "H", 190_000, 12),
              edge("H", "I", 180_000, 16)]
    return comp(chain + branch)


CASES = [
    ("diamond", fx_diamond),
    ("round_tripping", fx_round_tripping),
    ("hub_network", fx_hub),
    ("scatter_gather", fx_scatter_gather),
    ("structuring", fx_structuring),
    ("cash_laundering", fx_cash_laundering),
    ("night_activity", fx_night),
    ("weekend_activity", fx_weekend),
    ("temporal_spike", fx_temporal_spike),
    ("uniform_amount", fx_uniform),
    ("nested_layering", fx_nested),
]


@pytest.mark.parametrize("name,builder", CASES, ids=[c[0] for c in CASES])
def test_detector_fires(name, builder):
    found = patterns_for(builder())
    assert name in found, f"{name} did not fire; got {sorted(found)}"


def test_benign_no_wave1_noise():
    """A few small, daytime, distinct transfers should not trip Wave-1 detectors."""
    benign = comp([
        edge("P", "Q", 5_000, 0),
        edge("Q", "Z", 3_000, 60 * 30),
        edge("R", "S", 2_500, 60 * 50),
    ])
    wave1 = {"diamond", "round_tripping", "hub_network", "scatter_gather",
             "structuring", "cash_laundering", "night_activity",
             "weekend_activity", "temporal_spike", "uniform_amount", "nested_layering"}
    found = patterns_for(benign)
    assert not (found & wave1), f"benign component tripped Wave-1 detectors: {found & wave1}"
