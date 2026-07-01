from __future__ import annotations
import copy
import random
import logging

from red_team.core.genome import FraudGenome
from red_team.core.rail_constraints import RailConstraintViolation

logger = logging.getLogger(__name__)

# Diwali 2026 is October 20. FESTIVALS ordered by score reduction effectiveness.
FESTIVALS = [
    {
        "name": "diwali",
        "month": 10,
        "day_range": (15, 25),
        "score_reduction": 0.30,
        "amount_max": 4_999,
        "description": "Diwali gifting — Blue Team reduces score 30% for small gifts in Oct-Nov",
    },
    {
        "name": "dhanteras",
        "month": 10,
        "day_range": (13, 16),
        "score_reduction": 0.30,
        "amount_max": 4_999,
        "description": "Dhanteras wealth gifts",
    },
    {
        "name": "eid",
        "month": 4,
        "day_range": (1, 10),
        "score_reduction": 0.25,
        "amount_max": 4_999,
        "description": "Eid Eidi transfers",
    },
]


def time_dilation(genome: FraudGenome) -> FraudGenome:
    """
    Blue Team's velocity checks operate on 1h, 24h, 7-day, 30-day rolling windows.
    Stretching transaction spacing beyond 30 days means at most 1 transaction appears
    in any monitoring window — velocity reads as near-zero, no spike possible.
    """
    if not genome.timing.spacing_days:
        raise RailConstraintViolation("No spacing_days to dilate")

    g = copy.deepcopy(genome)
    dilation = random.uniform(1.5, 5.0)
    g.timing.spacing_days = [round(d * dilation, 2) for d in g.timing.spacing_days]
    g.timing.low_slow = True
    g.mutation_history.append("time_dilation")
    return g


def add_dormancy_period(genome: FraudGenome) -> FraudGenome:
    """
    Blue Team's sequence detection tracks patterns over time windows (30-day default).
    A dormancy gap > 30 days splits the transaction sequence into two disjoint windows —
    the pre-dormancy and post-dormancy segments never co-appear in the same window.
    Also prevents "abandoned sink" detection: dormant then active again ≠ abandoned.
    KYC re-verification triggers after 12 months inactivity — keep dormancy < 365 days.
    """
    if not genome.timing.spacing_days:
        raise RailConstraintViolation("No transactions to insert dormancy between")

    g = copy.deepcopy(genome)
    dormancy_start = random.randint(1, max(1, len(g.timing.spacing_days) - 1))
    duration = random.choice([30, 45, 60, 90])

    g.timing.dormancy_periods.append({
        "after_transaction": dormancy_start,
        "duration_days": duration,
    })
    g.mutation_history.append("add_dormancy_period")
    return g


def jitter_timing(genome: FraudGenome) -> FraudGenome:
    """
    Perfectly regular intervals (2.0, 2.0, 2.0) are themselves a hard signal —
    Blue Team's amount_series_score detects mechanical regularity.
    Human beings are irregular. Jitter makes the pattern look organic and hand-driven.
    """
    if not genome.timing.spacing_days:
        raise RailConstraintViolation("No spacing_days to jitter")

    g = copy.deepcopy(genome)
    jitter_pct = random.uniform(0.15, 0.35)
    g.timing.spacing_days = [
        max(0.5, round(d * (1 + random.uniform(-jitter_pct, jitter_pct)), 2))
        for d in g.timing.spacing_days
    ]
    g.timing.jitter = jitter_pct
    g.mutation_history.append("jitter_timing")
    return g


def festival_timing(genome: FraudGenome) -> FraudGenome:
    """
    Blue Team's Indian context adjuster multiplies fraud score by 0.70 during Oct-Nov
    (Diwali season) for transactions < ₹5,000 with has_festival_gifting_history=True.
    A score of 0.75 normal → 0.525 during festival = below REVIEW threshold.
    Amounts are capped to the festival maximum to guarantee the reduction fires.
    """
    g = copy.deepcopy(genome)
    festival = random.choice(FESTIVALS)
    g.timing.festival_timing = festival
    g.timing.festival_name = festival["name"]
    g.timing.time_of_day = "afternoon"  # 1pm-5pm — business hours, not suspicious

    # Cap all amounts to just below the festival adjuster's threshold (< ₹5k)
    max_amt = festival["amount_max"]
    g.amounts.values = [
        round(min(v, max_amt) * random.uniform(0.85, 0.99), 2)
        for v in g.amounts.values
    ]
    # Ensure at least ₹1,000 (meaningful transfer)
    g.amounts.values = [max(1_000.0, v) for v in g.amounts.values]

    g.mutation_history.append("festival_timing")
    return g
