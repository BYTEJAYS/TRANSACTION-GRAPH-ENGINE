"""
Canonical feature spec — the SINGLE source of truth shared by training and
serving so the two can never skew. Extends the existing 12-feature
`FEATURE_NAMES` (from the shipped FeatureExtractor) with optional graph features
appended when a graph context is available.
"""
from __future__ import annotations

import numpy as np

from anomaly_detection.isolation_forest_detector import FEATURE_NAMES as _BASE

BASE_FEATURES: list[str] = list(_BASE)                 # 12 tabular features
GRAPH_FEATURES: list[str] = ["degree_c", "betweenness_c", "closeness_c"]
FEATURE_NAMES: list[str] = BASE_FEATURES + GRAPH_FEATURES


def synthetic_dataset(n_per_class: int = 4000, seed: int = 42):
    """Labelled synthetic data over the 12 base features (reuses the shipped
    generator so distributions match the typologies TGIE detects). Graph
    features are appended as zeros for the tabular-only training split."""
    from ml.xgboost_classifier import _generate_training_data
    X, y = _generate_training_data(n_per_class=n_per_class, random_state=seed)
    pad = np.zeros((X.shape[0], len(GRAPH_FEATURES)), dtype=np.float32)
    return np.hstack([X, pad]), y


def base_only(X: np.ndarray) -> np.ndarray:
    """Slice to the 12 base features for models that don't use graph context."""
    return X[:, : len(BASE_FEATURES)]
