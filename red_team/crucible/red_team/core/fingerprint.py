from __future__ import annotations
import json
import hashlib
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from red_team.core.genome import FraudGenome


def compute_fingerprint(genome: "FraudGenome") -> str:
    """
    Structural fingerprint — same fraud pattern structure hashes identically
    regardless of specific amounts, account IDs, or timestamps.
    Used by Bloom filter for exact-duplicate detection.
    """
    min_age = min(genome.accounts.source_ages_days) if genome.accounts.source_ages_days else 0
    key = {
        "topology_type": genome.topology.type,
        "depth": genome.topology.depth,
        "width": genome.topology.width,
        "collector_count": genome.topology.collector_count,
        "timing_low_slow": genome.timing.low_slow,
        "timing_festival": bool(genome.timing.festival_timing),
        "timing_festival_name": genome.timing.festival_name,
        "has_dormancy": len(genome.timing.dormancy_periods) > 0,
        "dormancy_count": len(genome.timing.dormancy_periods),
        "amount_pattern": genome.amounts.pattern,
        "just_under_threshold": genome.amounts.just_under_threshold,
        "channel_hop": genome.channels.channel_hop,
        "upi_diversity": genome.channels.upi_app_diversity,
        "primary_channel": max(genome.channels.mix, key=genome.channels.mix.get) if genome.channels.mix else "ach_transfer",
        "has_abandoned": genome.special_nodes.abandoned_nodes.get("count", 0) > 0,
        "has_merchant": genome.special_nodes.merchant_nodes.get("count", 0) > 0,
        "has_bridge": genome.special_nodes.bridge_nodes.get("count", 0) > 0,
        "cash_out_method": genome.special_nodes.cash_out_method,
        "mimics_legitimate": genome.topology.mimics_legitimate,
        "account_age_band": "young" if min_age < 180 else "aged",
        "geographic_spread": genome.accounts.cross_city,
        "kyc_tier": genome.accounts.kyc_tier,
        "has_layers": bool(genome.topology.layers),
    }
    canonical = json.dumps(key, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def compute_embedding(genome: "FraudGenome") -> np.ndarray:
    """
    256-dimensional L2-normalized float32 vector.
    Similar fraud patterns produce similar vectors — FAISS cosine similarity
    finds near-duplicates that Bloom filter misses.
    """
    source_ages = genome.accounts.source_ages_days or [0]
    amounts = genome.amounts.values or [0.0]

    base: list[float] = [
        # Topology dims
        genome.topology.depth / 10.0,
        genome.topology.width / 20.0,
        genome.topology.collector_count / 5.0,
        # Special node counts
        genome.special_nodes.abandoned_nodes.get("count", 0) / 10.0,
        genome.special_nodes.merchant_nodes.get("count", 0) / 5.0,
        genome.special_nodes.bridge_nodes.get("count", 0) / 5.0,
        genome.special_nodes.exchange_nodes.get("count", 0) / 3.0,
        # Timing
        genome.timing.jitter,
        1.0 if genome.timing.low_slow else 0.0,
        1.0 if genome.timing.festival_timing else 0.0,
        len(genome.timing.dormancy_periods) / 5.0,
        genome.timing.burst_behavior and 1.0 or 0.0,
        sum(genome.timing.spacing_days) / 365.0 if genome.timing.spacing_days else 0.0,
        len(genome.timing.spacing_days) / 20.0,
        # Accounts
        genome.accounts.velocity_ratio,
        min(source_ages) / 365.0,
        max(source_ages) / 365.0,
        sum(source_ages) / (len(source_ages) * 365.0),
        len(genome.accounts.geographic_spread) / 8.0,
        1.0 if genome.accounts.cross_city else 0.0,
        # Amounts
        genome.amounts.noise_percent,
        1.0 if genome.amounts.just_under_threshold else 0.0,
        1.0 if genome.amounts.round_number_avoidance else 0.0,
        min(amounts) / 200_000.0,
        max(amounts) / 200_000.0,
        sum(amounts) / 1_000_000.0,
        len(amounts) / 20.0,
        # Channels
        genome.channels.mix.get("p2p_transfer", 0.0),
        genome.channels.mix.get("internal_transfer", 0.0),
        genome.channels.mix.get("ach_transfer", 0.0),
        genome.channels.mix.get("wire_transfer", 0.0),
        1.0 if genome.channels.channel_hop else 0.0,
        1.0 if genome.channels.upi_app_diversity else 0.0,
        len(genome.channels.channel_sequence) / 4.0,
        len(genome.channels.upi_apps) / 5.0,
        # Structural
        1.0 if genome.topology.mimics_legitimate else 0.0,
        1.0 if genome.special_nodes.cash_out_method else 0.0,
        genome.special_nodes.cash_out_delay_days / 60.0,
        bool(genome.topology.layers) and 1.0 or 0.0,
        len(genome.topology.layers or []) / 6.0,
        # Topology type one-hot
        1.0 if genome.topology.type == "fan_in" else 0.0,
        1.0 if genome.topology.type == "fan_out" else 0.0,
        1.0 if genome.topology.type == "cycle" else 0.0,
        1.0 if genome.topology.type == "chain" else 0.0,
        1.0 if genome.topology.type == "bipartite" else 0.0,
        1.0 if genome.topology.type == "layered" else 0.0,
        # KYC one-hot
        1.0 if genome.accounts.kyc_tier == "min" else 0.0,
        1.0 if genome.accounts.kyc_tier == "basic" else 0.0,
        1.0 if genome.accounts.kyc_tier == "full" else 0.0,
        # Cash out method one-hot
        1.0 if genome.special_nodes.cash_out_method == "delayed_14d" else 0.0,
        1.0 if genome.special_nodes.cash_out_method == "pos_goods_resale" else 0.0,
        1.0 if genome.special_nodes.cash_out_method == "wallet_hop" else 0.0,
        1.0 if genome.special_nodes.cash_out_method == "gold_purchase" else 0.0,
    ]

    # Pad to 256 with interaction features
    while len(base) < 256:
        i = len(base)
        a = base[i % len(base[:53])]
        b = base[(i + 7) % len(base[:53])]
        base.append(a * b)

    arr = np.array(base[:256], dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm > 0:
        arr = arr / norm
    return arr
