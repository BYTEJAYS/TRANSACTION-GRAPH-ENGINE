"""
Adversarial research engine.

This is a controlled *research* environment. Its sole capability is to explore
the abstract parameter space of a scenario — varying numeric knobs such as hop
count, fan-out degree, amount dispersion or layer depth — and to score the
resulting synthetic datasets for **realism** and **diversity**.

It deliberately does NOT, and must NOT:
  * interact with any real payment system,
  * produce step-by-step instructions for committing fraud,
  * tune against, query, or otherwise involve the Blue Team detector.

The output is a structured *hypothesis ledger*: a table of parameter vectors
and the descriptive realism/diversity scores they yielded. Researchers read the
ledger to understand which regions of the synthetic space are under-explored.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from red_team.core.config import RedTeamConfig, config as default_config
from red_team.core.models import GeneratedScenario, ScenarioSpec
from red_team.simulators.fraud_simulator import FraudSimulator


@dataclass
class Hypothesis:
    """One explored point in the scenario parameter space."""

    parameters: Dict[str, float]
    realism_score: float
    diversity_score: float
    transaction_count: int
    account_count: int

    @property
    def combined_score(self) -> float:
        return round(0.6 * self.realism_score + 0.4 * self.diversity_score, 4)


@dataclass
class ExplorationResult:
    base_scenario_id: str
    hypotheses: List[Hypothesis] = field(default_factory=list)

    def best(self) -> Optional[Hypothesis]:
        return max(self.hypotheses, key=lambda h: h.combined_score, default=None)

    def ledger(self) -> List[Dict]:
        return [
            {**h.parameters, "realism": h.realism_score, "diversity": h.diversity_score,
             "combined": h.combined_score, "txns": h.transaction_count}
            for h in sorted(self.hypotheses, key=lambda h: h.combined_score, reverse=True)
        ]


# Parameters the explorer is allowed to perturb, with sampling bounds.
_SEARCH_SPACE = {
    "depth": (2, 6),
    "recipients": (4, 20),
    "layers": (2, 5),
    "split": (2, 6),
    "hops": (3, 8),
    "count": (4, 15),
    "instances": (1, 4),
    "population": (40, 140),
    "baseline_transactions": (40, 220),
}


class StrategyExplorer:
    """Samples the scenario parameter space and scores synthetic realism."""

    def __init__(self, cfg: Optional[RedTeamConfig] = None, seed: Optional[int] = None):
        self.cfg = cfg or default_config
        self.seed = seed if seed is not None else self.cfg.seed
        self._rng = random.Random(self.seed)
        self._sim = FraudSimulator(cfg=self.cfg)

    def explore(self, spec: ScenarioSpec, trials: int = 12) -> ExplorationResult:
        result = ExplorationResult(base_scenario_id=spec.scenario_id)
        for i in range(trials):
            params = self._sample(spec.parameters)
            variant = spec.model_copy(update={"parameters": params})
            scenario = self._sim.run(variant, seed=self.seed + i)
            result.hypotheses.append(
                Hypothesis(
                    parameters={k: params[k] for k in params if k in _SEARCH_SPACE},
                    realism_score=self._realism(scenario),
                    diversity_score=self._diversity(scenario),
                    transaction_count=scenario.num_transactions,
                    account_count=scenario.num_accounts,
                )
            )
        return result

    # ── Sampling ──────────────────────────────────────────────────────────────

    def _sample(self, base: Dict) -> Dict:
        params = dict(base)
        for key in base:
            if key in _SEARCH_SPACE:
                lo, hi = _SEARCH_SPACE[key]
                params[key] = self._rng.randint(int(lo), int(hi))
        return params

    # ── Descriptive scoring (no detector involved) ─────────────────────────────

    @staticmethod
    def _realism(scenario: GeneratedScenario) -> float:
        """
        A heuristic 0..1 'realism' score: fraud should be a believable minority
        embedded in benign activity, and amounts should not be degenerate.
        """
        n = scenario.num_transactions or 1
        fraud_ratio = scenario.fraud_transaction_count / n
        # Most realistic when fraud is a small-but-present minority (~5–25%).
        balance = 1.0 - min(1.0, abs(fraud_ratio - 0.15) / 0.5)
        amounts = [t.amount for t in scenario.transactions] or [0.0]
        spread = statistics.pstdev(amounts) / (statistics.mean(amounts) + 1e-9)
        spread_score = min(1.0, spread / 2.0)  # some dispersion is realistic
        return round(0.6 * balance + 0.4 * spread_score, 4)

    @staticmethod
    def _diversity(scenario: GeneratedScenario) -> float:
        """Diversity = fraction of distinct counterparties and rails exercised."""
        accounts = {t.from_account for t in scenario.transactions} | {
            t.to_account for t in scenario.transactions
        }
        rails = {t.payment_rail for t in scenario.transactions}
        acct_div = min(1.0, len(accounts) / (scenario.num_accounts or 1))
        rail_div = len(rails) / 5.0  # five rails defined
        return round(0.7 * acct_div + 0.3 * rail_div, 4)
