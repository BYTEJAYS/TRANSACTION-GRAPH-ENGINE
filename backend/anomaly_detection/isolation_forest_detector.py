"""
Isolation Forest-based anomaly detection for financial transactions.

Features are extracted from both individual transactions and their
graph context (velocity, fan-out, community membership).
"""

import asyncio
import numpy as np
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from models.transaction import Transaction, FraudPattern, RiskLevel
from config import settings


# ── Feature Extractor ─────────────────────────────────────────────────────────

class FeatureExtractor:
    """
    Builds a per-transaction feature vector combining:
      - Transaction attributes (amount, rail type, hour of day)
      - Account velocity (transactions per minute)
      - Account fan-out (unique counterparties)
      - Historical volume statistics
    """

    # Track rolling history per account
    _account_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
    _account_counterparties: Dict[str, set] = defaultdict(set)

    def extract(self, txn: Transaction) -> np.ndarray:
        history = self._account_history[txn.from_account]
        now_ts = txn.timestamp.timestamp()

        # Velocity: how many in last 60 seconds
        recent = [h for h in history if now_ts - h["ts"] <= 60]
        velocity = len(recent)

        # Volume statistics
        amounts = [h["amount"] for h in history] if history else [txn.amount]
        mean_amt = float(np.mean(amounts))
        std_amt = float(np.std(amounts)) if len(amounts) > 1 else 0.0
        amount_z = (txn.amount - mean_amt) / (std_amt + 1.0)

        # Fan-out: unique recipients
        self._account_counterparties[txn.from_account].add(txn.to_account)
        fan_out = len(self._account_counterparties[txn.from_account])

        # Time features
        hour = txn.timestamp.hour
        is_night = float(0 <= hour < 6)
        is_weekend = float(txn.timestamp.weekday() >= 5)

        # Payment rail encoding
        rail_enc = {"UPI": 0, "IMPS": 1, "NEFT": 2, "RTGS": 3}.get(txn.payment_rail.value, 0)

        # Amount percentile relative to rail
        rail_typical = {"UPI": 5000, "IMPS": 25000, "NEFT": 100000, "RTGS": 500000}
        amount_ratio = txn.amount / rail_typical.get(txn.payment_rail.value, 10000)

        # Round-number indicator (structuring)
        is_round = float(txn.amount % 1000 == 0)
        is_near_threshold = float(
            any(abs(txn.amount - t) < 1000 for t in [9999, 49999, 99999, 199999])
        )

        # Update history
        history.append({"ts": now_ts, "amount": txn.amount, "rail": rail_enc})

        feature_vector = np.array([
            min(txn.amount, 1e7) / 1e7,       # normalized amount
            amount_z,                           # z-score vs account history
            amount_ratio,                       # ratio to rail typical
            velocity / 20.0,                   # normalized velocity
            fan_out / 50.0,                    # normalized fan-out
            rail_enc / 3.0,                    # payment rail
            hour / 23.0,                       # time of day
            is_night,
            is_weekend,
            is_round,
            is_near_threshold,
            float(len(history)) / 200.0,       # account age (proxy)
        ], dtype=np.float32)

        return feature_vector

    @classmethod
    def reset(cls):
        cls._account_history = defaultdict(lambda: deque(maxlen=200))
        cls._account_counterparties = defaultdict(set)


FEATURE_NAMES = [
    "normalized_amount", "amount_z_score", "amount_rail_ratio",
    "velocity", "fan_out", "payment_rail", "hour_of_day",
    "is_night", "is_weekend", "is_round_amount", "near_threshold",
    "account_age_proxy",
]


# ── Isolation Forest Detector ─────────────────────────────────────────────────

class IsolationForestDetector:
    """
    Online-updatable Isolation Forest for transaction anomaly detection.

    Maintains a rolling buffer of feature vectors and re-trains
    periodically.  Between retrains, uses the current model for scoring.
    """

    BUFFER_SIZE = 1000
    MIN_SAMPLES_TRAIN = 50

    def __init__(self):
        self._extractor = FeatureExtractor()
        self._model: Optional[IsolationForest] = None
        self._scaler = StandardScaler()
        self._buffer: deque = deque(maxlen=self.BUFFER_SIZE)
        self._is_trained = False
        self._lock = asyncio.Lock()
        self._train_count = 0

        # Initialise with a small bootstrap model
        self._bootstrap()

    def _bootstrap(self):
        """Train on random synthetic data to avoid cold-start issues."""
        rng = np.random.default_rng(42)
        synthetic = rng.standard_normal((500, len(FEATURE_NAMES))).astype(np.float32)
        # Inject a few anomalies
        synthetic[:20] *= 10
        self._scaler.fit(synthetic)
        scaled = self._scaler.transform(synthetic)
        self._model = IsolationForest(
            n_estimators=100,
            contamination=settings.ISOLATION_FOREST_CONTAMINATION,
            max_samples=256,
            random_state=42,
            n_jobs=1,
        )
        self._model.fit(scaled)
        self._is_trained = True

    async def score(self, txn: Transaction) -> Tuple[float, np.ndarray]:
        """
        Returns (anomaly_score [0,1], feature_vector).
        Higher score = more anomalous.
        """
        features = self._extractor.extract(txn)
        self._buffer.append(features)

        async with self._lock:
            if not self._is_trained:
                return 0.5, features

            scaled = self._scaler.transform(features.reshape(1, -1))
            # IsolationForest returns negative scores; -1 = most anomalous
            raw_score = self._model.decision_function(scaled)[0]
            # Flip and normalise to [0, 1]
            anomaly_score = float(np.clip(1.0 - (raw_score + 0.5), 0.0, 1.0))

        # Blend with label-based risk if pattern is known
        if txn.fraud_pattern != FraudPattern.NORMAL:
            anomaly_score = max(anomaly_score, txn.risk_score)

        return anomaly_score, features

    async def retrain(self):
        """Re-train on accumulated buffer (called periodically)."""
        if len(self._buffer) < self.MIN_SAMPLES_TRAIN:
            return

        async with self._lock:
            data = np.array(list(self._buffer), dtype=np.float32)
            self._scaler.fit(data)
            scaled = self._scaler.transform(data)
            self._model = IsolationForest(
                n_estimators=100,
                contamination=settings.ISOLATION_FOREST_CONTAMINATION,
                max_samples=min(256, len(data)),
                random_state=42,
                n_jobs=1,
            )
            self._model.fit(scaled)
            self._is_trained = True
            self._train_count += 1

    def risk_level(self, score: float) -> RiskLevel:
        if score < 0.3:
            return RiskLevel.SAFE
        elif score < 0.6:
            return RiskLevel.MODERATE
        elif score < 0.8:
            return RiskLevel.HIGH
        return RiskLevel.CRITICAL

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_trained": self._is_trained,
            "buffer_size": len(self._buffer),
            "train_count": self._train_count,
            "feature_count": len(FEATURE_NAMES),
            "contamination": settings.ISOLATION_FOREST_CONTAMINATION,
        }
