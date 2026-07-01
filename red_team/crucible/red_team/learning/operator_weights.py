from __future__ import annotations
"""
OperatorPerformanceTracker — records which operators appear in winning genomes
and computes normalized performance weights.

Winning = fitness > WINNING_THRESHOLD AND approved by human investigator.
Weights are persisted to DB (OperatorPerformance table) and also cached in
memory for fast lookup during PBT operator sampling.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

WINNING_THRESHOLD = 0.05  # fitness must exceed this to count as a win
_DECAY_FACTOR = 0.95       # old counts decay each update cycle (recency bias)


class OperatorPerformanceTracker:

    def __init__(self) -> None:
        self._wins: dict[str, int] = {}
        self._attempts: dict[str, int] = {}

    def record_attempt(self, operator_name: str) -> None:
        self._attempts[operator_name] = self._attempts.get(operator_name, 0) + 1

    def record_win(self, operators: list[str], fitness: float) -> None:
        if fitness < WINNING_THRESHOLD:
            return
        for op in operators:
            self._wins[op] = self._wins.get(op, 0) + 1

    def apply_decay(self) -> None:
        """Call once per nightly cycle to reduce influence of old data."""
        for op in list(self._wins.keys()):
            self._wins[op] = int(self._wins[op] * _DECAY_FACTOR)
        for op in list(self._attempts.keys()):
            self._attempts[op] = int(self._attempts[op] * _DECAY_FACTOR)

    def get_weights(self) -> dict[str, float]:
        """
        Returns {operator_name: weight} where weight ∈ [0.1, 3.0].
        Default weight for unseen operators = 1.0.
        """
        weights: dict[str, float] = {}
        all_ops = set(self._wins) | set(self._attempts)

        for op in all_ops:
            attempts = self._attempts.get(op, 0)
            wins = self._wins.get(op, 0)
            if attempts == 0:
                weights[op] = 1.0
                continue
            win_rate = wins / attempts
            # Scale: 0% → 0.1, 50% → 1.5, 100% → 3.0
            weight = 0.1 + win_rate * 2.9
            weights[op] = round(min(3.0, max(0.1, weight)), 4)

        return weights

    def get_stats(self) -> list[dict[str, Any]]:
        all_ops = set(self._wins) | set(self._attempts)
        result = []
        for op in sorted(all_ops):
            attempts = self._attempts.get(op, 0)
            wins = self._wins.get(op, 0)
            result.append({
                "operator": op,
                "attempts": attempts,
                "wins": wins,
                "win_rate": round(wins / attempts, 4) if attempts else 0.0,
            })
        return result


operator_tracker = OperatorPerformanceTracker()
