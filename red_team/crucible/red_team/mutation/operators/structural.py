from __future__ import annotations
import copy
import random
import logging

from red_team.core.genome import FraudGenome
from red_team.core.rail_constraints import RailConstraintViolation

logger = logging.getLogger(__name__)

COVER_STORIES = [
    "rent_payment", "business_invoice", "family_gift",
    "loan_repayment", "investment_return", "freelance_payment",
]

LEGITIMATE_PATTERNS = {
    "salary_advance": {
        "topology": "fan_out",
        "timing": "month_start",
        "amount_range": (5_000, 50_000),
        "description": "employer_to_employees",
    },
    "b2b_invoice": {
        "topology": "fan_out",
        "timing": "month_end",
        "amount_range": (10_000, 200_000),
        "description": "business_invoice_settlement",
    },
    "family_remittance": {
        "topology": "fan_in",
        "timing": "festival",
        "amount_range": (2_000, 50_000),
        "description": "family_festival_transfer",
    },
}

CASH_OUT_METHODS = [
    "delayed_14d",       # withdraw 14+ days later — breaks 48h window in cash_mule_sink_gate
    "pos_goods_resale",  # buy goods via POS then sell for cash
    "wallet_hop",        # bank → Paytm wallet → cash (breaks direct trail)
    "gold_purchase",     # physical, portable, liquid
]


def recognized_pattern_verification(genome: FraudGenome) -> FraudGenome:
    """
    DANGER: Directly exploits Blue Team's legitimacy filter whitelist.
    Blue Team checks 5 legitimacy filters on the cycle gate — if a pattern matches
    one of them (salary advance, B2B, family), it SUPPRESSES the alert.
    This operator makes the fraud graph look exactly like one of those whitelisted patterns.
    Requires SENIOR INVESTIGATOR review — never auto-approve.
    """
    g = copy.deepcopy(genome)
    pattern_name = random.choice(list(LEGITIMATE_PATTERNS))
    pattern = LEGITIMATE_PATTERNS[pattern_name]

    g.topology.mimics_legitimate = pattern["description"]
    g.topology.type = pattern["topology"]

    # Adjust amounts to match typical range for this pattern
    lo, hi = pattern["amount_range"]
    g.amounts.values = [
        round(random.uniform(lo, hi), 2)
        for _ in range(max(1, len(g.amounts.values)))
    ]
    g.timing.time_of_day = pattern["timing"]

    g.flags.append("REQUIRES_SENIOR_REVIEW")
    g.mutation_history.append("recognized_pattern_verification:HIGH_DANGER")
    logger.warning(
        "recognized_pattern_verification applied — REQUIRES SENIOR REVIEW",
        genome_id=g.genome_id,
        pattern=pattern_name,
    )
    return g


def cash_out_disguise(genome: FraudGenome) -> FraudGenome:
    """
    Blue Team's cash_mule_sink_gate fires on: receive → ATM withdrawal >80% in 48h → digital silence.
    This operator breaks all three signals:
    - delayed_14d: withdrawal is outside the 48h window
    - pos_goods_resale: no ATM withdrawal, withdrawal via POS looks like purchase
    - wallet_hop: adds a non-ATM intermediary hop that breaks the direct trail
    - gold_purchase: untraceable physical asset conversion
    """
    g = copy.deepcopy(genome)
    method = random.choice(CASH_OUT_METHODS)
    g.special_nodes.cash_out_method = method
    g.special_nodes.cash_out_delay_days = random.randint(14, 60)

    # wallet_hop adds a topology layer to model the bank → wallet step
    if method == "wallet_hop":
        if g.topology.depth < 8:
            g.topology.depth += 1
        g.special_nodes.bridge_nodes["count"] = g.special_nodes.bridge_nodes.get("count", 0) + 1

    g.mutation_history.append("cash_out_disguise")
    return g


def layered_mixing(genome: FraudGenome) -> FraudGenome:
    """
    Blue Team's fund trail reconstruction traces 4-6 hops. At 7+ layers with cover stories,
    the SHAP explainer attributes each hop to a different "legitimate" reason — rent payment,
    B2B invoice, family gift — making the overall chain invisible as a unified fraud pattern.
    This is trade-based money laundering replicated in digital form.
    """
    g = copy.deepcopy(genome)
    num_layers = random.randint(3, 6)
    g.topology.layers = [
        {
            "layer": i,
            "cover_story": COVER_STORIES[i % len(COVER_STORIES)],
            "hold_days": random.choice([0, 1, 3, 7]),
            "partial_forward": random.random() > 0.5,
            "forward_percent": round(random.uniform(0.88, 1.0), 3),
        }
        for i in range(num_layers)
    ]
    g.topology.depth = num_layers + 2
    g.topology.type = "layered"
    g.mutation_history.append("layered_mixing")
    return g
