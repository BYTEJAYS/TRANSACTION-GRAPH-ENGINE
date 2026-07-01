"""
Provenance / account-history signal — the discriminator V2's 16 factors lack.

§13 showed V2 (and a factor calibration) cannot separate laundering from legitimate
structured/high-value activity: payroll, merchant and corporate clusters are
structurally identical to distribution / collection / cash-out schemes, so any
structural or volume signal flags them too (≈57% benign false positives).

The signal that *does* separate them is not in the graph's shape at all — it is in
*who the counterparties are*. A bank knows its customers: an employer paying salaries
and its employees are KYC-established accounts with years of history. A laundering
ring runs on fresh synthetic / mule accounts with no verified history. This module
models that knowledge as a trusted registry the **attacker cannot write to** — it can
forge a node's `transaction_count` in the submitted graph, but it cannot mint a
KYC-verified identity in the bank's records.

Two properties make this robust where structural hardening failed:
  * it *reduces* false positives — legitimate clusters of established customers are
    vouched for regardless of how hub-like or high-value they look;
  * it is *immune to fragmentation* (B1) — splitting a scheme into singletons does
    not make fresh mules verified, so the unverified-value ratio stays ≈1 per
    fragment.

Known, intended limitation: an **account-takeover** scheme that routes through a
real customer's verified account defeats provenance (the unverified ratio drops).
That is the correct hard residual and the obvious next Red probe — it is not a flaw
in the signal but the precise boundary of what provenance can claim.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass


def build_customer_universe(n: int = 5000, seed: int = 2024) -> dict[str, float]:
    """The bank's KYC base: account_id → establishment score in [0,1].

    Establishment blends verified account age and prior legitimate transaction
    volume — both held in the bank's records, neither settable by the attacker.
    """
    rng = random.Random(seed)
    universe: dict[str, float] = {}
    for i in range(n):
        age_days = rng.randint(30, 2400)
        prior_txns = rng.randint(5, 3000)
        est = 0.45 * min(1.0, age_days / 365.0) + 0.55 * min(1.0, prior_txns / 200.0)
        universe[f"cust_{i:05d}"] = round(min(1.0, est), 4)
    return universe


@dataclass
class ProvenanceRegistry:
    """The trusted KYC/history store. Unknown accounts have establishment 0."""
    universe: dict[str, float]

    def establishment(self, account: object) -> float:
        return self.universe.get(str(account), 0.0)

    def customer_ids(self) -> list[str]:
        return list(self.universe.keys())


class ProvenanceScorer:
    """Turns counterparty establishment into a risk adjustment on a component."""

    def __init__(self, registry: ProvenanceRegistry,
                 attenuation_floor: float = 0.25, unverified_risk: float = 0.8) -> None:
        self.reg = registry
        self.attenuation_floor = attenuation_floor   # how much trusted clusters keep
        self.unverified_risk = unverified_risk         # risk floor for unverified value

    def unverified_value_ratio(self, component: dict) -> float:
        """Value-weighted fraction of flow whose BOTH ends are not fully established.

        A rupee is 'trusted' only to the degree both counterparties are KYC-known,
        so value moving between established customers counts as verified while value
        touching a fresh account counts as unverified.
        """
        total = 0.0
        unverified = 0.0
        for e in component.get("edges", []):
            amt = float(e.get("amount", 0) or 0)
            if amt <= 0:
                continue
            trust = min(self.reg.establishment(e.get("source")),
                        self.reg.establishment(e.get("target")))
            total += amt
            unverified += amt * (1.0 - trust)
        return (unverified / total) if total > 0 else 1.0

    def adjust(self, component: dict, native_risk: float) -> float:
        """Combine native structural risk with provenance.

        * trusted clusters (low unverified ratio) have their native risk attenuated
          toward ``attenuation_floor`` — this is what clears the legitimate
          payroll/corporate false positives;
        * unverified value imposes a risk floor — this is what catches fresh-account
          laundering even after it has evaded every structural gate, and survives
          fragmentation.
        """
        u = self.unverified_value_ratio(component)
        attenuated = native_risk * (self.attenuation_floor + (1 - self.attenuation_floor) * u)
        floor = self.unverified_risk * u
        return max(0.0, min(0.999, max(attenuated, floor)))
