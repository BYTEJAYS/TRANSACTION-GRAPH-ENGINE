from __future__ import annotations
"""
50 initial fraud seed genomes across 5 MO categories:
  1. Mule Ring (10 seeds)       — fan_in/fan_out chains
  2. Structuring (10 seeds)     — just-under-threshold patterns
  3. Merchant Fraud (10 seeds)  — merchant node exploitation
  4. Festival Fraud (10 seeds)  — Diwali/Eid timing
  5. Abandoned Node (10 seeds)  — time-dilated dormant accounts

Seeds intentionally START as detectable — evolution makes them undetectable.
"""
import uuid
from red_team.core.genome import (
    FraudGenome,
    TopologyGene,
    TimingGene,
    AmountsGene,
    ChannelsGene,
    AccountsGene,
    SpecialNodesGene,
)


def _g(
    lineage_id: str,
    topo_type: str,
    depth: int,
    width: int,
    collector_count: int,
    amounts: list[float],
    spacing_days: list[float],
    time_of_day: str,
    source_ages: list[int],
    velocity_ratio: float,
    channel_mix: dict,
    festival_timing: dict | None = None,
    festival_name: str | None = None,
    mimics_legitimate: str | None = None,
    merchant_nodes: dict | None = None,
    abandoned_nodes: dict | None = None,
    cash_out_method: str | None = None,
    cash_out_delay: int = 0,
    cross_city: bool = False,
    geographic_spread: list[str] | None = None,
    low_slow: bool = False,
    dormancy_periods: list[dict] | None = None,
) -> FraudGenome:
    return FraudGenome(
        lineage_id=lineage_id,
        topology=TopologyGene(
            type=topo_type,
            depth=depth,
            width=width,
            collector_count=collector_count,
            mimics_legitimate=mimics_legitimate,
        ),
        timing=TimingGene(
            spacing_days=spacing_days,
            time_of_day=time_of_day,
            festival_timing=festival_timing,
            festival_name=festival_name,
            low_slow=low_slow,
            dormancy_periods=dormancy_periods or [],
        ),
        amounts=AmountsGene(values=amounts),
        channels=ChannelsGene(mix=channel_mix),
        accounts=AccountsGene(
            source_ages_days=source_ages,
            velocity_ratio=velocity_ratio,
            cross_city=cross_city,
            geographic_spread=geographic_spread or [],
        ),
        special_nodes=SpecialNodesGene(
            merchant_nodes=merchant_nodes or {"count": 0},
            abandoned_nodes=abandoned_nodes or {"count": 0},
            cash_out_method=cash_out_method,
            cash_out_delay_days=cash_out_delay,
        ),
    )


# ── 1. Mule Ring Seeds ────────────────────────────────────────────────────

MULE_RING_SEEDS = [
    _g(
        lineage_id="mule_ring",
        topo_type="fan_in", depth=3, width=i + 3, collector_count=1,
        amounts=[15_000 + i * 2000] * (i + 3),
        spacing_days=[1.0] * (i + 3),
        time_of_day="business_hours",
        source_ages=[90 + i * 10] * (i + 3),
        velocity_ratio=0.4,
        channel_mix={"ach_transfer": 1.0},
    )
    for i in range(10)
]

# ── 2. Structuring Seeds ─────────────────────────────────────────────────

STRUCTURING_SEEDS = [
    _g(
        lineage_id="structuring",
        topo_type="chain", depth=2, width=1, collector_count=1,
        amounts=[49_500 - i * 100, 49_400 - i * 50],
        spacing_days=[0.5],
        time_of_day="afternoon",
        source_ages=[150 + i * 5],
        velocity_ratio=0.6,
        channel_mix={"p2p_transfer": 0.5, "internal_transfer": 0.5},
    )
    for i in range(10)
]

# ── 3. Merchant Fraud Seeds ───────────────────────────────────────────────

MERCHANT_SEEDS = [
    _g(
        lineage_id="merchant_fraud",
        topo_type="bipartite", depth=2, width=2, collector_count=1,
        amounts=[8_000 + i * 500, 7_500 + i * 300],
        spacing_days=[1.0],
        time_of_day="business_hours",
        source_ages=[200 + i * 5, 210 + i * 5],
        velocity_ratio=0.2,
        channel_mix={"ach_transfer": 1.0},
        merchant_nodes={"count": 1, "mcc_codes": [5040], "invoice_pattern": True},
        mimics_legitimate="business_invoice_settlement",
    )
    for i in range(10)
]

# ── 4. Festival Fraud Seeds ───────────────────────────────────────────────

FESTIVAL_SEEDS = [
    _g(
        lineage_id="festival_fraud",
        topo_type="fan_out", depth=2, width=5, collector_count=0,
        amounts=[4_800 - i * 100] * 5,
        spacing_days=[0.08] * 5,
        time_of_day="afternoon",
        source_ages=[200 + i * 10],
        velocity_ratio=0.3,
        channel_mix={"p2p_transfer": 1.0},
        festival_timing={"name": "diwali", "month": 10},
        festival_name="diwali",
    )
    for i in range(10)
]

# ── 5. Abandoned Node Seeds ───────────────────────────────────────────────

ABANDONED_SEEDS = [
    _g(
        lineage_id="abandoned_node",
        topo_type="chain", depth=3, width=1, collector_count=1,
        amounts=[12_000 + i * 1000, 11_500 + i * 800, 11_000 + i * 600],
        spacing_days=[30.0 + i * 2, 30.0 + i * 2],
        time_of_day="morning",
        source_ages=[300 + i * 5],
        velocity_ratio=0.05,
        channel_mix={"ach_transfer": 1.0},
        abandoned_nodes={"count": 1, "dormancy_days": 30 + i * 5},
        low_slow=True,
        dormancy_periods=[{"after_txn": 1, "duration_days": 30 + i * 5}],
    )
    for i in range(10)
]


# Combined seed list — 50 genomes
SEED_GENOMES: list[FraudGenome] = (
    MULE_RING_SEEDS
    + STRUCTURING_SEEDS
    + MERCHANT_SEEDS
    + FESTIVAL_SEEDS
    + ABANDONED_SEEDS
)
