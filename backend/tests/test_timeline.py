"""Tests for the timeline-intelligence engine."""
from datetime import datetime, timedelta

from graph_engine.timeline import summarize_timeline


def _edges(specs):
    """specs: list of (iso_timestamp, amount[, risk])."""
    out = []
    for i, s in enumerate(specs):
        ts, amt = s[0], s[1]
        risk = s[2] if len(s) > 2 else 0.0
        out.append({"source": f"A{i}", "target": f"B{i}", "amount": amt,
                    "risk_score": risk, "timestamp": ts})
    return out


def test_empty_and_untimed_are_safe():
    assert summarize_timeline([])["available"] is False
    untimed = [{"source": "A", "target": "B", "amount": 100, "timestamp": ""}]
    r = summarize_timeline(untimed)
    assert r["available"] is False
    assert r["total_transactions"] == 1
    assert r["timed_transactions"] == 0


def test_span_and_totals():
    base = datetime(2026, 6, 1, 10, 0, 0)
    specs = [((base + timedelta(hours=h)).isoformat(), 1000.0) for h in range(5)]
    r = summarize_timeline(_edges(specs))
    assert r["available"] is True
    assert r["timed_transactions"] == 5
    assert r["total_amount"] == 5000.0
    assert r["span"]["duration_hours"] == 4.0
    assert r["span"]["first"].startswith("2026-06-01T10:00")


def test_night_concentration_triggers_rule():
    # all activity at 02:00–03:00 (night hours)
    base = datetime(2026, 6, 1, 2, 0, 0)
    specs = [((base + timedelta(minutes=10 * i)).isoformat(), 500.0) for i in range(6)]
    r = summarize_timeline(_edges(specs))
    assert r["concentration"]["night_share"] == 1.0
    assert "AML016" in r["triggered_rules"]


def test_weekend_concentration_triggers_rule():
    # 2026-06-06 is a Saturday
    base = datetime(2026, 6, 6, 13, 0, 0)
    specs = [((base + timedelta(minutes=15 * i)).isoformat(), 200.0) for i in range(5)]
    r = summarize_timeline(_edges(specs))
    assert r["concentration"]["weekend_share"] == 1.0
    assert "AML017" in r["triggered_rules"]


def test_burst_detection():
    base = datetime(2026, 6, 1, 9, 0, 0)
    specs = []
    # ~1 txn/hour baseline for 10 hours, then a tight burst of 25 in one hour
    for h in range(10):
        specs.append(((base + timedelta(hours=h)).isoformat(), 100.0))
    burst_hour = base + timedelta(hours=11)
    for i in range(25):
        specs.append(((burst_hour + timedelta(seconds=i)).isoformat(), 100.0))
    r = summarize_timeline(_edges(specs), bucket_minutes=60)
    assert r["burst_count"] >= 1
    assert "AML018" in r["triggered_rules"]
