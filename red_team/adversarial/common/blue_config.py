"""
Blue Team configuration — the mutable surface the self-play loop hardens.

V2 has no learned weights; it is hardened by *retuning its decision surface*.
``BlueConfig`` is the adversarial-side representation of that surface. It defaults
to V2's shipped thresholds, so an oracle built from a default config reproduces
the deployed detector exactly. The hardener returns a *tightened* config; the loop
measures the resulting robustness gain and benign false-positive cost before
adopting it.

Only the decision thresholds are exposed for now (the cleanest, highest-leverage
lever — see white-box report §0: V2's verdict is a threshold over cluster risk).
Per-detector monetary/degree gate overrides are the natural next extension and
would slot in as additional fields here.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

# shipped defaults, mirrored so the adversarial package need not import V2 at rest
_LOG, _REVIEW, _HIGH = 0.38, 0.62, 0.83


@dataclass(frozen=True)
class BlueConfig:
    log_threshold: float = _LOG
    review_threshold: float = _REVIEW
    high_risk_threshold: float = _HIGH

    def to_v2_thresholds(self):
        """Project to the V2 engine's Thresholds object."""
        from blue_team_v2.types import Thresholds
        return Thresholds(log=self.log_threshold, review=self.review_threshold,
                          high_risk=self.high_risk_threshold)

    def with_review(self, review: float) -> "BlueConfig":
        # keep ordering sane: log ≤ review ≤ high_risk
        review = max(self.log_threshold, min(self.high_risk_threshold, review))
        return replace(self, review_threshold=round(review, 4))

    def is_default(self) -> bool:
        return (self.log_threshold == _LOG and self.review_threshold == _REVIEW
                and self.high_risk_threshold == _HIGH)

    def summary(self) -> dict:
        return {"log": self.log_threshold, "review": self.review_threshold,
                "high_risk": self.high_risk_threshold}
