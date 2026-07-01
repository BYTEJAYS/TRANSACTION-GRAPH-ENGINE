from __future__ import annotations
"""
Seed Enrichment — when Blue Team sends a confirmed fraud that Red Team MISSED,
convert it into a high-priority seed genome so the next evolution run starts
closer to the missed pattern.

priority=HIGH seeds get 5x representation in the initial population.
"""
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome

logger = logging.getLogger(__name__)

_HIGH_PRIORITY_MULTIPLIER = 5
_NORMAL_PRIORITY_MULTIPLIER = 1


class SeedBank:

    def __init__(self) -> None:
        # [(genome, priority)] where priority in {"HIGH", "NORMAL"}
        self._seeds: list[tuple["FraudGenome", str]] = []

    def add_seed(self, genome: "FraudGenome", priority: str = "NORMAL") -> None:
        self._seeds.append((genome, priority))
        logger.info(
            "Seed added",
            genome_id=genome.genome_id[:8],
            priority=priority,
            total_seeds=len(self._seeds),
        )

    def add_missed_fraud(self, genome: "FraudGenome") -> None:
        """Missed by Red Team — highest priority to avoid missing similar patterns."""
        genome.flags.append("missed_by_red_team")
        self.add_seed(genome, priority="HIGH")

    def get_initial_population(self, size: int) -> list["FraudGenome"]:
        """
        Build starting population by oversampling HIGH-priority seeds.
        Returns list of `size` genomes (with duplicates for high-priority).
        """
        from copy import deepcopy
        import uuid

        weighted: list["FraudGenome"] = []
        for genome, priority in self._seeds:
            mult = _HIGH_PRIORITY_MULTIPLIER if priority == "HIGH" else _NORMAL_PRIORITY_MULTIPLIER
            for _ in range(mult):
                clone = deepcopy(genome)
                clone.genome_id = str(uuid.uuid4())
                clone.flags = [f for f in clone.flags if f != "missed_by_red_team"]
                weighted.append(clone)

        if not weighted:
            return []

        # Cycle through weighted seeds to reach requested size
        result = []
        for i in range(size):
            result.append(deepcopy(weighted[i % len(weighted)]))
            result[-1].genome_id = str(uuid.uuid4())
        return result

    def __len__(self) -> int:
        return len(self._seeds)

    def stats(self) -> dict[str, int]:
        high = sum(1 for _, p in self._seeds if p == "HIGH")
        return {"total": len(self._seeds), "high_priority": high, "normal": len(self._seeds) - high}


seed_bank = SeedBank()
