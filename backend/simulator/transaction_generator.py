"""
Synthetic transaction generator that simulates realistic and fraudulent
financial transaction patterns across UPI, IMPS, RTGS, and NEFT rails.
"""

import asyncio
import random
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Callable, Awaitable
from faker import Faker

from models.transaction import (
    Transaction, FraudPattern, PaymentRail, AccountType
)
from config import settings

fake = Faker("en_IN")


# ── Payment rail constraints ──────────────────────────────────────────────────

RAIL_CONFIG: Dict[str, Dict] = {
    PaymentRail.UPI: {
        "min_amount": 1,
        "max_amount": 100_000,
        "typical_range": (100, 10_000),
        "freq_weight": 0.55,
    },
    PaymentRail.IMPS: {
        "min_amount": 1,
        "max_amount": 500_000,
        "typical_range": (1_000, 50_000),
        "freq_weight": 0.25,
    },
    PaymentRail.NEFT: {
        "min_amount": 1,
        "max_amount": 10_000_000,
        "typical_range": (10_000, 500_000),
        "freq_weight": 0.12,
    },
    PaymentRail.RTGS: {
        "min_amount": 200_000,
        "max_amount": 100_000_000,
        "typical_range": (200_000, 2_000_000),
        "freq_weight": 0.08,
    },
}

INDIAN_CITIES = [
    "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai",
    "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Surat",
    "Lucknow", "Kanpur", "Nagpur", "Bhopal", "Indore",
]

DEVICE_TYPES = ["mobile_android", "mobile_ios", "web_browser", "desktop_app", "api_client"]


def _pick_rail() -> PaymentRail:
    rails = list(RAIL_CONFIG.keys())
    weights = [RAIL_CONFIG[r]["freq_weight"] for r in rails]
    return random.choices(rails, weights=weights, k=1)[0]


def _random_amount(rail: PaymentRail, anomalous: bool = False) -> float:
    cfg = RAIL_CONFIG[rail]
    if anomalous:
        # Structuring: just below round detection thresholds
        thresholds = [9999, 49999, 199999]
        base = random.choice(thresholds)
        return round(base - random.uniform(1, 500), 2)
    lo, hi = cfg["typical_range"]
    return round(random.triangular(lo, hi, (lo + hi) / 3), 2)


def _fake_ip() -> str:
    return f"{random.randint(1,254)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


def _fake_geo() -> str:
    city = random.choice(INDIAN_CITIES)
    lat = round(random.uniform(8.0, 37.0), 4)
    lon = round(random.uniform(68.0, 97.0), 4)
    return f"{city},{lat},{lon}"


def _fake_device() -> str:
    return f"{random.choice(DEVICE_TYPES)}-{uuid.uuid4().hex[:8]}"


# ── Account Pool ──────────────────────────────────────────────────────────────

class AccountPool:
    """Manages a pool of synthetic accounts with varying risk profiles."""

    def __init__(self):
        self.accounts: Dict[str, Dict] = {}
        self._init_accounts()

    def _init_accounts(self):
        # Normal accounts
        for _ in range(settings.NORMAL_ACCOUNTS):
            aid = f"ACC-{uuid.uuid4().hex[:8].upper()}"
            self.accounts[aid] = {
                "id": aid,
                "type": AccountType.NORMAL,
                "home_city": random.choice(INDIAN_CITIES),
                "typical_amount_range": (500, 20_000),
                "device": _fake_device(),
                "ip": _fake_ip(),
            }

        # Mule accounts (money laundering intermediaries)
        for _ in range(settings.MULE_ACCOUNTS):
            aid = f"MUL-{uuid.uuid4().hex[:8].upper()}"
            self.accounts[aid] = {
                "id": aid,
                "type": AccountType.MULE,
                "home_city": random.choice(INDIAN_CITIES),
                "typical_amount_range": (5_000, 100_000),
                "device": _fake_device(),
                "ip": _fake_ip(),
            }

        # High-value accounts
        for _ in range(settings.HIGH_RISK_ACCOUNTS):
            aid = f"HVA-{uuid.uuid4().hex[:8].upper()}"
            self.accounts[aid] = {
                "id": aid,
                "type": AccountType.HIGH_VALUE,
                "home_city": random.choice(INDIAN_CITIES),
                "typical_amount_range": (100_000, 5_000_000),
                "device": _fake_device(),
                "ip": _fake_ip(),
            }

    def random_account(self, account_type: Optional[AccountType] = None) -> str:
        pool = [
            aid for aid, info in self.accounts.items()
            if account_type is None or info["type"] == account_type
        ]
        return random.choice(pool) if pool else random.choice(list(self.accounts.keys()))

    def mule_accounts(self) -> List[str]:
        return [aid for aid, info in self.accounts.items() if info["type"] == AccountType.MULE]

    def normal_accounts(self) -> List[str]:
        return [aid for aid, info in self.accounts.items() if info["type"] == AccountType.NORMAL]

    def get_info(self, account_id: str) -> Dict:
        return self.accounts.get(account_id, {})


# ── Transaction Generator ─────────────────────────────────────────────────────

class TransactionGenerator:
    """
    Generates synthetic transactions including normal payments and
    a variety of fraud patterns for training and demo purposes.
    """

    def __init__(self, pool: Optional[AccountPool] = None):
        self.pool = pool or AccountPool()
        self._callbacks: List[Callable[[Transaction], Awaitable[None]]] = []
        self._running = False
        self._burst_until: float = 0.0
        self._forced_pattern: Optional[FraudPattern] = None

    def on_transaction(self, callback: Callable[[Transaction], Awaitable[None]]):
        self._callbacks.append(callback)

    async def _emit(self, txn: Transaction):
        for cb in self._callbacks:
            await cb(txn)

    # ── Pattern generators ────────────────────────────────────────────────────

    def _build_txn(
        self,
        from_acc: str,
        to_acc: str,
        amount: float,
        rail: PaymentRail,
        risk_score: float,
        pattern: FraudPattern,
        metadata: Optional[Dict] = None,
    ) -> Transaction:
        acc_info = self.pool.get_info(from_acc)
        city = acc_info.get("home_city", random.choice(INDIAN_CITIES))
        # Occasionally change IP/geo to indicate suspicious location change
        geo = _fake_geo() if random.random() < 0.2 else f"{city},{round(random.uniform(8,37),4)},{round(random.uniform(68,97),4)}"
        return Transaction(
            from_account=from_acc,
            to_account=to_acc,
            amount=amount,
            payment_rail=rail,
            device_id=acc_info.get("device", _fake_device()),
            ip_address=acc_info.get("ip", _fake_ip()),
            geo_location=geo,
            risk_score=min(1.0, max(0.0, risk_score)),
            fraud_pattern=pattern,
            metadata=metadata or {},
        )

    def generate_normal(self) -> Transaction:
        src = self.pool.random_account(AccountType.NORMAL)
        dst = self.pool.random_account()
        while dst == src:
            dst = self.pool.random_account()
        rail = _pick_rail()
        amount = _random_amount(rail)
        risk = random.uniform(0.0, 0.25)
        return self._build_txn(src, dst, amount, rail, risk, FraudPattern.NORMAL)

    def generate_circular_transfer(self, depth: int = 3) -> List[Transaction]:
        """A→B→C→...→A: funds return to origin after n hops."""
        mules = self.pool.mule_accounts()
        if len(mules) < depth:
            mules = list(self.pool.accounts.keys())
        ring = random.sample(mules, min(depth, len(mules)))
        ring.append(ring[0])  # close the loop

        amount = round(random.uniform(10_000, 500_000), 2)
        rail = random.choice([PaymentRail.UPI, PaymentRail.IMPS])
        txns = []
        risk = random.uniform(0.75, 0.97)

        for i in range(len(ring) - 1):
            # Slight amount decay to disguise the loop
            hop_amount = round(amount * random.uniform(0.92, 1.0), 2)
            txn = self._build_txn(
                ring[i], ring[i + 1], hop_amount, rail, risk, FraudPattern.CIRCULAR,
                metadata={"ring_depth": depth, "hop": i},
            )
            txns.append(txn)
        return txns

    def generate_fan_out(self, recipients: int = 7) -> List[Transaction]:
        """One account rapidly sends to N distinct accounts (smurfing)."""
        src = self.pool.random_account(AccountType.MULE)
        targets = random.sample(
            [a for a in self.pool.accounts if a != src],
            min(recipients, len(self.pool.accounts) - 1),
        )
        total = random.uniform(50_000, 2_000_000)
        rail = PaymentRail.UPI
        risk = random.uniform(0.70, 0.95)
        txns = []
        for t in targets:
            share = round(total / recipients * random.uniform(0.8, 1.2), 2)
            txn = self._build_txn(
                src, t, share, rail, risk, FraudPattern.FAN_OUT,
                metadata={"fan_out_degree": recipients},
            )
            txns.append(txn)
        return txns

    def generate_layering(self) -> List[Transaction]:
        """Split a large amount across multiple hops, then consolidate."""
        layers = random.randint(2, 4)
        split_factor = random.randint(2, 5)
        origin = self.pool.random_account(AccountType.HIGH_VALUE)
        amount = random.uniform(500_000, 10_000_000)
        rail = PaymentRail.RTGS
        risk = random.uniform(0.78, 0.96)

        intermediaries = random.sample(self.pool.mule_accounts(), min(layers * split_factor, len(self.pool.mule_accounts())))
        final_dest = self.pool.random_account(AccountType.NORMAL)
        txns = []

        # Layer 1: split from origin
        chunk = amount / split_factor
        for i in range(split_factor):
            if i < len(intermediaries):
                txn = self._build_txn(
                    origin, intermediaries[i], round(chunk, 2),
                    rail, risk, FraudPattern.LAYERING,
                    metadata={"layer": 1, "split": split_factor},
                )
                txns.append(txn)

        # Layer 2+: route through additional hops
        for layer in range(1, layers):
            for i in range(min(split_factor, len(intermediaries) - split_factor * layer)):
                src_idx = split_factor * (layer - 1) + i
                dst_idx = split_factor * layer + i
                if dst_idx < len(intermediaries):
                    txn = self._build_txn(
                        intermediaries[src_idx], intermediaries[dst_idx],
                        round(chunk * random.uniform(0.9, 1.0), 2),
                        PaymentRail.IMPS, risk, FraudPattern.LAYERING,
                        metadata={"layer": layer + 1},
                    )
                    txns.append(txn)

        # Final consolidation
        for i in range(split_factor):
            idx = split_factor * (layers - 1) + i
            if idx < len(intermediaries):
                txn = self._build_txn(
                    intermediaries[idx], final_dest,
                    round(chunk * random.uniform(0.85, 0.98), 2),
                    PaymentRail.NEFT, risk, FraudPattern.LAYERING,
                    metadata={"layer": "consolidation"},
                )
                txns.append(txn)

        return txns

    def generate_rapid_microtransactions(self, count: int = 12) -> List[Transaction]:
        """Many tiny transactions in rapid succession — velocity abuse."""
        src = self.pool.random_account()
        dst = self.pool.random_account()
        while dst == src:
            dst = self.pool.random_account()
        risk = random.uniform(0.60, 0.85)
        txns = []
        for _ in range(count):
            amount = round(random.uniform(1, 999), 2)
            txn = self._build_txn(
                src, dst, amount, PaymentRail.UPI, risk, FraudPattern.RAPID_MICRO,
                metadata={"micro_burst_size": count},
            )
            txns.append(txn)
        return txns

    def generate_mule_chain(self, hops: int = 4) -> List[Transaction]:
        """Linear chain through mule accounts: src→M1→M2→M3→dest."""
        mules = random.sample(self.pool.mule_accounts(), min(hops, len(self.pool.mule_accounts())))
        origin = self.pool.random_account(AccountType.HIGH_VALUE)
        final = self.pool.random_account(AccountType.NORMAL)
        chain = [origin] + mules + [final]

        amount = random.uniform(100_000, 5_000_000)
        risk = random.uniform(0.72, 0.94)
        txns = []

        for i in range(len(chain) - 1):
            rail = random.choice([PaymentRail.IMPS, PaymentRail.UPI])
            txn = self._build_txn(
                chain[i], chain[i + 1],
                round(amount * random.uniform(0.93, 1.0), 2),
                rail, risk, FraudPattern.MULE_CHAIN,
                metadata={"chain_length": len(chain), "hop": i},
            )
            txns.append(txn)
        return txns

    def generate_structuring(self, count: int = 5) -> List[Transaction]:
        """Break large amount into sub-threshold chunks — classic structuring."""
        src = self.pool.random_account()
        dst = self.pool.random_account()
        risk = random.uniform(0.65, 0.90)
        txns = []
        for _ in range(count):
            rail = random.choice([PaymentRail.UPI, PaymentRail.IMPS])
            amount = _random_amount(rail, anomalous=True)
            txn = self._build_txn(
                src, dst, amount, rail, risk, FraudPattern.STRUCTURING,
                metadata={"structuring_batch": count},
            )
            txns.append(txn)
        return txns

    # ── Main simulation loop ──────────────────────────────────────────────────

    def trigger_burst(self, duration_seconds: float = 5.0):
        import time
        self._burst_until = time.time() + duration_seconds

    def inject_fraud(self, pattern: FraudPattern):
        self._forced_pattern = pattern

    async def run(self, rate_override: Optional[float] = None):
        """Continuously emit transactions; mix normal and fraud patterns."""
        import time
        self._running = True
        base_rate = rate_override or settings.SIMULATION_RATE

        while self._running:
            import time as _time
            is_burst = _time.time() < self._burst_until
            rate = base_rate * (settings.SIMULATION_BURST_MULTIPLIER if is_burst else 1.0)

            pattern = self._forced_pattern
            self._forced_pattern = None  # consume single injection

            txns: List[Transaction] = []

            if pattern:
                txns = self._dispatch_pattern(pattern)
            elif random.random() < settings.SIMULATION_FRAUD_PROBABILITY:
                # Randomly inject a fraud pattern
                chosen = random.choice([
                    FraudPattern.CIRCULAR,
                    FraudPattern.FAN_OUT,
                    FraudPattern.LAYERING,
                    FraudPattern.RAPID_MICRO,
                    FraudPattern.MULE_CHAIN,
                    FraudPattern.STRUCTURING,
                ])
                txns = self._dispatch_pattern(chosen)
            else:
                txns = [self.generate_normal()]

            for txn in txns:
                await self._emit(txn)
                # Small stagger between burst transactions
                if len(txns) > 1:
                    await asyncio.sleep(random.uniform(0.01, 0.08))

            # Throttle to target rate
            sleep_time = max(0.05, 1.0 / rate)
            await asyncio.sleep(sleep_time)

    def _dispatch_pattern(self, pattern: FraudPattern) -> List[Transaction]:
        dispatch = {
            FraudPattern.CIRCULAR: lambda: self.generate_circular_transfer(random.randint(3, 5)),
            FraudPattern.FAN_OUT: lambda: self.generate_fan_out(random.randint(5, 10)),
            FraudPattern.LAYERING: self.generate_layering,
            FraudPattern.RAPID_MICRO: lambda: self.generate_rapid_microtransactions(random.randint(8, 15)),
            FraudPattern.MULE_CHAIN: lambda: self.generate_mule_chain(random.randint(3, 6)),
            FraudPattern.STRUCTURING: lambda: self.generate_structuring(random.randint(4, 8)),
            FraudPattern.NORMAL: lambda: [self.generate_normal()],
        }
        return dispatch.get(pattern, lambda: [self.generate_normal()])()

    def stop(self):
        self._running = False
