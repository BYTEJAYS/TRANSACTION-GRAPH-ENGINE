"""
Python simulation of Apache Flink stream-processing semantics.

Implements sliding window aggregation, velocity analysis, fan-out
detection, burst detection, and real-time anomaly pre-scoring.
"""

import asyncio
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Callable, Awaitable, Optional, Tuple

from models.transaction import Transaction, FraudPattern, FraudAlert, RiskLevel
from config import settings

AlertCallback = Callable[[FraudAlert], Awaitable[None]]


# ── Sliding window ────────────────────────────────────────────────────────────

class SlidingWindow:
    """Fixed-duration sliding window keyed by account or global."""

    def __init__(self, window_seconds: int):
        self.window_seconds = window_seconds
        # account_id → deque of (timestamp, txn_dict)
        self._data: Dict[str, deque] = defaultdict(deque)

    def add(self, key: str, entry: dict):
        now = time.time()
        self._data[key].append((now, entry))
        self._evict(key, now)

    def _evict(self, key: str, now: float):
        cutoff = now - self.window_seconds
        q = self._data[key]
        while q and q[0][0] < cutoff:
            q.popleft()

    def get(self, key: str) -> List[dict]:
        now = time.time()
        self._evict(key, now)
        return [entry for _, entry in self._data[key]]

    def count(self, key: str) -> int:
        return len(self.get(key))

    def total_amount(self, key: str) -> float:
        return sum(e["amount"] for e in self.get(key))

    def unique_targets(self, key: str) -> int:
        return len({e["to_account"] for e in self.get(key)})

    def unique_sources(self, key: str) -> int:
        return len({e["from_account"] for e in self.get(key)})


# ── Flink-style Stream Processor ─────────────────────────────────────────────

class FlinkStreamProcessor:
    """
    Simulates Flink operator pipeline:
      Raw stream → filter → keyed windows → pattern detection → alert sink
    """

    def __init__(self):
        # 60-second velocity window
        self._velocity_window = SlidingWindow(settings.VELOCITY_WINDOW_SECONDS)
        # 10-minute fan-out window
        self._fanout_window = SlidingWindow(600)
        # 30-second burst window (global)
        self._burst_window = SlidingWindow(30)

        self._alert_callbacks: List[AlertCallback] = []
        self._processed_count: int = 0
        self._flagged_count: int = 0

        # Seen circular pairs to avoid duplicate alerts: (frozenset, hop_1)
        self._recent_circulars: deque = deque(maxlen=200)
        self._recent_fanouts: deque = deque(maxlen=100)

    def on_alert(self, callback: AlertCallback):
        self._alert_callbacks.append(callback)

    async def _fire_alert(self, alert: FraudAlert):
        for cb in self._alert_callbacks:
            await cb(alert)

    # ── Main entry point ──────────────────────────────────────────────────────

    async def process(self, txn: Transaction):
        """Process a single transaction through all window operators."""
        self._processed_count += 1
        txn_dict = txn.model_dump(mode="json")

        sender = txn.from_account
        self._velocity_window.add(sender, txn_dict)
        self._fanout_window.add(sender, txn_dict)
        self._burst_window.add("__global__", txn_dict)

        alerts = await asyncio.gather(
            self._check_velocity(txn),
            self._check_fanout(txn),
            self._check_burst(),
            self._check_pattern_flags(txn),
            return_exceptions=True,
        )

        fired = sum(1 for a in alerts if isinstance(a, FraudAlert))
        if fired:
            self._flagged_count += fired

    # ── Window operators ──────────────────────────────────────────────────────

    async def _check_velocity(self, txn: Transaction) -> Optional[FraudAlert]:
        sender = txn.from_account
        count = self._velocity_window.count(sender)
        volume = self._velocity_window.total_amount(sender)

        if count >= settings.RAPID_TXN_THRESHOLD:
            alert = FraudAlert(
                alert_type=FraudPattern.RAPID_MICRO,
                severity=RiskLevel.HIGH if count >= settings.RAPID_TXN_THRESHOLD * 1.5 else RiskLevel.MODERATE,
                accounts_involved=[sender],
                transaction_ids=[txn.transaction_id],
                description=(
                    f"High velocity detected on {sender}: "
                    f"{count} transactions in {settings.VELOCITY_WINDOW_SECONDS}s "
                    f"totalling ₹{volume:,.0f}"
                ),
                risk_score=min(1.0, count / (settings.RAPID_TXN_THRESHOLD * 2)),
                total_amount=volume,
                metadata={"velocity_count": count, "window_seconds": settings.VELOCITY_WINDOW_SECONDS},
            )
            await self._fire_alert(alert)
            return alert
        return None

    async def _check_fanout(self, txn: Transaction) -> Optional[FraudAlert]:
        sender = txn.from_account
        unique = self._fanout_window.unique_targets(sender)

        if unique >= settings.FAN_OUT_THRESHOLD:
            sig = (sender, unique // settings.FAN_OUT_THRESHOLD)
            if sig in self._recent_fanouts:
                return None
            self._recent_fanouts.append(sig)

            targets = list({e["to_account"] for e in self._fanout_window.get(sender)})
            total = self._fanout_window.total_amount(sender)
            alert = FraudAlert(
                alert_type=FraudPattern.FAN_OUT,
                severity=RiskLevel.HIGH if unique >= settings.FAN_OUT_THRESHOLD * 1.5 else RiskLevel.MODERATE,
                accounts_involved=[sender] + targets[:10],
                transaction_ids=[txn.transaction_id],
                description=(
                    f"Fan-out detected from {sender}: "
                    f"funds spread to {unique} accounts totalling ₹{total:,.0f}"
                ),
                risk_score=min(1.0, unique / (settings.FAN_OUT_THRESHOLD * 3)),
                propagation_path=[sender] + targets[:5],
                total_amount=total,
                metadata={"unique_targets": unique},
            )
            await self._fire_alert(alert)
            return alert
        return None

    async def _check_burst(self) -> Optional[FraudAlert]:
        count = self._burst_window.count("__global__")
        if count >= 50:  # 50 txns globally in 30 seconds
            volume = self._burst_window.total_amount("__global__")
            alert = FraudAlert(
                alert_type=FraudPattern.BURST,
                severity=RiskLevel.MODERATE,
                accounts_involved=[],
                transaction_ids=[],
                description=f"Global burst: {count} transactions in 30s, ₹{volume:,.0f} total",
                risk_score=min(1.0, count / 150),
                total_amount=volume,
                metadata={"burst_count": count},
            )
            await self._fire_alert(alert)
            return alert
        return None

    async def _check_pattern_flags(self, txn: Transaction) -> Optional[FraudAlert]:
        """Elevate pre-labeled fraud patterns from the simulator."""
        if txn.fraud_pattern == FraudPattern.NORMAL:
            return None

        if txn.fraud_pattern == FraudPattern.CIRCULAR:
            sig = txn.from_account
            if sig in self._recent_circulars:
                return None
            self._recent_circulars.append(sig)

        severity_map = {
            FraudPattern.CIRCULAR: RiskLevel.CRITICAL,
            FraudPattern.MULE_CHAIN: RiskLevel.HIGH,
            FraudPattern.LAYERING: RiskLevel.CRITICAL,
            FraudPattern.STRUCTURING: RiskLevel.HIGH,
            FraudPattern.RAPID_MICRO: RiskLevel.MODERATE,
            FraudPattern.FAN_OUT: RiskLevel.HIGH,
            FraudPattern.BURST: RiskLevel.MODERATE,
        }
        severity = severity_map.get(txn.fraud_pattern, RiskLevel.MODERATE)

        alert = FraudAlert(
            alert_type=txn.fraud_pattern,
            severity=severity,
            accounts_involved=[txn.from_account, txn.to_account],
            transaction_ids=[txn.transaction_id],
            description=self._pattern_description(txn),
            risk_score=txn.risk_score,
            total_amount=txn.amount,
            metadata={
                "payment_rail": txn.payment_rail,
                "geo_location": txn.geo_location,
                **txn.metadata,
            },
        )
        await self._fire_alert(alert)
        return alert

    def _pattern_description(self, txn: Transaction) -> str:
        descriptions = {
            FraudPattern.CIRCULAR: f"Circular fund flow detected involving {txn.from_account} → {txn.to_account}",
            FraudPattern.MULE_CHAIN: f"Mule chain hop: {txn.from_account} → {txn.to_account} (₹{txn.amount:,.0f})",
            FraudPattern.LAYERING: f"Layering transaction: {txn.from_account} → {txn.to_account} (₹{txn.amount:,.0f})",
            FraudPattern.STRUCTURING: f"Structuring detected: ₹{txn.amount:,.0f} just below threshold",
            FraudPattern.RAPID_MICRO: f"Rapid microtransaction: ₹{txn.amount:,.2f} from {txn.from_account}",
            FraudPattern.FAN_OUT: f"Fan-out transaction from {txn.from_account} (₹{txn.amount:,.0f})",
            FraudPattern.BURST: f"Burst transfer: ₹{txn.amount:,.0f}",
        }
        return descriptions.get(txn.fraud_pattern, f"Suspicious activity: {txn.fraud_pattern}")

    # ── Metrics ───────────────────────────────────────────────────────────────

    def get_window_metrics(self, account_id: str) -> dict:
        return {
            "velocity_count": self._velocity_window.count(account_id),
            "velocity_volume": self._velocity_window.total_amount(account_id),
            "fanout_targets": self._fanout_window.unique_targets(account_id),
            "fanout_volume": self._fanout_window.total_amount(account_id),
        }

    def get_global_stats(self) -> dict:
        return {
            "processed": self._processed_count,
            "flagged": self._flagged_count,
            "global_burst_30s": self._burst_window.count("__global__"),
        }
