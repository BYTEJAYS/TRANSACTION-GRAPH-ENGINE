from __future__ import annotations
import copy
import random
import logging

from red_team.core.genome import FraudGenome
from red_team.core.rail_constraints import RailConstraintViolation

logger = logging.getLogger(__name__)


def add_hop(genome: FraudGenome) -> FraudGenome:
    """
    More hops push the chain beyond Blue Team's pre-computed 8-hop detection window.
    Each bridge adds ~T+1 settlement delay, spreading the trail across more time
    and making fund trail reconstruction more expensive.
    """
    if genome.topology.depth >= 8:
        raise RailConstraintViolation("Max depth 8 reached — add_hop would exceed rail limit")

    g = copy.deepcopy(genome)
    bridge = {
        "node_type": "bridge",
        "account_age_days": random.randint(90, 365),
        "hold_days": random.choice([0, 1, 2]),
        "partial_forward": random.random() > 0.7,
    }
    g.topology.bridge_nodes.append(bridge)
    g.topology.depth += 1
    g.special_nodes.bridge_nodes["count"] = g.special_nodes.bridge_nodes.get("count", 0) + 1
    g.mutation_history.append("add_hop")
    return g


def fan_out_collector(genome: FraudGenome) -> FraudGenome:
    """
    Splits 1 large collector into N smaller collectors, dropping each receiver's
    density below Blue Team's bipartite gate threshold (requires ≥5 senders AND density >0.7).
    Density per sub-collector = 1-2 senders each → well below detection.
    """
    if genome.topology.width < 2:
        raise RailConstraintViolation("fan_out_collector requires width >= 2 to split")

    g = copy.deepcopy(genome)
    num_new = random.choice([2, 3])
    g.topology.collector_count = num_new
    g.topology.width = max(2, g.topology.width // num_new)

    # Redistribute amounts: each original amount becomes split across collectors
    if g.amounts.values:
        base_amount = g.amounts.values[0]
        split = [round(base_amount / num_new * (1 + random.uniform(-0.03, 0.03)), 2) for _ in range(num_new)]
        g.amounts.values = split * max(1, len(g.amounts.values) // num_new)
        g.amounts.values = g.amounts.values[:len(g.amounts.values)]

    g.flags.append("bipartite_density_split")
    g.mutation_history.append("fan_out_collector")
    return g


def insert_abandoned_node(genome: FraudGenome) -> FraudGenome:
    """
    Abandoned accounts (send once, then dormant 60+ days) break velocity AND
    sequence detection simultaneously. Blue Team's behavioral model has no prior
    for an account with 1 transaction — no velocity, no sequence, no baseline.
    """
    min_age = min(genome.accounts.source_ages_days) if genome.accounts.source_ages_days else 0
    if min_age < 90:
        raise RailConstraintViolation(
            f"Abandoned nodes need source accounts ≥ 90 days old (got {min_age}d)"
        )

    g = copy.deepcopy(genome)
    dormancy_days = random.choice([60, 90, 120, 180])
    current = g.special_nodes.abandoned_nodes
    g.special_nodes.abandoned_nodes = {
        "count": current.get("count", 0) + 1,
        "dormancy_days": dormancy_days,
        "purpose": "break_velocity_and_sequence_detection",
        "account_age_days": random.randint(90, 365),
        "prior_legit_transactions": random.randint(1, 5),
    }
    g.mutation_history.append("insert_abandoned_node")
    return g


def insert_merchant_node(genome: FraudGenome) -> FraudGenome:
    """
    Merchant accounts trigger Blue Team's bipartite legitimacy filter: is_merchant
    AND density < 0.85 → gate suppressed. Payments to merchants look like purchases.
    We use MCC codes with large transaction norms so amounts don't trigger MCC-mismatch gate.
    """
    PROFILES = {
        "wholesale_trader":       {"mcc": "5040", "amount_range": (5_000, 100_000)},
        "it_services":            {"mcc": "7372", "amount_range": (10_000, 200_000)},
        "transport":              {"mcc": "4789", "amount_range": (2_000, 50_000)},
        "professional_services":  {"mcc": "7389", "amount_range": (5_000, 150_000)},
    }
    profile_name = random.choice(list(PROFILES))
    profile = PROFILES[profile_name]

    g = copy.deepcopy(genome)
    current = g.special_nodes.merchant_nodes
    existing_codes = current.get("mcc_codes", [])
    g.special_nodes.merchant_nodes = {
        "count": current.get("count", 0) + 1,
        "mcc_codes": existing_codes + [profile["mcc"]],
        "invoice_pattern": True,
        "profile": profile_name,
        "registered_days": random.randint(180, 730),
    }
    merchant_node = {
        "node_type": "merchant",
        "mcc": profile["mcc"],
        "profile": profile_name,
        "amount_range": profile["amount_range"],
        "registered_days": random.randint(180, 730),
        "prior_legit_revenue": True,
    }
    g.topology.merchant_nodes.append(merchant_node)
    g.mutation_history.append("insert_merchant_node")
    return g


def create_bipartite_split(genome: FraudGenome) -> FraudGenome:
    """
    Blue Team's bipartite gate fires when sender_count >= 5 AND density > 0.7.
    Splitting one large fan-in (7 senders → 1 collector) into 3 small fan-ins
    (2-3 senders each) means every sub-group falls individually below the 5-sender
    threshold and is never seen as a bipartite core.
    """
    if genome.topology.width < 4:
        raise RailConstraintViolation(
            f"create_bipartite_split needs width >= 4 to split meaningfully (got {genome.topology.width})"
        )

    g = copy.deepcopy(genome)
    num_groups = random.choice([3, 4])
    g.topology.collector_count = num_groups
    # Each group now has fewer senders — below the 5-sender detection threshold
    g.topology.width = max(2, g.topology.width // num_groups)
    g.topology.depth += 1  # extra aggregation layer added
    g.flags.append(f"bipartite_split_{num_groups}_groups")
    g.mutation_history.append("create_bipartite_split")
    return g
