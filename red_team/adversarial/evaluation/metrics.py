"""
Evaluation metrics.

Reports the headline quantities from the directive that are meaningful for the
current vertical slice:

  * Attack Success Rate (ASR)  — fraction of confirmed-FRAUD archetypes driven to
                                 a benign verdict (≤ LOGGED) with the laundering
                                 objective intact.
  * Mean detection downgrade   — baseline detection score minus evaded score.
  * Mean graph distortion      — structural cost of the successful attacks.
  * Detector-evasion table     — which Blue Team detectors were silenced.

Robustness Gain / Generalization / Calibration etc. plug in here once the
self-play retraining loop is online (they need a before/after defender).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..common.attack_graph import AttackGraph
from ..common.oracle import BlueTeamOracle, OperationDetection


@dataclass
class CampaignResult:
    archetype: str
    baseline_verdict: str
    baseline_risk: float
    baseline_detectors: set[str]
    best_verdict: str
    best_risk: float
    best_detection: float
    best_distortion: float
    evaded: bool
    objective_ok: bool
    residual_detectors: set[str]
    genome: str
    num_components: int
    oracle_calls: int
    # validity instrumentation
    strict_objective_ok: bool = True   # holds under on-graph (non-partition) objective
    evasion_rate: float = 0.0          # fraction of realizations that evaded
    detection_std: float = 0.0         # variance of detection score across realizations


def evaluate_baseline(oracle: BlueTeamOracle, base: AttackGraph) -> OperationDetection:
    """Confirm the untouched fraud graph's verdict before any attack."""
    return oracle.detect(base)


def summarize_campaign(results: list[CampaignResult]) -> dict:
    n = len(results) or 1
    evaded = [r for r in results if r.evaded and r.objective_ok]
    asr = len(evaded) / n
    # strict ASR: evasions that also hold under the on-graph (non-partition)
    # objective — i.e. NOT dependent on the off-graph-completion assumption.
    strict_evaded = [r for r in evaded if r.strict_objective_ok]
    asr_strict = len(strict_evaded) / n
    partition_dependent = len(evaded) - len(strict_evaded)

    downgrades = []
    from ..common.oracle import VERDICT_SCORE
    for r in results:
        downgrades.append(VERDICT_SCORE.get(r.baseline_verdict, 1.0) - r.best_detection)
    mean_downgrade = sum(downgrades) / n
    mean_distortion = (sum(r.best_distortion for r in evaded) / len(evaded)) if evaded else 0.0

    # which detectors did we silence, across successful attacks?
    silenced: dict[str, int] = {}
    for r in evaded:
        for d in (r.baseline_detectors - r.residual_detectors):
            silenced[d] = silenced.get(d, 0) + 1

    return {
        "archetypes": n,
        "attack_success_rate": round(asr, 4),
        "attack_success_rate_strict": round(asr_strict, 4),
        "partition_dependent_evasions": partition_dependent,
        "evaded": len(evaded),
        "mean_detection_downgrade": round(mean_downgrade, 4),
        "mean_distortion_on_success": round(mean_distortion, 4),
        "detectors_silenced": dict(sorted(silenced.items(), key=lambda kv: -kv[1])),
        "total_oracle_calls": sum(r.oracle_calls for r in results),
    }
