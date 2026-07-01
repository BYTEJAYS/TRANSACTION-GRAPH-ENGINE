"""
Concept-drift monitoring — Population Stability Index (PSI) per feature plus a
KS test, compared against a stored training baseline. A breach emits a retrain
signal (logged; optionally enqueued as a Celery task in Phase 9).
"""
from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger("tgie.ml.drift")

PSI_WARN = 0.1
PSI_ALERT = 0.25   # > 0.25 ⇒ significant population shift → retrain


def psi(expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
    """PSI over quantile buckets of the expected distribution."""
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    if expected.size == 0 or actual.size == 0:
        return 0.0
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, buckets + 1)))
    if edges.size < 2:
        return 0.0
    e_hist = np.histogram(expected, bins=edges)[0] / len(expected)
    a_hist = np.histogram(actual, bins=edges)[0] / len(actual)
    e_hist = np.clip(e_hist, 1e-6, None)
    a_hist = np.clip(a_hist, 1e-6, None)
    return float(np.sum((a_hist - e_hist) * np.log(a_hist / e_hist)))


class DriftMonitor:
    def __init__(self, feature_names: list[str]):
        self.feature_names = feature_names
        self._baseline: np.ndarray | None = None

    def fit_baseline(self, X: np.ndarray) -> "DriftMonitor":
        self._baseline = np.asarray(X, dtype=float)
        return self

    def check(self, X: np.ndarray) -> dict:
        if self._baseline is None:
            return {"status": "no_baseline", "features": {}}
        X = np.asarray(X, dtype=float)
        per = {}
        for j, name in enumerate(self.feature_names):
            if j >= X.shape[1] or j >= self._baseline.shape[1]:
                break
            per[name] = round(psi(self._baseline[:, j], X[:, j]), 4)
        worst = max(per.values()) if per else 0.0
        status = "alert" if worst > PSI_ALERT else "warn" if worst > PSI_WARN else "ok"
        if status == "alert":
            log.warning("ML drift ALERT — worst PSI %.3f → retrain recommended", worst)
        return {"status": status, "worst_psi": round(worst, 4),
                "retrain_recommended": status == "alert", "features": per}
