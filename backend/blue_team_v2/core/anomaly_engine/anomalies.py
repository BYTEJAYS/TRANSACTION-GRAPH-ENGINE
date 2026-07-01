"""
Anomaly Engine — temporal anomaly signals per node.

Produces three normalized [0,1] signals used by the risk engine:
  * velocity      — value throughput per active minute, log-compressed
  * burst         — burstiness of inter-arrival times (Fano-style)
  * dormancy      — sudden reactivation after a long quiet gap
"""
from __future__ import annotations

import math
from datetime import datetime

from ..graph_engine.builder import TransactionGraph


def _burstiness(times: list[datetime]) -> float:
    """
    Burstiness coefficient in [0,1].

    Based on the coefficient of variation of inter-arrival times:
      B = (sigma - mu) / (sigma + mu)  ∈ [-1, 1]
    Mapped to [0,1]; bursty (clumped) traffic → near 1, regular → 0.5, perfectly
    periodic → 0.  Single/no interval → 0.
    """
    if len(times) < 3:
        return 0.0
    gaps = [(times[i + 1] - times[i]).total_seconds() for i in range(len(times) - 1)]
    gaps = [g for g in gaps if g >= 0]
    if len(gaps) < 2:
        return 0.0
    mu = sum(gaps) / len(gaps)
    if mu <= 0:
        return 1.0
    var = sum((g - mu) ** 2 for g in gaps) / len(gaps)
    sigma = math.sqrt(var)
    b = (sigma - mu) / (sigma + mu) if (sigma + mu) > 0 else 0.0
    return max(0.0, min(1.0, (b + 1.0) / 2.0))


def _velocity(value: float, times: list[datetime]) -> float:
    """Value moved per minute within the node's active window."""
    if value <= 0:
        return 0.0
    if len(times) < 2:
        return value / 60.0  # treat as one minute window
    span = (times[-1] - times[0]).total_seconds()
    span = max(span, 1.0)
    return value / (span / 60.0)


# A quiet period only counts as genuine dormancy if it lasts at least this long
# in absolute terms — prevents minute-spaced bursts from looking "reactivated".
_MIN_DORMANCY_SECONDS = 6 * 3600  # 6 hours


def _dormancy_reactivation(times: list[datetime]) -> float:
    """
    Detect a long quiet period followed by a burst — classic mule reactivation.

    Returns the fraction of total activity-span that the largest single gap
    occupies, weighted by how much activity follows it.  The largest gap must
    exceed an absolute floor (hours), so ordinary rapid activity never registers.
    """
    if len(times) < 3:
        return 0.0
    gaps = [(times[i + 1] - times[i]).total_seconds() for i in range(len(times) - 1)]
    total = (times[-1] - times[0]).total_seconds()
    if total <= 0:
        return 0.0
    max_gap = max(gaps)
    if max_gap < _MIN_DORMANCY_SECONDS:
        return 0.0
    gap_idx = gaps.index(max_gap)
    after = len(times) - (gap_idx + 1)            # activity after the silence
    dormancy_ratio = max_gap / total
    activity_ratio = after / len(times)
    # both must be high: a big gap AND meaningful post-gap activity
    return max(0.0, min(1.0, dormancy_ratio * activity_ratio * 2.0))


class AnomalyEngine:
    def __init__(self, tg: TransactionGraph):
        self.tg = tg

    def node_signals(self, node: str) -> dict[str, float]:
        times = self.tg.timestamps(node)
        value = self.tg.in_volume(node) + self.tg.out_volume(node)
        raw_velocity = _velocity(value, times)
        # log-compress velocity into 0..1 (₹1L/min ≈ 0.5, ₹10L/min ≈ ~0.83)
        norm_velocity = 1.0 - math.exp(-raw_velocity / 100_000.0) if raw_velocity > 0 else 0.0
        return {
            "velocity_raw": raw_velocity,
            "velocity": max(0.0, min(1.0, norm_velocity)),
            "burst": _burstiness(times),
            "dormancy": _dormancy_reactivation(times),
        }

    def graph_velocity(self) -> float:
        """Whole-component value/min — used for graph-level velocity gate."""
        times = self.tg.all_timestamps()
        value = sum(d["amount"] for _, _, d in self.tg.G.edges(data=True))
        return _velocity(value, times)
