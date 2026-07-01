from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome

# Per-transaction amount limits by rail
RAIL_LIMITS: dict[str, int] = {
    "p2p_transfer": 100_000,
    "ach_transfer": 10_000_000,
    "wire_transfer": 10_000_000,
    "internal_transfer": 500_000,
    "crypto_exchange": 500_000,
    "bill_payment": 500_000,
    "debit_purchase": 100_000,
    "atm_withdrawal": 200_000,
    "pos_transaction": 200_000,
}

# Rails that have overnight/batch processing blackouts
BATCH_RAILS: frozenset[str] = frozenset({"ach_transfer"})

# KYC tier monthly credit ceilings
KYC_MONTHLY_LIMITS: dict[str, int] = {
    "min": 10_000,
    "basic": 100_000,
    "full": 10_000_000,
}

# Minimum account age (days) before transacting above this amount
ACCOUNT_AGE_AMOUNT_GATES: list[tuple[int, int]] = [
    (90, 10_000),
    (30, 1_000),
]


class RailConstraintViolation(Exception):
    """Raised when a mutation produces a physically impossible transaction."""


def _primary_channel(genome: "FraudGenome") -> str:
    if genome.channels.channel_sequence:
        return genome.channels.channel_sequence[0]
    if genome.channels.mix:
        return max(genome.channels.mix, key=genome.channels.mix.get)
    return "ach_transfer"


def validate_genome(genome: "FraudGenome") -> tuple[bool, list[str]]:
    """
    Returns (is_valid, violations).
    Called after every mutation — invalid genomes are dropped, not queued.
    """
    violations: list[str] = []
    channel = _primary_channel(genome)

    # 1. Channel amount limits
    limit = RAIL_LIMITS.get(channel, 100_000)
    for amount in genome.amounts.values:
        if amount > limit:
            violations.append(f"Amount {amount:,.0f} exceeds {channel} limit {limit:,}")

    # 2. Batch rail blackout: ach_transfer not processed at night
    if channel in BATCH_RAILS and genome.timing.time_of_day == "night":
        violations.append(f"{channel} unavailable during night hours (00:00-02:00)")

    # 3. KYC tier total credit limit
    total = genome.amounts.total
    kyc_limit = KYC_MONTHLY_LIMITS.get(genome.accounts.kyc_tier, 10_000_000)
    if total > kyc_limit:
        violations.append(
            f"KYC tier '{genome.accounts.kyc_tier}' limit {kyc_limit:,} exceeded by total {total:,.0f}"
        )

    # 4. Account age vs transaction size
    min_age = min(genome.accounts.source_ages_days) if genome.accounts.source_ages_days else 0
    for age_threshold, amount_threshold in ACCOUNT_AGE_AMOUNT_GATES:
        if min_age < age_threshold:
            if any(a > amount_threshold for a in genome.amounts.values):
                violations.append(
                    f"Account age {min_age}d too young for transactions > {amount_threshold:,}"
                )
            break

    # 5. Max topology depth
    if genome.topology.depth > 8:
        violations.append(f"Topology depth {genome.topology.depth} exceeds maximum 8 hops")

    # 6. Timing sanity
    if any(d <= 0 for d in genome.timing.spacing_days):
        violations.append("spacing_days contains non-positive value")

    # 7. Abandoned node age
    abandoned_count = genome.special_nodes.abandoned_nodes.get("count", 0)
    if abandoned_count > 0 and min_age < 90:
        violations.append(
            f"Abandoned nodes require source accounts >= 90 days old (got {min_age}d)"
        )

    # 8. Width must be positive; collector_count = 0 is valid for fan_out topologies
    if genome.topology.width < 1:
        violations.append("topology.width must be >= 1")
    if genome.topology.collector_count < 1 and genome.topology.type != "fan_out":
        violations.append("topology.collector_count must be >= 1 for non-fan_out topologies")

    return len(violations) == 0, violations
