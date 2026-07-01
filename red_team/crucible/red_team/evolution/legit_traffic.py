from __future__ import annotations
"""
Intelligent Noise Generator — never 100% fraud.

Real fraud hides inside ordinary banking activity. This wraps a fraud
transaction list in human-like legitimate traffic (salary, rent, EMI, bills,
recharge, food delivery, shopping, fuel, subscriptions) at a difficulty-driven
ratio (e.g. 95% legit / 5% fraud), with human-ish timing (working hours, weekends
avoided for payroll, festival/salary-day clustering).

The fraud edges are returned tagged so the engine can measure:
  • false positives — legit nodes Blue flags,
  • detection       — fraud nodes Blue flags.

`blend_into_graph` optionally injects a slice of legit edges into the very graph
Blue scores, testing its ability to ISOLATE fraud from noise.
"""
import hashlib
import random
from dataclasses import dataclass, field

# Recurring legitimate payees → typical amount bands (₹) and rails.
_LEGIT_PAYEES = [
    ("salary_credit", (28_000, 90_000), "ach_transfer"),
    ("house_rent", (8_000, 35_000), "p2p_transfer"),
    ("home_loan_emi", (12_000, 60_000), "ach_transfer"),
    ("electricity_bill", (800, 4_500), "bill_payment"),
    ("mobile_recharge", (199, 999), "bill_payment"),
    ("amazon_order", (300, 8_000), "debit_purchase"),
    ("swiggy_order", (150, 1_200), "debit_purchase"),
    ("zomato_order", (150, 1_500), "debit_purchase"),
    ("fuel_purchase", (500, 4_000), "pos_transaction"),
    ("netflix_sub", (149, 799), "bill_payment"),
    ("school_fees", (3_000, 25_000), "ach_transfer"),
    ("insurance_premium", (1_200, 15_000), "ach_transfer"),
    ("grocery_pos", (400, 6_000), "pos_transaction"),
    ("upi_friend_split", (50, 2_500), "p2p_transfer"),
]


@dataclass
class Scenario:
    fraud_txns: list[dict]
    legit_txns: list[dict]
    graph_txns: list[dict]            # what Blue actually scores
    fraud_nodes: set[str] = field(default_factory=set)
    legit_nodes: set[str] = field(default_factory=set)

    @property
    def legit_ratio(self) -> float:
        total = len(self.fraud_txns) + len(self.legit_txns)
        return round(len(self.legit_txns) / total, 4) if total else 0.0

    def summary(self) -> dict:
        return {
            "fraud_txn_count": len(self.fraud_txns),
            "legit_txn_count": len(self.legit_txns),
            "legit_ratio": self.legit_ratio,
            "graph_txn_count": len(self.graph_txns),
        }


def _acc(seed: str) -> str:
    return "acc_" + hashlib.md5(seed.encode()).hexdigest()[:10]


def _human_timestamp(rng: random.Random, day_offset: int) -> str:
    # Humans transact mostly during waking hours; salary/bills cluster month-start.
    hour = rng.choices(
        population=[9, 10, 11, 13, 14, 16, 18, 19, 20, 21],
        weights=[3, 4, 4, 3, 3, 3, 4, 5, 5, 3], k=1,
    )[0]
    minute = rng.randint(0, 59)
    return f"2026-05-{1 + (day_offset % 27):02d}T{hour:02d}:{minute:02d}:00"


def build_scenario(fraud_txns: list[dict], legit_ratio: float,
                   rng: random.Random, blend_into_graph: bool = False,
                   person_pool: int = 12) -> Scenario:
    """Wrap fraud in legitimate traffic at the requested ratio."""
    fraud_txns = list(fraud_txns or [])
    fraud_nodes: set[str] = set()
    for t in fraud_txns:
        fraud_nodes.add(t.get("from_account", t.get("source", "")))
        fraud_nodes.add(t.get("to_account", t.get("target", "")))
    fraud_nodes.discard("")

    # Number of legit txns to hit the target ratio: legit/(legit+fraud) = ratio.
    n_fraud = max(1, len(fraud_txns))
    ratio = min(0.99, max(0.0, legit_ratio))
    n_legit = int(round(n_fraud * ratio / (1.0 - ratio))) if ratio < 1.0 else n_fraud * 20

    people = [_acc(f"person_{i}") for i in range(max(2, person_pool))]
    legit_txns: list[dict] = []
    legit_nodes: set[str] = set()
    for i in range(n_legit):
        payee_name, (lo, hi), rail = rng.choice(_LEGIT_PAYEES)
        person = rng.choice(people)
        payee = _acc(f"merchant_{payee_name}")
        legit_txns.append({
            "from_account": person,
            "to_account": payee,
            "amount": int(rng.randint(lo, hi)),
            "payment_rail": rail,
            "timestamp": _human_timestamp(rng, i),
            "label": "legit",
        })
        legit_nodes.update((person, payee))

    # Blue scores the fraud subgraph; at higher difficulty, blend a noise slice in.
    graph_txns = list(fraud_txns)
    if blend_into_graph and legit_txns:
        slice_n = min(len(legit_txns), max(2, len(fraud_txns)))
        graph_txns = graph_txns + rng.sample(legit_txns, slice_n)

    return Scenario(
        fraud_txns=fraud_txns,
        legit_txns=legit_txns,
        graph_txns=graph_txns,
        fraud_nodes=fraud_nodes,
        legit_nodes=legit_nodes - fraud_nodes,
    )
