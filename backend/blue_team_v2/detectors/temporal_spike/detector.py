"""
Temporal-spike detector.

A sudden burst in which a large fraction of the cluster's total value moves
inside a short window — the cluster "wakes up" and pushes funds rapidly, then
goes quiet. Captures coordinated, time-boxed laundering runs that per-node
burstiness alone can miss. (A simple, baseline-free seasonal/burst signal; the
full STL/EWMA seasonal model is a Phase 5 upgrade.)
"""
from __future__ import annotations

from ...types import Evidence

NAME = "temporal_spike"
WINDOW_SECONDS = 3600          # 1-hour spike window
MIN_SPIKE_FRACTION = 0.6       # >=60% of cluster value in one window
MIN_TOTAL_VALUE = 2_00_000


def detect(tg, metrics, meta) -> list[Evidence]:
    # collect (timestamp, amount) for every transfer
    events: list[tuple[float, float]] = []
    for _, _, d in tg.G.edges(data=True):
        amt_per = d["amount"] / max(1, len(d["timestamps"]) or 1)
        for t in d["timestamps"]:
            events.append((t.timestamp(), amt_per))
    if len(events) < 4:
        return []
    total = sum(a for _, a in events)
    if total < MIN_TOTAL_VALUE:
        return []
    events.sort()
    # sliding window: max value within any WINDOW_SECONDS span
    best_val, best_span, j = 0.0, (None, None), 0
    cur = 0.0
    times = [e[0] for e in events]
    for i in range(len(events)):
        cur += events[i][1]
        while times[i] - times[j] > WINDOW_SECONDS:
            cur -= events[j][1]
            j += 1
        if cur > best_val:
            best_val = cur
            best_span = (times[j], times[i])
    frac = best_val / total
    if frac < MIN_SPIKE_FRACTION:
        return []
    from datetime import datetime, timezone
    a = datetime.fromtimestamp(best_span[0], tz=timezone.utc).isoformat()
    b = datetime.fromtimestamp(best_span[1], tz=timezone.utc).isoformat()
    sev = min(0.9, 0.5 + 0.5 * frac)
    return [Evidence(
        pattern=NAME,
        title=f"Temporal spike ({frac:.0%} of value in ≤1h)",
        description=(
            f"{frac:.0%} of the cluster's ₹{total:,.0f} total flow moved within a single "
            f"≤1-hour window ({a} → {b}). A coordinated, time-boxed burst of value is "
            f"characteristic of a laundering run executed quickly to outpace monitoring."
        ),
        nodes=tg.nodes[:25],
        severity=sev,
        confidence=0.7,
        data={"spike_fraction": round(frac, 3), "spike_value": round(best_val, 2),
              "total_value": round(total, 2), "window_start": a, "window_end": b},
    )]
