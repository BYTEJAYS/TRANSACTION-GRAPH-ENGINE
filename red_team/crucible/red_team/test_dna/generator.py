from __future__ import annotations
"""
Test DNA Generator — converts a FraudGenome to the Blue Team transaction JSON format.
Wraps genome.to_transaction_list() and adds metadata for the test harness.
"""
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome


def generate_test_dna(
    genome: "FraudGenome",
    bypass_gates: list[str] | None = None,
    bypass_logic: str = "",
) -> dict[str, Any]:
    """
    Converts a FraudGenome into a test DNA dict with:
      - transactions: list of {from_account, to_account, amount, payment_rail, timestamp}
      - metadata: bypass context for the bypass_verifier
    """
    transactions = genome.to_transaction_list()
    return {
        "genome_id": genome.genome_id,
        "lineage_id": genome.lineage_id,
        "generation": genome.generation,
        "mutation_history": genome.mutation_history,
        "flags": genome.flags,
        "bypass_gates": bypass_gates or [],
        "bypass_logic": bypass_logic,
        "transactions": transactions,
        "topology": {
            "type": genome.topology.type,
            "depth": genome.topology.depth,
            "width": genome.topology.width,
            "collector_count": genome.topology.collector_count,
            "mimics_legitimate": genome.topology.mimics_legitimate,
        },
        "timing": {
            "time_of_day": genome.timing.time_of_day,
            "festival_timing": bool(genome.timing.festival_timing),
            "festival_name": genome.timing.festival_name,
            "low_slow": genome.timing.low_slow,
        },
        "amounts_summary": {
            "total": genome.amounts.total,
            "count": len(genome.amounts.values),
            "min": min(genome.amounts.values) if genome.amounts.values else 0,
            "max": max(genome.amounts.values) if genome.amounts.values else 0,
        },
    }
