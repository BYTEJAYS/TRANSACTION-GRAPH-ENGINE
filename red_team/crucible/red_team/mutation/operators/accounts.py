from __future__ import annotations
import copy
import random
import logging

from red_team.core.genome import FraudGenome
from red_team.core.rail_constraints import RailConstraintViolation

logger = logging.getLogger(__name__)

# Blue Team's cash_mule_sink_gate hard threshold — only fires for accounts ≤ 180 days
CASH_MULE_AGE_THRESHOLD = 180

# Major Indian cities for geographic spread — high volumes, diverse demographics
CITIES = ["Mumbai", "Delhi", "Bangalore", "Chennai", "Hyderabad", "Pune", "Ahmedabad", "Kolkata"]


def age_the_accounts(genome: FraudGenome) -> FraudGenome:
    """
    Blue Team's cash_mule_sink_gate fires only when account_age_days ≤ 180.
    Pushing ALL source accounts to 200+ days means this gate never even evaluates
    the rest of its conditions — it returns False immediately at the age check.
    This is the single highest-ROI evasion operator: one gate completely bypassed.
    """
    g = copy.deepcopy(genome)
    min_age = random.choice([200, 250, 300, 365])  # well above 180-day threshold
    n = len(g.accounts.source_ages_days) or 1

    g.accounts.source_ages_days = [
        random.randint(min_age, min_age + 180) for _ in range(n)
    ]
    g.accounts.prior_legit_transactions_per_account = random.randint(5, 20)
    g.mutation_history.append("age_the_accounts")
    return g


def reduce_velocity(genome: FraudGenome) -> FraudGenome:
    """
    Blue Team's Tier 1 velocity_spike flag fires when velocity_1h > 5.
    At velocity_ratio < 0.08 (< 8% of normal monthly volume), the fraudulent
    transactions are statistical noise in the account's overall activity — the
    velocity counter never crosses any threshold.
    """
    g = copy.deepcopy(genome)
    g.accounts.velocity_ratio = round(random.uniform(0.02, 0.08), 3)
    g.accounts.prior_legit_transactions_per_account = random.randint(30, 100)
    g.mutation_history.append("reduce_velocity")
    return g


def geographic_spread(genome: FraudGenome) -> FraudGenome:
    """
    Blue Team correlates accounts by geographic proximity — same PIN code across
    multiple flagged accounts is a clustering signal. Spreading source accounts
    across 4-5 different cities breaks geographic clustering entirely.
    Each city also has different KYC verification paths (some use V-CIP),
    making the accounts look independently acquired.
    """
    g = copy.deepcopy(genome)
    n = len(g.accounts.source_ages_days) or 3

    g.accounts.geographic_spread = random.sample(CITIES, min(n, len(CITIES)))
    g.accounts.cross_city = True
    g.accounts.device_diversity = True  # different cities = different devices
    g.accounts.ip_diversity = True
    g.mutation_history.append("geographic_spread")
    return g
