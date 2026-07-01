"""
Fraud simulation engine.

Materialises a :class:`ScenarioSpec` into a fully populated
:class:`GeneratedScenario`: it builds a synthetic population, lays down a
baseline of benign activity, then injects the fraud topology described by the
scenario's category and parameters.

The simulator is the single orchestration point that ties the synthetic-data
generators to the scenario library. It is deterministic for a given seed.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from red_team.core.config import RedTeamConfig, config as default_config
from red_team.core.models import (
    FraudCategory,
    GeneratedScenario,
    Provenance,
    ScenarioSpec,
    SyntheticTransaction,
)
from red_team.core.safety import verify_all_synthetic
from red_team.synthetic_data.identity_generator import IdentityGenerator
from red_team.synthetic_data.transaction_patterns import TransactionPatternGenerator


class FraudSimulator:
    """Turns scenario specifications into labelled synthetic datasets."""

    def __init__(self, cfg: Optional[RedTeamConfig] = None):
        self.cfg = cfg or default_config

    def run(self, spec: ScenarioSpec, seed: Optional[int] = None) -> GeneratedScenario:
        seed = seed if seed is not None else self.cfg.seed
        params = spec.parameters or {}

        # 1. Build the synthetic population.
        idgen = IdentityGenerator(cfg=self.cfg, seed=seed)
        pop_size = int(params.get("population", self.cfg.default_identity_count))
        identities, accounts = idgen.population(
            identity_count=pop_size,
            mule_fraction=float(params.get("mule_fraction", 0.18)),
            shell_fraction=float(params.get("shell_fraction", 0.05)),
        )

        # 2. Lay down a benign baseline so fraud is embedded in realistic noise.
        txgen = TransactionPatternGenerator(accounts, cfg=self.cfg, seed=seed)
        transactions: List[SyntheticTransaction] = []
        baseline = int(params.get("baseline_transactions", 40))
        if baseline > 0:
            transactions.extend(txgen.normal_activity(baseline))

        # 3. Inject the fraud topology for this scenario's category.
        injector = self._dispatch(spec.category)
        if injector is not None:
            for _ in range(int(params.get("instances", 1))):
                transactions.extend(injector(txgen, params))

        # 4. Stamp + audit, then assemble the result.
        scenario = GeneratedScenario(
            spec=spec,
            identities=identities,
            accounts=accounts,
            transactions=transactions,
            seed=seed,
            provenance=Provenance(seed=seed),
        )
        verify_all_synthetic(scenario.transactions)
        verify_all_synthetic(scenario.accounts)
        return scenario

    # ── Category → generator dispatch ─────────────────────────────────────────

    def _dispatch(
        self, category: FraudCategory
    ) -> Optional[Callable[[TransactionPatternGenerator, Dict], List[SyntheticTransaction]]]:
        table: Dict[FraudCategory, Callable] = {
            FraudCategory.NORMAL: None,
            FraudCategory.CIRCULAR_FLOW: lambda g, p: g.circular_flow(int(p.get("depth", 3))),
            FraudCategory.SMURFING: lambda g, p: g.smurfing_fan_out(int(p.get("recipients", 8))),
            FraudCategory.LAYERING: lambda g, p: g.layering(int(p.get("layers", 3)), int(p.get("split", 3))),
            FraudCategory.TRANSACTION_LAUNDERING: lambda g, p: g.layering(int(p.get("layers", 4)), int(p.get("split", 4))),
            FraudCategory.MULE_NETWORK: lambda g, p: g.mule_chain(int(p.get("hops", 4))),
            FraudCategory.STRUCTURING: lambda g, p: g.structuring(int(p.get("count", 6))),
            FraudCategory.ACCOUNT_TAKEOVER: lambda g, p: g.account_takeover_burst(int(p.get("count", 10))),
            FraudCategory.SYNTHETIC_IDENTITY: lambda g, p: g.smurfing_fan_out(int(p.get("recipients", 5))),
            FraudCategory.IDENTITY_FRAUD: lambda g, p: g.account_takeover_burst(int(p.get("count", 6))),
            FraudCategory.INSIDER_ABUSE: lambda g, p: g.structuring(int(p.get("count", 5))),
        }
        return table.get(category)
