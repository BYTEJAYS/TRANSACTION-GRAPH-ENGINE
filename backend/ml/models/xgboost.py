"""XGBoost wrapper — gradient-boosted supervised classifier. Gracefully reports
available()=False when xgboost (or its OpenMP runtime) is absent, so the
ensemble simply skips it."""
from __future__ import annotations

import numpy as np

from ml.platform.interfaces import Model

try:
    import xgboost as xgb
    _OK = True
except Exception:  # missing lib OR missing libomp → XGBoostError, catch broadly
    _OK = False


class XGBoostModel(Model):
    name = "xgboost"
    supervised = True

    def __init__(self, seed: int = 42):
        self._clf = (xgb.XGBClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.1,
            subsample=0.9, eval_metric="logloss", random_state=seed)
            if _OK else None)
        self._fitted = False

    def available(self) -> bool:
        return _OK and self._clf is not None

    def fit(self, X, y=None):
        if not self.available() or y is None:
            return self
        self._clf.fit(X, y)
        self._fitted = True
        return self

    def predict_proba(self, X) -> np.ndarray:
        if not self.available() or not self._fitted:
            return np.zeros(len(X), dtype=np.float32)
        return self._clf.predict_proba(X)[:, 1].astype(np.float32)
