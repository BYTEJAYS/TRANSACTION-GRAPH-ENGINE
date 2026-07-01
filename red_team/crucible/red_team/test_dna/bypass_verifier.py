#!/usr/bin/env python3
"""
Bypass Verifier — runs all 3 test DNAs through MockBlueTeam and asserts score < 0.5.

Usage:
    python -m red_team.test_dna.bypass_verifier
    # or directly:
    python test_dna/bypass_verifier.py

Exit code 0 = all DNAs bypass Blue Team (score < 0.5).
Exit code 1 = at least one DNA was detected (score >= 0.5).
"""
import json
import os
import sys
import uuid

# Ensure package root is on path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from red_team.core.genome import (
    FraudGenome, TopologyGene, TimingGene, AmountsGene,
    ChannelsGene, AccountsGene, SpecialNodesGene,
)
from red_team.sandbox.blue_clone import MockBlueTeam
from red_team.test_dna.account_fixtures import DNA_001_FIXTURES, DNA_002_FIXTURES, DNA_003_FIXTURES

OUTPUTS_DIR = os.path.join(os.path.dirname(__file__), "outputs")
SCORE_THRESHOLD = 0.50  # must be strictly below to count as bypass


def _load_dna(filename: str) -> dict:
    path = os.path.join(OUTPUTS_DIR, filename)
    with open(path) as f:
        return json.load(f)


def _build_dna_001_genome() -> FraudGenome:
    """Merchant bipartite split — 2 senders per merchant, 18-day delay to sink."""
    return FraudGenome(
        lineage_id="test_dna_001",
        topology=TopologyGene(
            type="bipartite",
            depth=3,
            width=2,   # 2 senders per merchant — below 5-sender threshold
            collector_count=3,
            mimics_legitimate="business_invoice_settlement",
        ),
        timing=TimingGene(
            spacing_days=[1.0, 2.0, 1.0, 3.0, 2.0, 1.0, 18.0, 1.0],
            time_of_day="business_hours",
        ),
        amounts=AmountsGene(values=[8347, 7891, 9214, 8603, 8021, 7654, 15938, 17517, 15275]),
        channels=ChannelsGene(mix={"ach_transfer": 0.67, "internal_transfer": 0.33}),
        accounts=AccountsGene(
            source_ages_days=[220, 235, 210, 245, 230, 215, 365, 420, 390],
            velocity_ratio=0.15,
        ),
        special_nodes=SpecialNodesGene(
            merchant_nodes={"count": 3, "mcc_codes": [5040], "invoice_pattern": True},
            cash_out_delay_days=18,
        ),
    )


def _build_dna_002_genome() -> FraudGenome:
    """Abandoned node time dilation — 4 sources, 35-day spacing, 300+ day accounts."""
    return FraudGenome(
        lineage_id="test_dna_002",
        topology=TopologyGene(
            type="fan_in",
            depth=2,
            width=4,   # 4 senders — below bipartite 5-sender threshold
            collector_count=1,
        ),
        timing=TimingGene(
            spacing_days=[35.0, 35.0, 35.0],  # 35-day gaps between inflows
            time_of_day="morning",
            low_slow=True,
        ),
        amounts=AmountsGene(values=[13450, 11870, 14230, 12615]),
        channels=ChannelsGene(mix={"ach_transfer": 1.0}),
        accounts=AccountsGene(
            source_ages_days=[320, 310, 335, 305, 400],
            velocity_ratio=0.04,  # very low velocity
        ),
        special_nodes=SpecialNodesGene(
            abandoned_nodes={"count": 4, "dormancy_days": 35},
        ),
    )


def _build_dna_003_genome() -> FraudGenome:
    """Festival fan-out — Diwali timing, amounts < ₹5k, Indian context 30% reduction."""
    return FraudGenome(
        lineage_id="test_dna_003",
        topology=TopologyGene(
            type="fan_out",
            depth=2,
            width=5,
            collector_count=0,
        ),
        timing=TimingGene(
            spacing_days=[0.09, 0.04, 0.10, 0.04],  # 2-4 hours between txns
            time_of_day="afternoon",
            festival_timing={"name": "diwali", "month": 10},
            festival_name="diwali",
        ),
        amounts=AmountsGene(values=[4800, 4650, 4750, 4890, 4720]),
        channels=ChannelsGene(mix={"p2p_transfer": 1.0}),
        accounts=AccountsGene(
            source_ages_days=[210, 220, 200, 215, 205, 225],
            velocity_ratio=0.25,
        ),
        special_nodes=SpecialNodesGene(),
    )


def verify_all() -> bool:
    results = []
    test_cases = [
        ("DNA 001 — Merchant Bipartite Split", _build_dna_001_genome(), DNA_001_FIXTURES),
        ("DNA 002 — Abandoned Node Time Dilation", _build_dna_002_genome(), DNA_002_FIXTURES),
        ("DNA 003 — Festival Fan-Out Cover", _build_dna_003_genome(), DNA_003_FIXTURES),
    ]

    all_passed = True
    print("\n" + "=" * 60)
    print("CRUCIBLE Red Team — Bypass Verifier")
    print("=" * 60)

    for name, genome, fixtures in test_cases:
        bt = MockBlueTeam(account_fixtures=fixtures)
        scores = bt.score(genome)
        champion = scores[0]
        action = bt.score_action(scores)
        passed = champion < SCORE_THRESHOLD

        status = "PASS ✓" if passed else "FAIL ✗"
        print(f"\n{name}")
        print(f"  Champion score: {champion:.4f}  |  Action: {action}  |  {status}")
        print(f"  All scores: {[round(s, 4) for s in scores]}")

        if not passed:
            all_passed = False
            print(f"  ERROR: Score {champion:.4f} >= threshold {SCORE_THRESHOLD}")
        else:
            print(f"  Blue Team does NOT detect this pattern (score < {SCORE_THRESHOLD})")

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL 3 DNA BYPASS BLUE TEAM — Red Team evolution successful.")
    else:
        print("SOME DNA DETECTED — review bypass logic above.")
    print("=" * 60 + "\n")

    return all_passed


if __name__ == "__main__":
    success = verify_all()
    sys.exit(0 if success else 1)
