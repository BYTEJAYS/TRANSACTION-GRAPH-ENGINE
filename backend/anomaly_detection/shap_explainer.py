"""
SHAP-based explainability for Isolation Forest anomaly scores.

Generates per-feature importance values that explain WHY a
transaction or account was flagged as suspicious.
"""

import numpy as np
from typing import Dict, List, Optional, Any

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False

from anomaly_detection.isolation_forest_detector import FEATURE_NAMES


FEATURE_LABELS = {
    "normalized_amount": "Transaction Amount",
    "amount_z_score": "Amount vs History",
    "amount_rail_ratio": "Amount vs Rail Average",
    "velocity": "Transaction Velocity",
    "fan_out": "Account Fan-out",
    "payment_rail": "Payment Rail",
    "hour_of_day": "Time of Day",
    "is_night": "Night Transaction",
    "is_weekend": "Weekend Transaction",
    "is_round_amount": "Round Amount",
    "near_threshold": "Near Detection Threshold",
    "account_age_proxy": "Account Activity Age",
}


class SHAPExplainer:
    """
    Wraps a trained IsolationForest with a TreeExplainer to produce
    SHAP values.  Falls back to rule-based importance if SHAP is absent.
    """

    def __init__(self, detector=None):
        self._detector = detector
        self._explainer: Optional[Any] = None
        self._background: Optional[np.ndarray] = None
        self._available = SHAP_AVAILABLE

    def fit(self, background_data: np.ndarray):
        """Fit SHAP explainer on background samples."""
        if not self._available or self._detector is None:
            return
        if self._detector._model is None:
            return
        try:
            self._background = background_data[:100]  # keep it fast
            self._explainer = shap.TreeExplainer(self._detector._model)
        except Exception:
            self._explainer = None

    def explain(
        self, feature_vector: np.ndarray, anomaly_score: float
    ) -> Dict[str, Any]:
        """
        Returns SHAP-based explanation dict:
          {feature_name: shap_value, ...} + metadata.
        """
        if self._available and self._explainer is not None:
            return self._shap_explain(feature_vector, anomaly_score)
        return self._rule_explain(feature_vector, anomaly_score)

    def _shap_explain(self, fv: np.ndarray, score: float) -> Dict[str, Any]:
        try:
            if self._detector is None:
                return self._rule_explain(fv, score)
            scaled = self._detector._scaler.transform(fv.reshape(1, -1))
            shap_values = self._explainer.shap_values(scaled)
            if isinstance(shap_values, list):
                sv = shap_values[0][0]
            else:
                sv = shap_values[0]

            importance = {FEATURE_NAMES[i]: float(abs(sv[i])) for i in range(len(FEATURE_NAMES))}
            top_features = sorted(importance.items(), key=lambda x: -x[1])[:5]

            return {
                "method": "SHAP TreeExplainer",
                "anomaly_score": round(score, 4),
                "feature_importance": {
                    FEATURE_LABELS.get(k, k): round(v, 4) for k, v in importance.items()
                },
                "top_drivers": [
                    {"feature": FEATURE_LABELS.get(k, k), "importance": round(v, 4)}
                    for k, v in top_features
                ],
                "explanation_text": self._narrative(top_features, fv, score),
            }
        except Exception:
            return self._rule_explain(fv, score)

    def _rule_explain(self, fv: np.ndarray, score: float) -> Dict[str, Any]:
        """Heuristic feature importance when SHAP is unavailable."""
        rules = {
            "velocity": fv[3] * 2.0,
            "fan_out": fv[4] * 1.8,
            "amount_z_score": abs(fv[1]) * 1.5,
            "near_threshold": fv[10] * 3.0,
            "is_night": fv[7] * 0.8,
            "normalized_amount": fv[0] * 1.2,
            "amount_rail_ratio": fv[2] * 1.0,
            "is_round_amount": fv[9] * 0.6,
        }
        total = sum(rules.values()) + 1e-9
        normalized = {k: v / total for k, v in rules.items()}
        top = sorted(normalized.items(), key=lambda x: -x[1])[:5]

        return {
            "method": "rule-based fallback",
            "anomaly_score": round(score, 4),
            "feature_importance": {
                FEATURE_LABELS.get(k, k): round(v, 4)
                for k, v in normalized.items()
            },
            "top_drivers": [
                {"feature": FEATURE_LABELS.get(k, k), "importance": round(v, 4)}
                for k, v in top
            ],
            "explanation_text": self._narrative(top, fv, score),
        }

    def _narrative(self, top_features: List, fv: np.ndarray, score: float) -> str:
        """Generate a human-readable explanation for the anomaly."""
        if score < 0.3:
            return "Transaction appears normal with no significant anomalies detected."

        parts = []
        feat_map = dict(top_features)

        if feat_map.get("velocity", 0) > 0.1:
            count = int(fv[3] * 20)
            parts.append(f"unusually high velocity ({count}+ txns/min)")

        if feat_map.get("fan_out", 0) > 0.1:
            out = int(fv[4] * 50)
            parts.append(f"wide fan-out pattern ({out}+ unique targets)")

        if feat_map.get("amount_z_score", 0) > 0.1:
            parts.append("amount deviates significantly from account history")

        if feat_map.get("near_threshold", 0) > 0.1:
            parts.append("amount structured near detection threshold")

        if feat_map.get("is_night", 0) > 0.05:
            parts.append("off-hours activity (00:00–06:00)")

        if not parts:
            parts.append("multiple low-weight anomaly signals combined")

        severity = (
            "CRITICAL" if score >= 0.8
            else "HIGH" if score >= 0.6
            else "MODERATE"
        )
        return f"[{severity}] Flagged due to: {'; '.join(parts)}."

    @staticmethod
    def get_feature_names() -> List[str]:
        return [FEATURE_LABELS.get(f, f) for f in FEATURE_NAMES]
