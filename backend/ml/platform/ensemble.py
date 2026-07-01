"""
RiskEnsemble — blends the available models into one calibrated fraud probability.

Only `available()` models participate, so the ensemble works whether you have
just sklearn (RandomForest + IsolationForest) or the full set (+XGBoost/LightGBM).
The blended score is isotonically calibrated against labels when supervised
models and labels are present. This score feeds the rule-based `risk_engine` as
ONE capped factor — it never opens a case alone.
"""
from __future__ import annotations

import numpy as np

from .interfaces import Model, Explanation
from . import explain as _explain
from .features import FEATURE_NAMES

try:
    from sklearn.isotonic import IsotonicRegression
    _HAS_ISO = True
except Exception:
    _HAS_ISO = False


class RiskEnsemble(Model):
    name = "risk_ensemble"

    def __init__(self, models: list[Model] | None = None):
        from ml.models.random_forest import RandomForestModel
        from ml.models.isolation_forest import IsolationForestModel
        from ml.models.xgboost import XGBoostModel
        self.models = models or [RandomForestModel(), XGBoostModel(), IsolationForestModel()]
        self._iso = None
        self._baseline: np.ndarray | None = None

    def active_models(self) -> list[Model]:
        return [m for m in self.models if m.available()]

    def available(self) -> bool:
        return len(self.active_models()) > 0

    def fit(self, X, y=None):
        X = np.asarray(X, dtype=np.float32)
        self._baseline = X.mean(axis=0)
        for m in self.active_models():
            m.fit(X, y if m.supervised else None)
        if _HAS_ISO and y is not None:
            blended = self._blend(X)
            try:
                self._iso = IsotonicRegression(out_of_bounds="clip").fit(blended, y)
            except Exception:
                self._iso = None
        return self

    def _blend(self, X) -> np.ndarray:
        active = self.active_models()
        if not active:
            return np.zeros(len(X), dtype=np.float32)
        # supervised models weighted 1.0, unsupervised anomaly 0.5 (a hint, not a verdict)
        num, den = np.zeros(len(X)), 0.0
        for m in active:
            w = 1.0 if m.supervised else 0.5
            num += w * m.predict_proba(X)
            den += w
        return (num / den).astype(np.float32)

    def predict_proba(self, X) -> np.ndarray:
        X = np.asarray(X, dtype=np.float32)
        blended = self._blend(X)
        if self._iso is not None:
            return np.clip(self._iso.predict(blended), 0.0, 1.0).astype(np.float32)
        return blended

    def explain_one(self, x: np.ndarray) -> Explanation:
        base = self._baseline if self._baseline is not None else np.zeros(len(FEATURE_NAMES))
        return _explain.explain(self, np.asarray(x, dtype=float), base, FEATURE_NAMES)
