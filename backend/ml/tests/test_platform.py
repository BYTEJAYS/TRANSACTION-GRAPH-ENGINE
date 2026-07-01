"""Phase 5 Wave A — ML platform tests: contracts, metrics gate, registry
round-trip, drift, fallback, explanation."""
from __future__ import annotations

import numpy as np
import pytest

from ml.platform.features import synthetic_dataset, FEATURE_NAMES
from ml.platform.ensemble import RiskEnsemble
from ml.platform.drift import DriftMonitor, psi
from ml.platform import registry
from ml.models.random_forest import RandomForestModel
from ml.models.isolation_forest import IsolationForestModel
from ml.models.xgboost import XGBoostModel


@pytest.fixture(scope="module")
def data():
    X, y = synthetic_dataset(n_per_class=1500)
    return X, y


def test_estimator_contracts(data):
    X, y = data
    for m in (RandomForestModel(), IsolationForestModel(), XGBoostModel()):
        assert isinstance(m.available(), bool)
        if not m.available():
            continue
        m.fit(X, y if m.supervised else None)
        p = m.predict_proba(X[:50])
        assert p.shape == (50,)
        assert float(p.min()) >= 0.0 and float(p.max()) <= 1.0


def test_ensemble_metrics_gate(data):
    X, y = data
    n = len(X); cut = int(n * 0.8)
    rng = np.random.default_rng(0); idx = rng.permutation(n)
    tr, te = idx[:cut], idx[cut:]
    ens = RiskEnsemble().fit(X[tr], y[tr])
    assert ens.available()                       # at least RF + IF on sklearn
    from ml.platform.training import _roc_auc
    auc = _roc_auc(y[te], ens.predict_proba(X[te]))
    assert auc >= 0.85, f"ensemble ROC-AUC below gate: {auc}"


def test_registry_round_trip(tmp_path, data, monkeypatch):
    # redirect artifacts to a temp dir so the test is hermetic
    import ml.platform.registry as reg
    monkeypatch.setattr(reg, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(reg, "_INDEX", tmp_path / "index.json")
    X, y = data
    ens = RiskEnsemble().fit(X[:500], y[:500])
    before = ens.predict_proba(X[:20])
    reg.save(ens, "risk_ensemble", "vtest", metrics={"roc_auc": 0.9})
    loaded = reg.load("risk_ensemble")
    after = loaded.predict_proba(X[:20])
    assert np.allclose(before, after), "predictions changed across save/load"
    assert reg.info("risk_ensemble")["active"] == "vtest"


def test_drift_detects_shift(data):
    X, y = data
    mon = DriftMonitor(FEATURE_NAMES).fit_baseline(X)
    shifted = X.copy()
    shifted[:, 0] = shifted[:, 0] + 5.0          # large shift on feature 0
    res = mon.check(shifted)
    assert res["status"] == "alert" and res["retrain_recommended"]
    # and no false alarm on the same distribution
    assert mon.check(X)["status"] == "ok"


def test_explanation_reason_codes(data):
    X, y = data
    ens = RiskEnsemble().fit(X[:800], y[:800])
    expl = ens.explain_one(X[0])
    d = expl.to_dict()
    assert 0.0 <= d["score"] <= 1.0
    assert len(d["reason_codes"]) >= 1
    assert d["method"] in ("shap", "permutation")
    assert isinstance(d["narrative"], str) and d["narrative"]


def test_psi_zero_on_identical():
    a = np.random.default_rng(1).normal(size=2000)
    assert psi(a, a) < 0.01
