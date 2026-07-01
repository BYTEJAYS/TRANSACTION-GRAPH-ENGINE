from __future__ import annotations
import copy
import random
import logging

from red_team.core.genome import FraudGenome
from red_team.core.rail_constraints import RailConstraintViolation

logger = logging.getLogger(__name__)

# RBI mandatory reporting thresholds
THRESHOLDS = [50_000, 200_000, 1_000_000]
# Stay 8% below (not 1%) — Blue Team's threshold_proximity flag checks near-threshold clustering
SAFE_MARGIN = 0.08


def just_under_threshold(genome: FraudGenome) -> FraudGenome:
    """
    Classic structuring uses 1% below threshold — Blue Team detects that proximity.
    Staying 8% below avoids BOTH the threshold reporting AND the proximity detection flag.
    Multiple thresholds checked: ₹50k, ₹2L, ₹10L — no amount sits close to any of them.
    """
    g = copy.deepcopy(genome)
    new_values = []
    for amount in g.amounts.values:
        for threshold in THRESHOLDS:
            if amount * (1 + SAFE_MARGIN) > threshold:
                amount = threshold * (1 - SAFE_MARGIN)
                break
        new_values.append(round(max(1.0, amount), 2))

    g.amounts.values = new_values
    g.amounts.just_under_threshold = True
    g.mutation_history.append("just_under_threshold")
    return g


def amount_noise(genome: FraudGenome) -> FraudGenome:
    """
    Equal amounts (₹10k, ₹10k, ₹10k) trigger Blue Team's uniformity check in the
    bipartite gate and merchant terminal gate. Adding organic noise breaks uniformity
    while keeping the total value approximately constant — the money still moves,
    but the pattern looks like humans transacting, not a script.
    """
    if not genome.amounts.values:
        raise RailConstraintViolation("No amounts to add noise to")

    g = copy.deepcopy(genome)
    noise_pct = random.uniform(0.02, 0.08)

    g.amounts.values = [
        max(1.0, round(v * (1 + random.uniform(-noise_pct, noise_pct)), 2))
        for v in g.amounts.values
    ]
    g.amounts.pattern = "organic_noisy"
    g.amounts.noise_percent = noise_pct
    g.amounts.round_number_avoidance = True
    g.mutation_history.append("amount_noise")
    return g


def pyramid_amounts(genome: FraudGenome) -> FraudGenome:
    """
    Monotonically decreasing amounts mimic a series of purchases (spend and taper off)
    or increasing amounts mimic accumulation toward a goal — both are recognizable
    human spending patterns. Neither pattern triggers uniformity gates, and both
    have a plausible cover story that an investigator would find convincing.
    """
    if not genome.amounts.values:
        raise RailConstraintViolation("No amounts to pyramid")

    g = copy.deepcopy(genome)
    direction = random.choice(["decreasing", "increasing"])
    total = g.amounts.total
    n = len(g.amounts.values)

    if direction == "decreasing":
        weights = [n - i for i in range(n)]
    else:
        weights = [i + 1 for i in range(n)]

    weight_sum = sum(weights)
    g.amounts.values = [
        round(max(1.0, total * w / weight_sum), 2) for w in weights
    ]
    g.amounts.pattern = direction
    g.mutation_history.append("pyramid_amounts")
    return g
