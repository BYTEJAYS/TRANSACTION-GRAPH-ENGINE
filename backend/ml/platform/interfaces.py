"""
ML platform interfaces — the contract every estimator, ensemble, and explainer
implements. Kept tiny and dependency-light (numpy only) so anything can import it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np


@dataclass
class Explanation:
    """Unified explanation consumed by the evidence builder (Phase 8) and the
    explainability panel (Phase 7)."""
    score: float
    reason_codes: list[tuple[str, float]] = field(default_factory=list)  # (feature, signed contribution)
    shap: dict[str, float] = field(default_factory=dict)
    method: str = "permutation"
    narrative: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "reason_codes": [[f, round(c, 4)] for f, c in self.reason_codes],
            "shap": {k: round(v, 4) for k, v in self.shap.items()},
            "method": self.method,
            "narrative": self.narrative,
        }


class Model(ABC):
    """A scoring model. `predict_proba` returns fraud probability in [0,1] per row."""
    name: str = "model"
    version: str = "v1"
    supervised: bool = True

    @abstractmethod
    def fit(self, X: np.ndarray, y: Optional[np.ndarray] = None) -> "Model": ...

    @abstractmethod
    def predict_proba(self, X: np.ndarray) -> np.ndarray: ...

    def available(self) -> bool:
        """False when an optional backing library is missing — the ensemble skips it."""
        return True
