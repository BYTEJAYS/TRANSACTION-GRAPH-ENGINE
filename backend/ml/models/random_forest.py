"""Random Forest supervised fraud classifier (sklearn)."""
from __future__ import annotations

import numpy as np

from ml.platform.interfaces import Model

try:
    from sklearn.ensemble import RandomForestClassifier
    _OK = True
except Exception:
    _OK = False


class RandomForestModel(Model):
    name = "random_forest"
    supervised = True

    def __init__(self, n_estimators: int = 200, max_depth: int | None = 12, seed: int = 42):
        self._clf = (RandomForestClassifier(
            n_estimators=n_estimators, max_depth=max_depth,
            class_weight="balanced", random_state=seed, n_jobs=-1)
            if _OK else None)

    def available(self) -> bool:
        return _OK and self._clf is not None

    def fit(self, X, y=None):
        if not self.available() or y is None:
            return self
        self._clf.fit(X, y)
        return self

    def predict_proba(self, X) -> np.ndarray:
        if not self.available() or not hasattr(self._clf, "classes_"):
            return np.zeros(len(X), dtype=np.float32)
        return self._clf.predict_proba(X)[:, 1].astype(np.float32)

    @property
    def feature_importances_(self):
        return getattr(self._clf, "feature_importances_", None)
