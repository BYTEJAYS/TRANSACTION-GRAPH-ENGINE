from __future__ import annotations
import copy
import random
import logging

from red_team.core.genome import FraudGenome
from red_team.core.rail_constraints import RailConstraintViolation

logger = logging.getLogger(__name__)

P2P_APPS = ["venmo", "zelle", "cashapp", "paypal", "apple_pay"]

# Multi-channel sequences that spread the anomaly signal across different detection models
CHANNEL_COMBOS = [
    ["p2p_transfer", "internal_transfer", "ach_transfer"],
    ["internal_transfer", "ach_transfer", "p2p_transfer"],
    ["p2p_transfer", "ach_transfer"],
    ["internal_transfer", "p2p_transfer"],
    ["wire_transfer", "ach_transfer", "internal_transfer"],
    ["crypto_exchange", "ach_transfer"],
    ["p2p_transfer", "bill_payment", "internal_transfer"],
]


def channel_hop(genome: FraudGenome) -> FraudGenome:
    """
    Blue Team builds per-channel behavioral models. Hopping channels distributes
    the anomaly signal — each model sees only 1 unusual transaction, not enough
    to fire individually. Cross-channel correlation requires graph-level analysis.
    """
    g = copy.deepcopy(genome)
    sequence = random.choice(CHANNEL_COMBOS)

    g.channels.channel_hop = True
    g.channels.channel_sequence = sequence
    g.channels.mix = {ch: round(1.0 / len(sequence), 3) for ch in sequence}
    g.mutation_history.append("channel_hop")
    return g


def upi_app_diversity(genome: FraudGenome) -> FraudGenome:
    """
    Banks monitor payment app as a cross-account clustering signal. Using a different
    app per source account breaks the cluster fingerprint — each account looks
    like an independent user with their own preferred app.
    """
    g = copy.deepcopy(genome)
    n_accounts = len(g.accounts.source_ages_days)
    if n_accounts == 0:
        raise RailConstraintViolation("No source accounts to assign p2p apps to")

    apps = random.sample(P2P_APPS, min(n_accounts, len(P2P_APPS)))
    while len(apps) < n_accounts:
        apps.append(random.choice(P2P_APPS))

    g.channels.upi_app_diversity = True
    g.channels.upi_apps = apps[:n_accounts]
    if "p2p_transfer" not in g.channels.mix:
        g.channels.mix["p2p_transfer"] = 0.8
    g.mutation_history.append("upi_app_diversity")
    return g
