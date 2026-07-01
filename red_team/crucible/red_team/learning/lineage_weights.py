from __future__ import annotations
"""
LineageWeightManager — bridges ProphecyLedger scores to PBT engine selection weights.

Called at the start of each nightly run to load current lineage weights,
and by the engine every 500 generations for mid-run updates.
"""
import logging
from typing import Any

from red_team.prophecy.ledger import ProphecyLedger
from red_team.learning.operator_weights import OperatorPerformanceTracker

logger = logging.getLogger(__name__)


class LineageWeightManager:

    def __init__(
        self,
        ledger: ProphecyLedger,
        tracker: OperatorPerformanceTracker,
    ) -> None:
        self._ledger = ledger
        self._tracker = tracker

    def get_combined_weights(self) -> dict[str, float]:
        """
        Merges prophecy-based operator boosts with tracker win-rate weights.
        Final weight = 0.6 × prophecy_boost + 0.4 × tracker_weight
        Both signals normalized to same scale [0.1, 3.0].
        """
        prophecy_boosts = self._ledger.get_operator_boosts()
        tracker_weights = self._tracker.get_weights()

        all_ops = set(prophecy_boosts) | set(tracker_weights)
        combined: dict[str, float] = {}

        for op in all_ops:
            pb = prophecy_boosts.get(op, 1.0)
            tw = tracker_weights.get(op, 1.0)
            combined[op] = round(0.6 * pb + 0.4 * tw, 4)

        return combined

    def report(self) -> list[dict[str, Any]]:
        weights = self.get_combined_weights()
        return [
            {"operator": op, "combined_weight": w}
            for op, w in sorted(weights.items(), key=lambda x: -x[1])
        ]
