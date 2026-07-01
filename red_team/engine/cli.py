"""
Red Team command-line interface.

Run as a module from the repository root:

    python -m red_team.cli list-scenarios
    python -m red_team.cli generate --scenario A01-multi-stage-laundering
    python -m red_team.cli generate-all
    python -m red_team.cli explore --scenario I01-coordinated-smurfing --trials 12
    python -m red_team.cli evolve --scenario A02-mule-network --generations 8
    python -m red_team.cli report

Every command operates entirely within the Red Team. None of them touch the
Blue Team, any real payment system, or any real data.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List

from red_team.adversarial_research.strategy_explorer import StrategyExplorer
from red_team.analytics.dashboard import AnalyticsEngine
from red_team.core.config import config
from red_team.core.models import GeneratedScenario
from red_team.core.safety import assert_isolation
from red_team.datasets.exporter import DatasetExporter
from red_team.evolution_engine.evolver import EvolutionEngine
from red_team.scenario_library.catalog import ScenarioCatalog
from red_team.simulators.fraud_simulator import FraudSimulator

_BANNER = "TGIE Red Team — synthetic adversarial fraud simulation (isolated from Blue Team)"


def _cmd_list(args, catalog: ScenarioCatalog) -> int:
    print(_BANNER + "\n")
    for s in catalog.all():
        print(f"  [{s.complexity.value:>12}] {s.scenario_id}")
        print(f"               {s.title}  ({s.category.value})")
    return 0


def _cmd_generate(args, catalog: ScenarioCatalog) -> int:
    sim = FraudSimulator(cfg=config)
    exporter = DatasetExporter(cfg=config)
    specs = [catalog.get(args.scenario)] if args.scenario else catalog.all()

    generated: List[GeneratedScenario] = []
    for spec in specs:
        scenario = sim.run(spec, seed=args.seed)
        written = exporter.export(scenario, fmt=args.format)
        generated.append(scenario)
        print(f"✓ {spec.scenario_id}: {scenario.num_transactions} txns "
              f"({scenario.fraud_transaction_count} fraud), {scenario.num_accounts} accounts")
        for kind, path in written.items():
            print(f"    {kind}: {path}")

    analytics = AnalyticsEngine(cfg=config)
    analytics.write_json(generated)
    analytics.write_report(generated)
    print(f"\nWrote analytics summary to {config.output_dir}")
    return 0


def _cmd_explore(args, catalog: ScenarioCatalog) -> int:
    spec = catalog.get(args.scenario)
    explorer = StrategyExplorer(cfg=config, seed=args.seed)
    result = explorer.explore(spec, trials=args.trials)
    print(f"Explored {args.trials} parameter variants of {spec.scenario_id}\n")
    print(json.dumps(result.ledger()[:10], indent=2))
    best = result.best()
    if best:
        print(f"\nBest combined score: {best.combined_score}  params={best.parameters}")
    return 0


def _cmd_evolve(args, catalog: ScenarioCatalog) -> int:
    spec = catalog.get(args.scenario)
    engine = EvolutionEngine(cfg=config, seed=args.seed)
    report = engine.evolve(spec, generations=args.generations)
    print(json.dumps(report.as_dict(), indent=2))

    # Materialise + export the evolved scenario so it joins the dataset corpus.
    evolved = engine.evolved_spec(spec, report)
    catalog.register(evolved)
    scenario = FraudSimulator(cfg=config).run(evolved, seed=args.seed)
    DatasetExporter(cfg=config).export(scenario)
    print(f"\n✓ Evolved scenario exported as {evolved.scenario_id}")
    return 0


def _cmd_report(args, catalog: ScenarioCatalog) -> int:
    sim = FraudSimulator(cfg=config)
    generated = [sim.run(s, seed=args.seed) for s in catalog.all()]
    analytics = AnalyticsEngine(cfg=config)
    jpath = analytics.write_json(generated)
    mpath = analytics.write_report(generated)
    print(f"✓ analytics JSON:   {jpath}")
    print(f"✓ analytics report: {mpath}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="red_team", description=_BANNER)
    p.add_argument("--seed", type=int, default=config.seed, help="Deterministic seed.")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list-scenarios", help="List all scenarios in the catalog.")

    g = sub.add_parser("generate", help="Generate one scenario's dataset.")
    g.add_argument("--scenario", required=True, help="Scenario ID (see list-scenarios).")
    g.add_argument("--format", default="all", choices=["all", "csv", "json", "report"])

    sub.add_parser("generate-all", help="Generate datasets for every scenario.")

    e = sub.add_parser("explore", help="Explore a scenario's parameter space.")
    e.add_argument("--scenario", required=True)
    e.add_argument("--trials", type=int, default=12)

    v = sub.add_parser("evolve", help="Evolve a scenario for realism + diversity.")
    v.add_argument("--scenario", required=True)
    v.add_argument("--generations", type=int, default=8)

    sub.add_parser("report", help="Write an aggregate analytics report.")
    return p


def main(argv: List[str] | None = None) -> int:
    assert_isolation()  # defence-in-depth: refuse to run if coupled to Blue Team
    parser = build_parser()
    args = parser.parse_args(argv)
    catalog = ScenarioCatalog()

    if args.command == "list-scenarios":
        return _cmd_list(args, catalog)
    if args.command == "generate":
        return _cmd_generate(args, catalog)
    if args.command == "generate-all":
        args.scenario = None
        args.format = "all"
        return _cmd_generate(args, catalog)
    if args.command == "explore":
        return _cmd_explore(args, catalog)
    if args.command == "evolve":
        return _cmd_evolve(args, catalog)
    if args.command == "report":
        return _cmd_report(args, catalog)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
