"""
Detector-level hardener — learned calibration of V2's 16 scoring factors.

Phase B showed that lowering V2's global REVIEW threshold cannot separate
fraud-evasions from benign traffic: both sit at cluster risk ≈ 0.52–0.61, so any
cutoff that catches evasions drowns in benign false positives. The fix is to add
*margin* — to score on the factor combination that actually distinguishes the two,
which V2's hand-tuned weights do not (the white-box report notes structural factors
are deliberately demoted to tie-breakers, and that demotion is exactly where
evasions hide).

This hardener fits a logistic calibration over the SAME 16 factor signals V2
already computes, aggregated per cluster, against a labelled corpus (diverse QD
evasions = positive, benign traffic = negative). The calibrated probability is
combined with V2's native risk as ``risk' = max(native_risk, P(evasion))`` so a
benign cluster (low P) keeps its native — sub-threshold — risk while an evasion
(high P) is pushed over the line. No shipped constant is mutated; the calibration
rides on top of the engine via the oracle.

It is *learned*, so the honest test is generalization: fit on a train split, then
let the Red Team RE-EVOLVE against the calibrated detector and measure whether the
new attacks it finds still evade (see the harden campaign runner).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

# the exact 16 factor keys, in the scorer's order
FACTOR_KEYS = [
    "pattern_participation", "fraud_proximity", "velocity_anomaly", "risk_inheritance",
    "burst_activity", "volume", "pass_through", "dormancy_reactivation", "layering",
    "historical_behavior", "bridge_activity", "circular_flow", "fan_out", "fan_in",
    "betweenness", "frequency",
]


def _p90(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[int(0.9 * (len(s) - 1))]


def cluster_features(analysis) -> list[float]:
    """Per-cluster 16-vector: the p90 (robust max) of each factor signal across
    the cluster's nodes — a faithful cluster-level view of V2's own factors."""
    from blue_team_v2.core.scoring_engine.scorer import _factor_signals
    nodes = list(analysis.metrics.values())
    if not nodes:
        return [0.0] * len(FACTOR_KEYS)
    cols: dict[str, list[float]] = {k: [] for k in FACTOR_KEYS}
    for m in nodes:
        sig = _factor_signals(m)
        for k in FACTOR_KEYS:
            cols[k].append(sig[k][2])
    return [_p90(cols[k]) for k in FACTOR_KEYS]


@dataclass
class DetectorCalibrator:
    """A fitted calibration: standardiser + logistic weights, applied on top of V2."""
    mean: list[float]
    std: list[float]
    weights: list[float]
    bias: float

    def _prob(self, feats: list[float]) -> float:
        z = self.bias
        for x, mu, sd, w in zip(feats, self.mean, self.std, self.weights):
            z += w * ((x - mu) / sd)
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))

    def prob(self, analysis) -> float:
        return self._prob(cluster_features(analysis))

    def adjust(self, analysis, native_risk: float) -> float:
        """risk' = max(native, P(evasion)) — adds margin without lifting benign."""
        return max(native_risk, self._prob(cluster_features(analysis)))


@dataclass
class FactorCalibrationHardener:
    """Fits a DetectorCalibrator from labelled clusters (evasion=1, benign=0)."""
    epochs: int = 400
    lr: float = 0.3
    l2: float = 1e-3
    seed: int = 0

    def fit(self, evasion_feats: list[list[float]],
            benign_feats: list[list[float]]) -> DetectorCalibrator:
        X = evasion_feats + benign_feats
        y = [1.0] * len(evasion_feats) + [0.0] * len(benign_feats)
        n, d = len(X), len(FACTOR_KEYS)

        # standardise
        mean = [sum(row[j] for row in X) / n for j in range(d)]
        std = []
        for j in range(d):
            var = sum((row[j] - mean[j]) ** 2 for row in X) / n
            std.append(math.sqrt(var) or 1.0)
        Z = [[(row[j] - mean[j]) / std[j] for j in range(d)] for row in X]

        # class weights so the (usually fewer) evasions are not swamped
        n_pos = max(1, sum(1 for t in y if t > 0.5))
        n_neg = max(1, n - n_pos)
        w_pos, w_neg = n / (2 * n_pos), n / (2 * n_neg)

        w = [0.0] * d
        b = 0.0
        rng = random.Random(self.seed)
        idx = list(range(n))
        for _ in range(self.epochs):
            rng.shuffle(idx)
            gw = [0.0] * d
            gb = 0.0
            for i in idx:
                zi = b + sum(w[j] * Z[i][j] for j in range(d))
                p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, zi))))
                cw = w_pos if y[i] > 0.5 else w_neg
                err = cw * (p - y[i])
                for j in range(d):
                    gw[j] += err * Z[i][j]
                gb += err
            for j in range(d):
                w[j] -= self.lr * (gw[j] / n + self.l2 * w[j])
            b -= self.lr * (gb / n)

        return DetectorCalibrator(mean=mean, std=std, weights=w, bias=b)
