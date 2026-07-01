from __future__ import annotations
"""
Human Gate Queue — impact-sorted presentation queue for investigator review.

Priority score = ₹_at_risk × ease_of_replication × scalability_multiplier
  ease_of_replication: 1.0=simple, 2.0=moderate, 3.0=complex
  scalability: how many accounts/transactions would real deployment require

Items stay in queue until reviewed. Investigators must confirm with 2FA
before approving a genome (passed to Blue Team as a hardening target).
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome

logger = logging.getLogger(__name__)

_EASE_MAP = {
    "simple": 1.0,   # fan_out, threshold proximity
    "moderate": 2.0, # abandoned nodes, merchant nodes
    "complex": 3.0,  # layered mixing, bipartite split
}

_SCALABILITY_MAP = {
    "low": 1.0,
    "medium": 2.0,
    "high": 3.5,
}


@dataclass
class QueueItem:
    genome_id: str
    genome_summary: dict[str, Any]
    priority_score: float
    rupees_at_risk: float
    ease_label: str
    scalability_label: str
    flags: list[str]
    requires_senior: bool
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed: bool = False
    reviewer_id: str | None = None
    review_decision: str | None = None  # "approve" | "discard" | "needs_more_info"
    review_notes: str | None = None


class HumanGateQueue:

    def __init__(self) -> None:
        self._items: dict[str, QueueItem] = {}

    def _estimate_ease(self, genome: "FraudGenome") -> str:
        ops = genome.mutation_history
        if any(op in ops for op in ("layered_mixing", "create_bipartite_split")):
            return "complex"
        if any(op in ops for op in ("insert_abandoned_node", "insert_merchant_node", "time_dilation")):
            return "moderate"
        return "simple"

    def _estimate_scalability(self, genome: "FraudGenome") -> str:
        total_accounts = (
            genome.topology.width
            + genome.topology.collector_count
            + genome.topology.depth
        )
        if total_accounts > 15:
            return "high"
        if total_accounts > 7:
            return "medium"
        return "low"

    def _compute_priority(
        self,
        rupees_at_risk: float,
        ease: str,
        scalability: str,
    ) -> float:
        return round(
            (rupees_at_risk / 100_000)  # normalize to ₹1L units
            * _EASE_MAP.get(ease, 1.0)
            * _SCALABILITY_MAP.get(scalability, 1.0),
            4,
        )

    def enqueue(self, genome: "FraudGenome", fitness: float) -> QueueItem:
        rupees_at_risk = genome.amounts.total
        ease = self._estimate_ease(genome)
        scalability = self._estimate_scalability(genome)
        priority = self._compute_priority(rupees_at_risk, ease, scalability)

        item = QueueItem(
            genome_id=genome.genome_id,
            genome_summary={
                "topology_type": genome.topology.type,
                "depth": genome.topology.depth,
                "width": genome.topology.width,
                "total_amount": rupees_at_risk,
                "timing": genome.timing.time_of_day,
                "festival": genome.timing.festival_timing,
                "channels": genome.channels.mix,
                "lineage": genome.mutation_history,
                "fitness": round(fitness, 6),
            },
            priority_score=priority,
            rupees_at_risk=rupees_at_risk,
            ease_label=ease,
            scalability_label=scalability,
            flags=list(genome.flags),
            requires_senior="REQUIRES_SENIOR_REVIEW" in genome.flags,
        )
        self._items[genome.genome_id] = item
        logger.info("Genome enqueued", genome_id=genome.genome_id[:8], priority=priority)
        return item

    def get_sorted(self, pending_only: bool = True) -> list[QueueItem]:
        items = list(self._items.values())
        if pending_only:
            items = [i for i in items if not i.reviewed]
        # Senior-review items always float to top regardless of score
        items.sort(key=lambda x: (x.requires_senior, x.priority_score), reverse=True)
        return items

    def record_review(
        self,
        genome_id: str,
        reviewer_id: str,
        decision: str,
        notes: str | None = None,
    ) -> QueueItem | None:
        item = self._items.get(genome_id)
        if item is None:
            return None
        item.reviewed = True
        item.reviewer_id = reviewer_id
        item.review_decision = decision
        item.review_notes = notes
        logger.info("Review recorded", genome_id=genome_id[:8], decision=decision)
        return item

    def __len__(self) -> int:
        return sum(1 for i in self._items.values() if not i.reviewed)


human_gate_queue = HumanGateQueue()
