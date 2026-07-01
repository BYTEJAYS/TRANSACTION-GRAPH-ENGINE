"""Isolation Forest unsupervised anomaly model (sklearn). Maps the anomaly
score to a [0,1] 'fraud-ness' probability using the training score range."""
from __future__ import annotations

import numpy as np

from ml.platform.interfaces import Model

try:
    from sklearn.ensemble import IsolationForest
    _OK = True
except Exception:
    _OK = False


class IsolationForestModel(Model):
    name = "isolation_forest"
    supervised = False

    def __init__(self, contamination: float = 0.1, seed: int = 42):
        self._clf = (IsolationForest(contamination=contamination, random_state=seed, n_jobs=-1)
                     if _OK else None)
        self._lo = 0.0
        self._hi = 1.0

    def available(self) -> bool:
        return _OK and self._clf is not None

    def fit(self, X, y=None):
        if not self.available():
            return self
        self._clf.fit(X)
        s = -self._clf.score_samples(X)   # higher = more anomalous
        self._lo, self._hi = float(np.min(s)), float(np.max(s))
        return self

    def predict_proba(self, X) -> np.ndarray:
        if not self.available() or not hasattr(self._clf, "offset_"):
            return np.zeros(len(X), dtype=np.float32)
        s = -self._clf.score_samples(X)
        rng = max(self._hi - self._lo, 1e-9)
        return np.clip((s - self._lo) / rng, 0.0, 1.0).astype(np.float32)
