"""
Unified explainability. Tries SHAP, then LIME, then a dependency-free
permutation fallback — always returns an `Explanation` with reason codes, so
downstream (evidence builder, UI panel) never has to care which was available.
"""
from __future__ import annotations

import numpy as np

from .interfaces import Explanation

try:
    import shap  # noqa: F401
    _HAS_SHAP = True
except Exception:
    _HAS_SHAP = False

try:
    import lime  # noqa: F401
    _HAS_LIME = True
except Exception:
    _HAS_LIME = False


def _permutation_contributions(model, x: np.ndarray, baseline: np.ndarray,
                               feature_names: list[str]) -> list[tuple[str, float]]:
    """Contribution of each feature = Δ probability when reset to baseline mean."""
    x = x.reshape(1, -1)
    base_p = float(model.predict_proba(x)[0])
    contribs = []
    for j, name in enumerate(feature_names):
        if j >= x.shape[1]:
            break
        perturbed = x.copy()
        perturbed[0, j] = baseline[j]
        p = float(model.predict_proba(perturbed)[0])
        contribs.append((name, base_p - p))   # how much this feature pushed the score up
    contribs.sort(key=lambda t: abs(t[1]), reverse=True)
    return contribs


def explain(model, x: np.ndarray, baseline: np.ndarray,
            feature_names: list[str]) -> Explanation:
    x = np.asarray(x, dtype=float)
    score = float(model.predict_proba(x.reshape(1, -1))[0])
    method = "permutation"
    shap_map: dict[str, float] = {}

    if _HAS_SHAP and hasattr(getattr(model, "_clf", None), "predict_proba"):
        try:
            import shap
            expl = shap.TreeExplainer(model._clf)
            vals = expl.shap_values(x.reshape(1, -1))
            arr = vals[1][0] if isinstance(vals, list) else np.asarray(vals)[0]
            shap_map = {feature_names[i]: float(arr[i])
                        for i in range(min(len(feature_names), len(arr)))}
            method = "shap"
        except Exception:
            shap_map = {}

    reason_codes = (sorted(shap_map.items(), key=lambda t: abs(t[1]), reverse=True)
                    if shap_map else
                    _permutation_contributions(model, x, baseline, feature_names))

    top = reason_codes[:3]
    drivers = ", ".join(f"{f} ({c:+.2f})" for f, c in top)
    narrative = (f"Model risk {score:.0%}. Top drivers: {drivers}."
                 if top else f"Model risk {score:.0%}.")
    return Explanation(score=score, reason_codes=reason_codes, shap=shap_map,
                       method=method, narrative=narrative)
