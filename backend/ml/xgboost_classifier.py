"""
XGBoost supervised fraud classifier.

Complements the unsupervised Isolation Forest: where the forest flags
*statistical* outliers, this gradient-boosted model learns the *labelled*
boundary between fraudulent and legitimate transaction behaviour and emits a
calibrated fraud probability in [0, 1].

It reuses the exact 12-dimensional feature vector produced by
``anomaly_detection.FeatureExtractor`` (see ``FEATURE_NAMES``), so the same
features that drive anomaly scoring also drive supervised classification.

The model is trained at start-up on a deterministic synthetic dataset whose
feature distributions mirror the real fraud typologies TGIE detects
(structuring, smurfing/fan-out, velocity bursts, new-account mules). This keeps
the engine self-contained — no external dataset or model artifact required.

Falls back gracefully if ``xgboost`` is not installed.
"""

import numpy as np
from typing import Dict, List, Optional, Any

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except Exception:  # pragma: no cover - xgboost missing OR native libs (e.g. libomp) unavailable
    # xgboost raises XGBoostError (not ImportError) when the OpenMP runtime is
    # absent, so we catch broadly and degrade gracefully instead of crashing.
    XGBOOST_AVAILABLE = False

from anomaly_detection.isolation_forest_detector import FEATURE_NAMES


# ── Synthetic labelled training data ──────────────────────────────────────────

def _generate_training_data(
    n_per_class: int = 4000, random_state: int = 42
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build a labelled dataset over the 12 FeatureExtractor features.

    Legitimate (label 0) and fraudulent (label 1) samples are drawn from
    distributions that reflect the real feature semantics, with deliberate
    overlap so the boundary is non-trivial (no leakage / perfect separation).
    """
    rng = np.random.default_rng(random_state)
    d = len(FEATURE_NAMES)  # 12

    # ---- Legitimate behaviour ------------------------------------------------
    legit = np.zeros((n_per_class, d), dtype=np.float32)
    legit[:, 0] = np.clip(rng.gamma(2.0, 0.004, n_per_class), 0, 1)      # normalized_amount (small)
    legit[:, 1] = rng.normal(0.0, 0.6, n_per_class)                      # amount_z_score (near 0)
    legit[:, 2] = np.clip(rng.normal(0.4, 0.25, n_per_class), 0, 3)      # amount_rail_ratio
    legit[:, 3] = np.clip(rng.gamma(1.3, 0.05, n_per_class), 0, 1)       # velocity (low)
    legit[:, 4] = np.clip(rng.gamma(1.3, 0.04, n_per_class), 0, 1)       # fan_out (low)
    legit[:, 5] = rng.integers(0, 4, n_per_class) / 3.0                  # payment_rail
    legit[:, 6] = rng.uniform(0.3, 0.95, n_per_class)                    # hour_of_day (daytime-ish)
    legit[:, 7] = (rng.random(n_per_class) < 0.12).astype(np.float32)    # is_night
    legit[:, 8] = (rng.random(n_per_class) < 0.28).astype(np.float32)    # is_weekend
    legit[:, 9] = (rng.random(n_per_class) < 0.20).astype(np.float32)    # is_round_amount
    legit[:, 10] = (rng.random(n_per_class) < 0.05).astype(np.float32)   # near_threshold (rare)
    legit[:, 11] = np.clip(rng.beta(5, 2, n_per_class), 0, 1)            # account_age_proxy (established)

    # ---- Fraudulent behaviour ------------------------------------------------
    fraud = np.zeros((n_per_class, d), dtype=np.float32)
    fraud[:, 0] = np.clip(rng.gamma(2.0, 0.02, n_per_class), 0, 1)       # larger / structured amounts
    fraud[:, 1] = rng.normal(1.6, 1.2, n_per_class)                      # high amount z-score
    fraud[:, 2] = np.clip(rng.normal(1.1, 0.4, n_per_class), 0, 3)       # near/over rail-typical
    fraud[:, 3] = np.clip(rng.gamma(3.0, 0.12, n_per_class), 0, 1)       # high velocity (bursts)
    fraud[:, 4] = np.clip(rng.gamma(3.0, 0.12, n_per_class), 0, 1)       # high fan_out (smurfing)
    fraud[:, 5] = rng.integers(0, 4, n_per_class) / 3.0                  # payment_rail
    fraud[:, 6] = rng.uniform(0.0, 1.0, n_per_class)                     # any hour
    fraud[:, 7] = (rng.random(n_per_class) < 0.45).astype(np.float32)    # more night activity
    fraud[:, 8] = (rng.random(n_per_class) < 0.32).astype(np.float32)    # is_weekend
    fraud[:, 9] = (rng.random(n_per_class) < 0.55).astype(np.float32)    # round amounts (layering)
    fraud[:, 10] = (rng.random(n_per_class) < 0.50).astype(np.float32)   # near reporting threshold
    fraud[:, 11] = np.clip(rng.beta(2, 5, n_per_class), 0, 1)            # newer accounts (mules)

    X = np.vstack([legit, fraud]).astype(np.float32)
    y = np.concatenate([np.zeros(n_per_class), np.ones(n_per_class)]).astype(np.int32)

    # Inject realistic overlap so the boundary is non-trivial:
    #  - additive Gaussian noise on the continuous features
    #  - a fraction of label noise (stealthy fraud / bursty-but-legit accounts)
    cont = [0, 1, 2, 3, 4, 6, 11]
    X[:, cont] += rng.normal(0.0, 0.18, size=(len(X), len(cont))).astype(np.float32)
    X[:, cont] = np.clip(X[:, cont], -2.0, 3.0)
    flip = rng.random(len(y)) < 0.07
    y[flip] = 1 - y[flip]

    # Shuffle
    idx = rng.permutation(len(y))
    return X[idx], y[idx]


# ── Classifier ────────────────────────────────────────────────────────────────

class XGBoostFraudClassifier:
    """
    Gradient-boosted (XGBoost) supervised fraud classifier over the shared
    12-feature transaction vector. Trains on synthetic labelled data at init.
    """

    def __init__(self, random_state: int = 42):
        self._model: Optional["xgb.XGBClassifier"] = None
        self._is_trained = False
        self._random_state = random_state
        self._train_auc: Optional[float] = None
        if XGBOOST_AVAILABLE:
            self._train()

    def _train(self):
        X, y = _generate_training_data(random_state=self._random_state)
        # Hold out a slice purely to report a train-time AUC for the status panel.
        split = int(len(y) * 0.85)
        X_tr, y_tr, X_val, y_val = X[:split], y[:split], X[split:], y[split:]

        self._model = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.9,
            colsample_bytree=0.9,
            reg_lambda=1.0,
            eval_metric="auc",
            random_state=self._random_state,
            n_jobs=1,
        )
        self._model.fit(X_tr, y_tr)

        # Simple AUC on the holdout (no sklearn.metrics dependency required).
        val_p = self._model.predict_proba(X_val)[:, 1]
        self._train_auc = _roc_auc(y_val, val_p)
        self._is_trained = True

    def predict_proba(self, features: np.ndarray) -> float:
        """Return fraud probability in [0, 1] for one 12-d feature vector."""
        if not self._is_trained or self._model is None:
            return 0.5  # graceful fallback when xgboost is unavailable
        x = np.asarray(features, dtype=np.float32).reshape(1, -1)
        return float(self._model.predict_proba(x)[0, 1])

    def feature_importances(self) -> Dict[str, float]:
        """Map each feature name to its gain-based importance (descending)."""
        if not self._is_trained or self._model is None:
            return {}
        imp = self._model.feature_importances_
        pairs = sorted(
            zip(FEATURE_NAMES, (float(v) for v in imp)),
            key=lambda kv: kv[1],
            reverse=True,
        )
        return dict(pairs)

    def get_status(self) -> Dict[str, Any]:
        return {
            "available": XGBOOST_AVAILABLE,
            "is_trained": self._is_trained,
            "model": "XGBClassifier (gradient-boosted trees)",
            "n_estimators": 200,
            "max_depth": 4,
            "feature_count": len(FEATURE_NAMES),
            "train_auc": round(self._train_auc, 4) if self._train_auc is not None else None,
        }


def _roc_auc(y_true: np.ndarray, scores: np.ndarray) -> float:
    """Rank-based ROC AUC (Mann-Whitney U), no sklearn dependency."""
    y_true = np.asarray(y_true)
    pos = scores[y_true == 1]
    neg = scores[y_true == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(scores)
    ranks = np.empty(len(scores), dtype=np.float64)
    ranks[order] = np.arange(1, len(scores) + 1)
    rank_sum_pos = ranks[y_true == 1].sum()
    auc = (rank_sum_pos - len(pos) * (len(pos) + 1) / 2.0) / (len(pos) * len(neg))
    return float(auc)


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    clf = XGBoostFraudClassifier()
    print("status:", clf.get_status())
    if clf._is_trained:
        # A clearly-fraudulent vector: high velocity, fan-out, near-threshold, new account
        fraudish = np.array(
            [0.04, 2.5, 1.1, 0.9, 0.85, 0.33, 0.1, 1, 0, 1, 1, 0.1], dtype=np.float32
        )
        legitish = np.array(
            [0.005, 0.1, 0.3, 0.05, 0.04, 0.0, 0.6, 0, 0, 0, 0, 0.8], dtype=np.float32
        )
        print(f"P(fraud | fraud-like)  = {clf.predict_proba(fraudish):.3f}")
        print(f"P(fraud | legit-like)  = {clf.predict_proba(legitish):.3f}")
        print("top features:", list(clf.feature_importances().items())[:5])
