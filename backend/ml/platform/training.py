"""
Retraining pipeline (CLI now; Celery task in Phase 9).

    python -m ml.platform.training --train     # train ensemble, eval, register if it passes the gate

Trains on the synthetic labelled dataset (distributions matching TGIE typologies),
evaluates ROC-AUC on a holdout, registers the model as 'active' iff it clears the
gate, and stores a drift baseline alongside it.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

from .ensemble import RiskEnsemble
from .drift import DriftMonitor
from .features import synthetic_dataset, FEATURE_NAMES
from . import registry

AUC_GATE = 0.85


def _split(X, y, frac=0.8, seed=42):
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(X))
    cut = int(len(X) * frac)
    tr, te = idx[:cut], idx[cut:]
    return X[tr], y[tr], X[te], y[te]


def _roc_auc(y_true, y_score) -> float:
    try:
        from sklearn.metrics import roc_auc_score
        return float(roc_auc_score(y_true, y_score))
    except Exception:
        # rank-based fallback (Mann–Whitney U) if sklearn.metrics unavailable
        order = np.argsort(y_score)
        ranks = np.empty_like(order, dtype=float)
        ranks[order] = np.arange(1, len(y_score) + 1)
        pos = ranks[y_true == 1].sum()
        n1 = int((y_true == 1).sum()); n0 = len(y_true) - n1
        return float((pos - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else 0.5


def train_and_register(version: str = "v1") -> dict:
    X, y = synthetic_dataset()
    Xtr, ytr, Xte, yte = _split(X, y)
    ens = RiskEnsemble().fit(Xtr, ytr)
    auc = _roc_auc(yte, ens.predict_proba(Xte))
    active = [m.name for m in ens.active_models()]
    passed = auc >= AUC_GATE
    result = {"roc_auc": round(auc, 4), "passed_gate": passed,
              "active_models": active, "gate": AUC_GATE}
    if passed:
        drift = DriftMonitor(FEATURE_NAMES).fit_baseline(Xtr)
        registry.save(ens, "risk_ensemble", version, metrics=result, status="active")
        registry.save(drift, "drift_baseline", version, metrics={}, status="active")
        result["registered"] = registry.info("risk_ensemble")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.parse_args()
    res = train_and_register()
    print(f"models: {res['active_models']}")
    print(f"ROC-AUC: {res['roc_auc']}  (gate {res['gate']})  -> "
          f"{'REGISTERED active' if res['passed_gate'] else 'FAILED gate, not registered'}")
    return 0 if res["passed_gate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
