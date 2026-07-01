#!/usr/bin/env python3
"""
Attack Loop — generates fraud graph variants and scores against MockBlueTeam.

Qualifying bypass criteria (both must be true):
  1. champion_score < --threshold  (default 0.75)
  2. is_confirmed_fraud() == True  (structural fraud confirmation)

Qualifying patterns are saved as DNA JSON files in test_dna/outputs/.
Blue team is locked at BLUE_TEAM_VERSION — no changes to blue_clone.py affect
past DNA files, since the version is embedded in each saved record.

Usage:
    python -m red_team.scripts.attack_loop
    python -m red_team.scripts.attack_loop --variants 500 --threshold 0.75
    python -m red_team.scripts.attack_loop --variants 1000 --threshold 0.65 --seed 42
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from red_team.core.genome import (
    AccountsGene, AmountsGene, ChannelsGene, FraudGenome,
    SpecialNodesGene, TimingGene, TopologyGene,
)
from red_team.sandbox.blue_clone import BLUE_TEAM_VERSION, MockBlueTeam

OUTPUTS_DIR = Path(__file__).parent.parent / "test_dna" / "outputs"
DEFAULT_THRESHOLD = 0.75
DEFAULT_VARIANTS = 300


# ── Structural fraud confirmation ─────────────────────────────────────────────

def is_confirmed_fraud(genome: FraudGenome) -> tuple[bool, str]:
    """
    Returns (True, reason) when a pattern is structurally fraud regardless of score.
    Rules are derived from known Indian fraud MOs: smurfing, structuring, mule collection.
    A pattern qualifies as a DNA only when this AND blue team score < threshold.
    """
    amounts = genome.amounts.values
    if not amounts or len(amounts) < 2:
        return False, ""

    avg = sum(amounts) / len(amounts)
    variance = sum((a - avg) ** 2 for a in amounts) / len(amounts)
    cv = (variance ** 0.5) / avg if avg > 0 else 1.0

    # Fan-in smurfing: multiple senders → 1 collector, uniform amounts, ₹10k–₹50k range
    if (
        genome.topology.type in ("fan_in", "bipartite")
        and genome.topology.width >= 3
        and cv < 0.25
        and 10_000 <= avg <= 50_000
    ):
        return True, (
            f"fan_in_smurfing(width={genome.topology.width}, "
            f"cv={cv:.3f}, avg_amt={avg:.0f})"
        )

    # Threshold structuring: amounts cluster just below ₹15k / ₹50k / ₹100k
    for sentinel in [15_000, 50_000, 100_000]:
        below = sum(1 for a in amounts if sentinel * 0.80 <= a < sentinel)
        if below >= 3:
            return True, f"threshold_structuring(sentinel={sentinel}, count={below})"

    # Layered mule collection: 3+ layers, 3+ nodes wide
    if (
        genome.topology.type == "layered"
        and genome.topology.depth >= 3
        and genome.topology.width >= 3
    ):
        return True, (
            f"layered_mule(depth={genome.topology.depth}, "
            f"width={genome.topology.width})"
        )

    # Rapid structuring: high velocity + uniform amounts + multiple sources
    if (
        len(amounts) >= 4
        and cv < 0.15
        and genome.accounts.velocity_ratio > 0.5
        and genome.topology.width >= 4
    ):
        return True, (
            f"rapid_structuring(cv={cv:.3f}, "
            f"vel={genome.accounts.velocity_ratio:.2f})"
        )

    return False, ""


# ── Account fixture builder ───────────────────────────────────────────────────

def _acc_id(genome_id: str, role: str) -> str:
    return "acc_" + hashlib.md5(f"{genome_id}_{role}".encode()).hexdigest()[:10]


def _build_fixtures(genome: FraudGenome, collector_age_days: int) -> dict:
    fixtures: dict = {}
    gid = genome.genome_id
    src_ages = genome.accounts.source_ages_days
    avg_amt = (
        sum(genome.amounts.values) / len(genome.amounts.values)
        if genome.amounts.values else 10_000
    )

    if genome.topology.type in ("fan_in", "bipartite"):
        for i in range(genome.topology.width):
            age = src_ages[i % len(src_ages)] if src_ages else 300
            fixtures[_acc_id(gid, f"src{i}")] = {
                "account_age_days": age,
                "account_type": "SAVINGS",
                "kyc_occupation": "salaried",
                "kyc_age": 32,
                "is_merchant": False,
                "avg_amount_30d": avg_amt * 0.4,
                "prior_monthly_txn_count": 8,
                "has_festival_gifting_history": False,
                "payee_vpa_age_days": collector_age_days,
                "role": "source",
            }
        n_collectors = max(1, genome.topology.collector_count)
        for j in range(n_collectors):
            fixtures[_acc_id(gid, f"col{j}")] = {
                "account_age_days": collector_age_days,
                "account_type": "SAVINGS",
                "kyc_occupation": "salaried",
                "kyc_age": 28,
                "is_merchant": False,
                "avg_amount_30d": 4_000.0,
                "prior_monthly_txn_count": 3,
                "has_festival_gifting_history": False,
                "payee_vpa_age_days": collector_age_days,
                "role": "collector",
            }
    else:
        # Generic fixtures for chain/layered topologies
        total_nodes = max(2, genome.topology.width)
        for i in range(total_nodes):
            age = src_ages[i % len(src_ages)] if src_ages else 300
            fixtures[_acc_id(gid, f"n{i}")] = {
                "account_age_days": age,
                "account_type": "SAVINGS",
                "kyc_occupation": "salaried",
                "kyc_age": 30,
                "is_merchant": False,
                "avg_amount_30d": avg_amt * 0.5,
                "prior_monthly_txn_count": 10,
                "has_festival_gifting_history": False,
                "payee_vpa_age_days": collector_age_days,
                "role": "source" if i < total_nodes - 1 else "collector",
            }

    return fixtures


# ── Variant generator ─────────────────────────────────────────────────────────

_SEED_AMOUNTS = [14500, 15200, 13800, 16100, 14900, 15600, 13500, 17200, 14700, 15300]

_AMOUNT_BASES = [
    _SEED_AMOUNTS,                                  # original fan-in (user's graph)
    [8000, 7800, 8200, 7900, 8100],                # lower range
    [24000, 23800, 24500, 23200, 24800],            # mid-high
    [49200, 48800, 49500, 48600, 49100],            # near-50k sentinel
    [12000, 11500, 12500, 11800, 12200],            # ₹12k cluster
    [9800, 9750, 9900, 9650, 9880],                 # near-10k
    [4800, 4750, 4900, 4650, 4820],                 # sub-5k (festival range)
    [19500, 19200, 19800, 18900, 19600],            # near-20k
]

_CHANNEL_MIXES = [
    {"ach_transfer": 1.0},
    {"p2p_transfer": 1.0},
    {"ach_transfer": 0.6, "p2p_transfer": 0.4},
    {"ach_transfer": 0.5, "internal_transfer": 0.5},
    {"p2p_transfer": 0.7, "internal_transfer": 0.3},
    {"ach_transfer": 0.4, "p2p_transfer": 0.4, "internal_transfer": 0.2},
]

_SPACING_HOURS = [
    0.063,   # ~1.5 h   (original — burst)
    0.125,   # ~3 h
    0.25,    # ~6 h
    0.5,     # 12 h
    1.0,     # 1 day
    7.0,     # 1 week
    35.0,    # 5 weeks  (very slow — evades velocity gate)
]


def generate_variants(
    n: int,
    rng: random.Random,
) -> Iterator[tuple[FraudGenome, dict]]:
    """
    Yields (genome, account_fixtures) pairs covering a broad parameter space.
    Each combination of (topo_type, width, collector_age, spacing, primary_channel)
    is deduplicated so no two variants are identical on the key axes.
    """
    widths = [2, 3, 4, 5, 6, 8, 10, 12, 15]
    collector_ages = [50, 90, 130, 160, 200, 250, 365, 500]
    topo_types = ["fan_in", "bipartite", "chain", "layered"]
    times_of_day = ["morning", "business_hours", "afternoon"]

    seen: set[tuple] = set()
    count = 0

    while count < n:
        width = rng.choice(widths)
        col_age = rng.choice(collector_ages)
        spacing_base = rng.choice(_SPACING_HOURS)
        chan_mix: dict = dict(rng.choice(_CHANNEL_MIXES))
        topo_type = rng.choice(topo_types)
        depth = rng.choice([2, 3, 4])
        src_age = rng.randint(180, 500)
        velocity = rng.uniform(0.04, 0.90)

        # Amounts: 30% chance of fully random, otherwise pick from bases
        if rng.random() < 0.3:
            base_amt = rng.randint(8_000, 48_000)
            amounts = [
                max(1_000, base_amt + rng.randint(-1_500, 1_500))
                for _ in range(width)
            ]
        else:
            base = list(rng.choice(_AMOUNT_BASES))
            amounts = [max(1_000, a + rng.randint(-500, 500)) for a in base[:width] or base]

        # Pad to match width
        while len(amounts) < width:
            amounts.append(max(1_000, amounts[-1] + rng.randint(-300, 300)))

        primary_channel = sorted(chan_mix.keys())[0]
        key = (topo_type, width, col_age, round(spacing_base, 3), primary_channel)
        if key in seen:
            continue
        seen.add(key)

        collector_count = max(1, width // 3) if topo_type == "bipartite" else 1
        spacing = [spacing_base] * max(1, width - 1)

        genome = FraudGenome(
            lineage_id=f"atk_{uuid.uuid4().hex[:8]}",
            topology=TopologyGene(
                type=topo_type,
                depth=depth,
                width=width,
                collector_count=collector_count,
            ),
            timing=TimingGene(
                spacing_days=spacing,
                time_of_day=rng.choice(times_of_day),
                low_slow=(spacing_base >= 1.0),
            ),
            amounts=AmountsGene(values=amounts),
            channels=ChannelsGene(mix=chan_mix),
            accounts=AccountsGene(
                source_ages_days=[src_age] * width,
                velocity_ratio=velocity,
            ),
            special_nodes=SpecialNodesGene(),
        )

        fixtures = _build_fixtures(genome, collector_age_days=col_age)
        count += 1
        yield genome, fixtures


# ── DNA file export ───────────────────────────────────────────────────────────

def _save_dna(
    genome: FraudGenome,
    score: float,
    all_scores: list[float],
    action: str,
    fraud_reason: str,
    threshold: float,
    run_id: str,
    idx: int,
) -> Path:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"attack_{run_id}_{idx:04d}.json"
    path = OUTPUTS_DIR / filename

    record = {
        "meta": {
            "run_id": run_id,
            "blue_team_version": BLUE_TEAM_VERSION,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "champion_score": score,
            "all_scores": all_scores,
            "action": action,
            "bypass_threshold": threshold,
            "fraud_confirmation": fraud_reason,
        },
        "genome_params": {
            "topology_type": genome.topology.type,
            "width": genome.topology.width,
            "depth": genome.topology.depth,
            "collector_count": genome.topology.collector_count,
            "spacing_days": genome.timing.spacing_days[:3],
            "time_of_day": genome.timing.time_of_day,
            "low_slow": genome.timing.low_slow,
            "channels": genome.channels.mix,
            "source_age_days": genome.accounts.source_ages_days[0],
            "velocity_ratio": genome.accounts.velocity_ratio,
            "avg_amount": round(
                sum(genome.amounts.values) / len(genome.amounts.values), 2
            ),
        },
        "transactions": genome.to_transaction_list(),
        "genome": genome.to_dict(),
    }

    with open(path, "w") as f:
        json.dump(record, f, indent=2, default=str)

    return path


# ── Main ──────────────────────────────────────────────────────────────────────

def run_attack(variants: int, threshold: float, seed: int | None = None) -> None:
    rng = random.Random(seed)
    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S")

    sep = "=" * 68
    print(f"\n{sep}")
    print(f"  CRUCIBLE Attack Loop   run={run_id}   bt={BLUE_TEAM_VERSION}")
    print(f"  Variants: {variants}   Bypass threshold: champion < {threshold}")
    print(f"{sep}\n")

    total = caught = bypassed = non_fraud = 0
    saved_paths: list[Path] = []

    for genome, fixtures in generate_variants(variants, rng):
        total += 1
        is_fraud, reason = is_confirmed_fraud(genome)

        if not is_fraud:
            non_fraud += 1
            continue

        bt = MockBlueTeam(account_fixtures=fixtures)
        scores = bt.score(genome)
        champion = scores[0]
        action = bt.score_action(scores)

        if champion < threshold:
            bypassed += 1
            path = _save_dna(
                genome, champion, scores, action,
                reason, threshold, run_id, bypassed,
            )
            saved_paths.append(path)
            print(
                f"  BYPASS [{bypassed:04d}]  score={champion:.4f}  action={action}\n"
                f"    topo={genome.topology.type}  width={genome.topology.width}"
                f"  depth={genome.topology.depth}"
                f"  spacing={genome.timing.spacing_days[0]:.3f}d\n"
                f"    channels={list(genome.channels.mix.keys())}"
                f"  src_age={genome.accounts.source_ages_days[0]}d\n"
                f"    reason: {reason}\n"
                f"    → {path.name}\n"
            )
        else:
            caught += 1

        if total % 50 == 0:
            pct = bypassed / max(1, total - non_fraud) * 100
            print(
                f"  ... {total}/{variants} scanned   "
                f"bypassed={bypassed}  caught={caught}  "
                f"bypass_rate={pct:.1f}%"
            )

    fraud_tested = total - non_fraud
    bypass_rate = bypassed / max(1, fraud_tested) * 100

    print(f"\n{sep}")
    print(f"  Scan complete")
    print(f"    Total variants   : {total}")
    print(f"    Confirmed fraud  : {fraud_tested}")
    print(f"    Bypassed (<{threshold}) : {bypassed}  ({bypass_rate:.1f}%)")
    print(f"    Caught           : {caught}")
    print(f"    Not fraud (skip) : {non_fraud}")
    print(f"    DNA files saved  : {OUTPUTS_DIR}")
    print(f"{sep}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CRUCIBLE Attack Loop")
    parser.add_argument(
        "--variants", type=int, default=DEFAULT_VARIANTS,
        help="Number of graph variants to generate (default 300)",
    )
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD,
        help="Blue team score below which a pattern is a bypass (default 0.75)",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="RNG seed for reproducible runs",
    )
    args = parser.parse_args()
    run_attack(variants=args.variants, threshold=args.threshold, seed=args.seed)
