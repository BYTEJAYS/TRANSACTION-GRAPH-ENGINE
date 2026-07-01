"""
Transaction pattern generator.

Produces synthetic transaction graphs that *resemble* normal and high-risk
financial behaviour at adjustable complexity. Output is a list of
:class:`SyntheticTransaction` objects plus an optional ``networkx`` view for
graph analytics.

Every transaction is synthetic and labelled with its ground-truth
``fraud_category`` for research evaluation. These generators model the
*shape* of money movement (topology, timing, amount dispersion) — they contain
no guidance for executing real transactions on any real payment network.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from red_team.core.config import RedTeamConfig, config as default_config
from red_team.core.models import (
    AccountArchetype,
    FraudCategory,
    PaymentRail,
    Provenance,
    SyntheticAccount,
    SyntheticTransaction,
)

# Sub-reporting-threshold band used to model structuring (abstract numbers).
_STRUCTURING_THRESHOLDS = [9_999, 49_999, 199_999]


class TransactionPatternGenerator:
    """Builds labelled synthetic transaction graphs at adjustable complexity."""

    def __init__(
        self,
        accounts: List[SyntheticAccount],
        cfg: Optional[RedTeamConfig] = None,
        seed: Optional[int] = None,
    ):
        if not accounts:
            raise ValueError("TransactionPatternGenerator requires a non-empty account list.")
        self.cfg = cfg or default_config
        self.accounts = accounts
        self.seed = seed if seed is not None else self.cfg.seed
        self._rng = random.Random(self.seed)
        self._t0 = datetime.now(timezone.utc)
        self._step = 0

        self._by_arch = {}
        for acc in accounts:
            self._by_arch.setdefault(acc.archetype, []).append(acc)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _pick(self, archetype: Optional[AccountArchetype] = None) -> SyntheticAccount:
        pool = self._by_arch.get(archetype) if archetype else None
        if not pool:
            pool = self.accounts
        return self._rng.choice(pool)

    def _mules(self, n: int) -> List[SyntheticAccount]:
        pool = self._by_arch.get(AccountArchetype.MULE, []) or self.accounts
        return self._rng.sample(pool, min(n, len(pool)))

    def _ts(self, spread_seconds: float = 30.0) -> datetime:
        self._step += 1
        jitter = self._rng.uniform(0, spread_seconds)
        return self._t0 + timedelta(seconds=self._step * spread_seconds + jitter)

    def _txn(
        self,
        src: SyntheticAccount,
        dst: SyntheticAccount,
        amount: float,
        rail: PaymentRail,
        category: FraudCategory,
        is_fraud: bool,
        **metadata,
    ) -> SyntheticTransaction:
        device = f"DEV-{src.account_id[-6:]}"
        geo = f"{src.home_city}"
        return SyntheticTransaction(
            from_account=src.account_id,
            to_account=dst.account_id,
            amount=round(amount, 2),
            timestamp=self._ts(),
            payment_rail=rail,
            device_id=device,
            geo_location=geo,
            fraud_category=category,
            is_fraud=is_fraud,
            scenario_step=self._step,
            metadata=metadata,
            provenance=Provenance(seed=self.seed),
        )

    # ── Benign baseline ───────────────────────────────────────────────────────

    def normal_activity(self, count: int = 50) -> List[SyntheticTransaction]:
        out = []
        for _ in range(count):
            src = self._pick()
            dst = self._pick()
            while dst.account_id == src.account_id:
                dst = self._pick()
            lo, hi = src.typical_amount_range
            amount = self._rng.triangular(lo, hi, (lo + hi) / 3)
            rail = self._rng.choices(
                [PaymentRail.UPI, PaymentRail.IMPS, PaymentRail.NEFT, PaymentRail.RTGS],
                weights=[0.6, 0.25, 0.1, 0.05],
            )[0]
            out.append(self._txn(src, dst, amount, rail, FraudCategory.NORMAL, False))
        return out

    # ── High-risk topologies ──────────────────────────────────────────────────

    def circular_flow(self, depth: int = 3) -> List[SyntheticTransaction]:
        """A -> B -> ... -> A. Funds return to origin after ``depth`` hops."""
        ring = self._mules(depth) or self._rng.sample(self.accounts, min(depth, len(self.accounts)))
        if len(ring) < 2:
            return []
        ring = ring + [ring[0]]
        amount = self._rng.uniform(50_000, 500_000)
        out = []
        for i in range(len(ring) - 1):
            hop = amount * self._rng.uniform(0.9, 1.0)  # slight decay disguises the loop
            out.append(
                self._txn(ring[i], ring[i + 1], hop, PaymentRail.IMPS,
                          FraudCategory.CIRCULAR_FLOW, True, ring_depth=depth, hop=i)
            )
        return out

    def smurfing_fan_out(self, recipients: int = 8) -> List[SyntheticTransaction]:
        """One source splits funds across many recipients (smurfing)."""
        src = self._pick(AccountArchetype.MULE)
        targets = self._rng.sample(
            [a for a in self.accounts if a.account_id != src.account_id],
            min(recipients, len(self.accounts) - 1),
        )
        total = self._rng.uniform(100_000, 2_000_000)
        out = []
        for t in targets:
            share = total / recipients * self._rng.uniform(0.8, 1.2)
            out.append(self._txn(src, t, share, PaymentRail.UPI,
                                 FraudCategory.SMURFING, True, fan_out_degree=recipients))
        return out

    def layering(self, layers: int = 3, split: int = 3) -> List[SyntheticTransaction]:
        """Split a large sum across hops, then reconsolidate (laundering layering)."""
        intermediaries = self._mules(layers * split)
        if len(intermediaries) < split:
            return self.smurfing_fan_out(split)
        origin = self._pick(AccountArchetype.HIGH_NET_WORTH)
        final = self._pick(AccountArchetype.RETAIL)
        amount = self._rng.uniform(500_000, 10_000_000)
        chunk = amount / split
        out: List[SyntheticTransaction] = []

        for i in range(split):
            out.append(self._txn(origin, intermediaries[i], chunk, PaymentRail.RTGS,
                                 FraudCategory.LAYERING, True, layer=1))
        for layer in range(1, layers):
            for i in range(split):
                s_idx = split * (layer - 1) + i
                d_idx = split * layer + i
                if d_idx < len(intermediaries):
                    out.append(self._txn(intermediaries[s_idx], intermediaries[d_idx],
                                         chunk * self._rng.uniform(0.9, 1.0), PaymentRail.IMPS,
                                         FraudCategory.LAYERING, True, layer=layer + 1))
        last = intermediaries[split * (layers - 1):split * layers] or intermediaries[-split:]
        for inter in last:
            out.append(self._txn(inter, final, chunk * self._rng.uniform(0.85, 0.98),
                                 PaymentRail.NEFT, FraudCategory.TRANSACTION_LAUNDERING, True,
                                 layer="consolidation"))
        return out

    def mule_chain(self, hops: int = 4) -> List[SyntheticTransaction]:
        """Linear hop chain through mule accounts: origin -> M1 -> ... -> dest."""
        mules = self._mules(hops)
        origin = self._pick(AccountArchetype.HIGH_NET_WORTH)
        final = self._pick(AccountArchetype.RETAIL)
        chain = [origin] + mules + [final]
        amount = self._rng.uniform(100_000, 5_000_000)
        out = []
        for i in range(len(chain) - 1):
            out.append(self._txn(chain[i], chain[i + 1], amount * self._rng.uniform(0.93, 1.0),
                                 self._rng.choice([PaymentRail.IMPS, PaymentRail.UPI]),
                                 FraudCategory.MULE_NETWORK, True, chain_len=len(chain), hop=i))
        return out

    def structuring(self, count: int = 6) -> List[SyntheticTransaction]:
        """Many sub-threshold transfers between a pair (structuring)."""
        src, dst = self._pick(), self._pick()
        while dst.account_id == src.account_id:
            dst = self._pick()
        out = []
        for _ in range(count):
            base = self._rng.choice(_STRUCTURING_THRESHOLDS)
            amount = base - self._rng.uniform(1, 500)
            out.append(self._txn(src, dst, amount, self._rng.choice([PaymentRail.UPI, PaymentRail.IMPS]),
                                 FraudCategory.STRUCTURING, True, batch=count))
        return out

    def account_takeover_burst(self, count: int = 10) -> List[SyntheticTransaction]:
        """Rapid drain from a single account to many recipients post-takeover."""
        victim = self._pick(AccountArchetype.SALARIED)
        out = []
        for _ in range(count):
            dst = self._pick()
            while dst.account_id == victim.account_id:
                dst = self._pick()
            lo, hi = victim.typical_amount_range
            amount = hi * self._rng.uniform(1.5, 4.0)  # abnormally large vs. baseline
            out.append(self._txn(victim, dst, amount, PaymentRail.UPI,
                                 FraudCategory.ACCOUNT_TAKEOVER, True, burst_size=count))
        return out

    # ── Graph view ────────────────────────────────────────────────────────────

    @staticmethod
    def to_networkx(transactions: List[SyntheticTransaction]):
        """Return a ``networkx.DiGraph`` aggregating transactions into edges."""
        import networkx as nx

        g = nx.DiGraph()
        for t in transactions:
            if g.has_edge(t.from_account, t.to_account):
                g[t.from_account][t.to_account]["amount"] += t.amount
                g[t.from_account][t.to_account]["count"] += 1
            else:
                g.add_edge(t.from_account, t.to_account, amount=t.amount, count=1,
                           fraud_category=t.fraud_category.value)
        return g
