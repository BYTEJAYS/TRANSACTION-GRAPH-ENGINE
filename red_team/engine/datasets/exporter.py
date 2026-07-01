"""
Dataset generation platform.

Serialises a :class:`GeneratedScenario` to research-friendly artefacts:

  * ``<id>_transactions.csv``  — flat transaction table with ground-truth labels
  * ``<id>_accounts.csv``      — synthetic account roster
  * ``<id>.json``              — full structured scenario (spec + entities + txns)
  * ``<id>_graph.json``        — node/edge graph view for visualisation tools
  * ``<id>_report.md``         — human-readable scenario report

Every file is written under a per-scenario directory inside the configured
output location and carries the synthetic watermark in its provenance fields.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from red_team.core.config import RedTeamConfig, config as default_config
from red_team.core.models import SYNTHETIC_WATERMARK, GeneratedScenario


class DatasetExporter:
    """Writes generated scenarios to disk in multiple formats."""

    def __init__(self, cfg: Optional[RedTeamConfig] = None):
        self.cfg = cfg or default_config

    def export(self, scenario: GeneratedScenario, fmt: str = "all") -> Dict[str, str]:
        out_root = self.cfg.ensure_output_dir()
        sdir = out_root / scenario.spec.scenario_id
        sdir.mkdir(parents=True, exist_ok=True)
        written: Dict[str, str] = {}

        if fmt in ("all", "csv"):
            written["transactions_csv"] = self._transactions_csv(scenario, sdir)
            written["accounts_csv"] = self._accounts_csv(scenario, sdir)
        if fmt in ("all", "json"):
            written["scenario_json"] = self._scenario_json(scenario, sdir)
            written["graph_json"] = self._graph_json(scenario, sdir)
        if fmt in ("all", "report"):
            written["report_md"] = self._report_md(scenario, sdir)

        return written

    # ── Writers ───────────────────────────────────────────────────────────────

    def _transactions_csv(self, scenario: GeneratedScenario, sdir: Path) -> str:
        path = sdir / f"{scenario.spec.scenario_id}_transactions.csv"
        fields = [
            "transaction_id", "from_account", "to_account", "amount", "timestamp",
            "payment_rail", "fraud_category", "is_fraud", "scenario_step", "watermark",
        ]
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for t in scenario.transactions:
                w.writerow({
                    "transaction_id": t.transaction_id,
                    "from_account": t.from_account,
                    "to_account": t.to_account,
                    "amount": t.amount,
                    "timestamp": t.timestamp.isoformat(),
                    "payment_rail": t.payment_rail.value,
                    "fraud_category": t.fraud_category.value,
                    "is_fraud": int(t.is_fraud),
                    "scenario_step": t.scenario_step,
                    "watermark": SYNTHETIC_WATERMARK,
                })
        return str(path)

    def _accounts_csv(self, scenario: GeneratedScenario, sdir: Path) -> str:
        path = sdir / f"{scenario.spec.scenario_id}_accounts.csv"
        fields = ["account_id", "owner_identity_id", "archetype", "home_city", "label", "watermark"]
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for a in scenario.accounts:
                w.writerow({
                    "account_id": a.account_id,
                    "owner_identity_id": a.owner_identity_id,
                    "archetype": a.archetype.value,
                    "home_city": a.home_city,
                    "label": a.label.value,
                    "watermark": SYNTHETIC_WATERMARK,
                })
        return str(path)

    def _scenario_json(self, scenario: GeneratedScenario, sdir: Path) -> str:
        path = sdir / f"{scenario.spec.scenario_id}.json"
        path.write_text(scenario.model_dump_json(indent=2))
        return str(path)

    def _graph_json(self, scenario: GeneratedScenario, sdir: Path) -> str:
        path = sdir / f"{scenario.spec.scenario_id}_graph.json"
        nodes = [
            {"id": a.account_id, "archetype": a.archetype.value, "city": a.home_city}
            for a in scenario.accounts
        ]
        edges: List[Dict] = [
            {
                "source": t.from_account,
                "target": t.to_account,
                "amount": t.amount,
                "rail": t.payment_rail.value,
                "fraud_category": t.fraud_category.value,
                "is_fraud": t.is_fraud,
            }
            for t in scenario.transactions
        ]
        payload = {
            "watermark": SYNTHETIC_WATERMARK,
            "scenario_id": scenario.spec.scenario_id,
            "nodes": nodes,
            "edges": edges,
        }
        path.write_text(json.dumps(payload, indent=2))
        return str(path)

    def _report_md(self, scenario: GeneratedScenario, sdir: Path) -> str:
        path = sdir / f"{scenario.spec.scenario_id}_report.md"
        s = scenario.spec
        lines = [
            f"# Scenario Report — {s.title}",
            "",
            f"> **{SYNTHETIC_WATERMARK}** — synthetic research artefact. "
            "Not derived from any real entity, account, or transaction.",
            "",
            f"- **Scenario ID:** `{s.scenario_id}`",
            f"- **Category:** {s.category.value}",
            f"- **Complexity:** {s.complexity.value}",
            f"- **Seed:** {scenario.seed}",
            f"- **Generated:** {datetime.utcnow().isoformat()}Z",
            "",
            "## Description",
            "",
            s.description,
            "",
            "## Objectives",
            "",
            *[f"- {o}" for o in s.objectives],
            "",
            "## Risk Indicators (ground truth)",
            "",
            *[f"- **{ri.name}** ({ri.severity.value}): {ri.description}" for ri in s.risk_indicators],
            "",
            "## Expected Research Outcomes",
            "",
            *[f"- {o}" for o in s.expected_outcomes],
            "",
            "## Generated Data",
            "",
            f"- Identities: **{len(scenario.identities)}**",
            f"- Accounts: **{scenario.num_accounts}**",
            f"- Transactions: **{scenario.num_transactions}** "
            f"({scenario.fraud_transaction_count} labelled fraudulent)",
            f"- Total synthetic volume: **{scenario.total_volume:,.2f}**",
            "",
        ]
        path.write_text("\n".join(lines))
        return str(path)
