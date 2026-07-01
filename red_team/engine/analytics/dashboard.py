"""
Analytics engine.

Aggregates descriptive metrics across a batch of generated scenarios and emits
both a machine-readable JSON summary and a human-readable Markdown report:

  * scenario count & complexity distribution
  * fraud-category distribution
  * dataset generation statistics (accounts, transactions, volume)
  * synthetic network sizes
  * optional evolution-progress series

The analytics layer is purely observational. It reports on what the Red Team
has produced; it never feeds anything back into the Blue Team.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from red_team.core.config import RedTeamConfig, config as default_config
from red_team.core.models import SYNTHETIC_WATERMARK, GeneratedScenario


class AnalyticsEngine:
    """Computes and renders aggregate metrics over generated scenarios."""

    def __init__(self, cfg: Optional[RedTeamConfig] = None):
        self.cfg = cfg or default_config

    def metrics(self, scenarios: List[GeneratedScenario]) -> Dict:
        complexity = Counter(s.spec.complexity.value for s in scenarios)
        category = Counter(s.spec.category.value for s in scenarios)
        total_txns = sum(s.num_transactions for s in scenarios)
        total_fraud = sum(s.fraud_transaction_count for s in scenarios)
        total_accounts = sum(s.num_accounts for s in scenarios)
        total_volume = round(sum(s.total_volume for s in scenarios), 2)

        return {
            "watermark": SYNTHETIC_WATERMARK,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "scenario_count": len(scenarios),
            "complexity_distribution": dict(complexity),
            "fraud_category_distribution": dict(category),
            "dataset_statistics": {
                "total_accounts": total_accounts,
                "total_transactions": total_txns,
                "fraud_transactions": total_fraud,
                "fraud_ratio": round(total_fraud / total_txns, 4) if total_txns else 0.0,
                "total_synthetic_volume": total_volume,
            },
            "network_sizes": [
                {"scenario_id": s.spec.scenario_id, "accounts": s.num_accounts,
                 "transactions": s.num_transactions}
                for s in scenarios
            ],
        }

    def write_json(self, scenarios: List[GeneratedScenario], filename: str = "analytics.json") -> str:
        out = self.cfg.ensure_output_dir() / filename
        out.write_text(json.dumps(self.metrics(scenarios), indent=2))
        return str(out)

    def write_report(self, scenarios: List[GeneratedScenario], filename: str = "ANALYTICS.md") -> str:
        m = self.metrics(scenarios)
        ds = m["dataset_statistics"]
        lines = [
            "# Red Team — Analytics Dashboard",
            "",
            f"> **{SYNTHETIC_WATERMARK}** — all figures derive from synthetic data only.",
            "",
            f"_Generated {m['generated_at']}_",
            "",
            "## Overview",
            "",
            f"- **Scenarios generated:** {m['scenario_count']}",
            f"- **Total synthetic accounts:** {ds['total_accounts']:,}",
            f"- **Total synthetic transactions:** {ds['total_transactions']:,}",
            f"- **Labelled fraudulent:** {ds['fraud_transactions']:,} "
            f"({ds['fraud_ratio'] * 100:.1f}%)",
            f"- **Total synthetic volume:** {ds['total_synthetic_volume']:,.2f}",
            "",
            "## Complexity Distribution",
            "",
            *[f"- {k}: {v}" for k, v in m["complexity_distribution"].items()],
            "",
            "## Fraud Category Distribution",
            "",
            *[f"- {k}: {v}" for k, v in m["fraud_category_distribution"].items()],
            "",
            "## Synthetic Network Sizes",
            "",
            "| Scenario | Accounts | Transactions |",
            "|----------|---------:|-------------:|",
            *[f"| `{n['scenario_id']}` | {n['accounts']} | {n['transactions']} |"
              for n in m["network_sizes"]],
            "",
        ]
        out = self.cfg.ensure_output_dir() / filename
        out.write_text("\n".join(lines))
        return str(out)
