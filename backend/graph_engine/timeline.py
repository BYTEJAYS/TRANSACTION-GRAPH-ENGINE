"""
Timeline intelligence — the temporal rollup of a graph's transactions.

The live payload carries per-edge timestamps but never the temporal *shape* of
the activity an investigator reasons about: when did the money move, how fast,
was it concentrated at night / on weekends, and were there bursts that look
automated rather than organic.

Pure and additive, like the layout / analytics engines: it takes the plain edge
dicts `get_graph_state()` already returns (each with an ISO `timestamp`, an
`amount` and a `risk_score`) and rolls them up. No detection logic leaks to the
frontend — it only renders these summaries. The AML behaviour rules this maps to
(night / weekend / burst / velocity) live in `rule_engine.RULES`.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

# Rules these temporal observations map to (see rule_engine.RULES).
_NIGHT_RULE = "AML016"      # Off-Hours / Night Activity
_WEEKEND_RULE = "AML017"    # Weekend Activity
_BURST_RULE = "AML018"      # Temporal Spike / Burst
_VELOCITY_RULE = "AML010"   # High-Velocity Transfers

_NIGHT_HOURS = set(range(0, 6))  # 00:00–05:59 local-naive


def _parse(ts: Any) -> datetime | None:
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def summarize_timeline(edges: list[dict], bucket_minutes: int = 60) -> dict[str, Any]:
    """
    Temporal rollup of a graph's transactions.

    Returns the activity span, an hour-of-day histogram, night / weekend
    concentration (share of value + count), the peak transfer velocity, detected
    bursts (buckets whose count is a statistical spike), and the AML behaviour
    rules these observations trigger. Deterministic; safe on empty input.
    """
    stamped = []
    for e in edges:
        dt = _parse(e.get("timestamp"))
        if dt is None:
            continue
        stamped.append((dt, float(e.get("amount", 0) or 0), float(e.get("risk_score", 0) or 0)))

    total_txns = len(edges)
    if not stamped:
        return {"available": False, "total_transactions": total_txns, "timed_transactions": 0}

    stamped.sort(key=lambda x: x[0])
    times = [s[0] for s in stamped]
    total_amount = sum(s[1] for s in stamped)
    first, last = times[0], times[-1]
    span_seconds = (last - first).total_seconds()
    span_hours = span_seconds / 3600.0

    # ── hour-of-day + day-of-week distribution ──
    hour_count: Counter = Counter()
    hour_amount: dict[int, float] = {h: 0.0 for h in range(24)}
    dow_count: Counter = Counter()
    night_count = night_amount = weekend_count = weekend_amount = 0.0
    for dt, amt, _ in stamped:
        hour_count[dt.hour] += 1
        hour_amount[dt.hour] += amt
        dow_count[dt.weekday()] += 1
        if dt.hour in _NIGHT_HOURS:
            night_count += 1
            night_amount += amt
        if dt.weekday() >= 5:  # Sat/Sun
            weekend_count += 1
            weekend_amount += amt

    n = len(stamped)
    hour_histogram = [
        {"hour": h, "count": hour_count.get(h, 0), "amount": round(hour_amount[h], 2)}
        for h in range(24)
    ]

    # ── velocity: transactions per hour, peak across fixed buckets ──
    bucket_s = max(1, bucket_minutes) * 60
    bucket_counts: Counter = Counter()
    for dt, _, _ in stamped:
        bucket_counts[int((dt - first).total_seconds() // bucket_s)] += 1
    peak_bucket, peak_in_bucket = bucket_counts.most_common(1)[0]
    avg_velocity = round(n / span_hours, 3) if span_hours > 0 else float(n)
    peak_velocity = round(peak_in_bucket / (bucket_s / 3600.0), 3)

    # ── burst detection: buckets whose count exceeds mean + 2·stdev ──
    # Include the empty buckets within the span so quiet periods lower the
    # baseline and a genuine spike stands out (otherwise the mean is computed
    # only over active buckets and a burst can hide behind its own weight).
    max_bucket = max(bucket_counts) if bucket_counts else 0
    counts = [bucket_counts.get(b, 0) for b in range(max_bucket + 1)]
    mean = sum(counts) / len(counts)
    var = sum((c - mean) ** 2 for c in counts) / len(counts)
    std = var ** 0.5
    threshold = mean + 2 * std
    bursts = []
    for b, c in sorted(bucket_counts.items()):
        if c > threshold and c >= 3:
            start = first.timestamp() + b * bucket_s
            bursts.append({
                "window_start": datetime.fromtimestamp(start).isoformat(),
                "transactions": c,
                "x_mean": round(c / mean, 2) if mean else None,
            })

    night_share = round(night_count / n, 4)
    weekend_share = round(weekend_count / n, 4)

    triggered_rules: list[str] = []
    if night_share >= 0.30:
        triggered_rules.append(_NIGHT_RULE)
    if weekend_share >= 0.40:
        triggered_rules.append(_WEEKEND_RULE)
    if bursts:
        triggered_rules.append(_BURST_RULE)
    if peak_velocity >= 20:
        triggered_rules.append(_VELOCITY_RULE)

    busiest_hour = hour_count.most_common(1)[0][0]
    _dow = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    return {
        "available": True,
        "total_transactions": total_txns,
        "timed_transactions": n,
        "total_amount": round(total_amount, 2),
        "span": {
            "first": first.isoformat(),
            "last": last.isoformat(),
            "duration_hours": round(span_hours, 3),
            "duration_days": round(span_hours / 24, 3),
        },
        "velocity": {
            "avg_per_hour": avg_velocity,
            "peak_per_hour": peak_velocity,
            "peak_window_transactions": peak_in_bucket,
            "bucket_minutes": bucket_minutes,
        },
        "concentration": {
            "busiest_hour": busiest_hour,
            "night_share": night_share,
            "night_amount": round(night_amount, 2),
            "weekend_share": weekend_share,
            "weekend_amount": round(weekend_amount, 2),
        },
        "hour_histogram": hour_histogram,
        "day_of_week": {_dow[d]: dow_count.get(d, 0) for d in range(7)},
        "bursts": bursts,
        "burst_count": len(bursts),
        "triggered_rules": triggered_rules,
    }
