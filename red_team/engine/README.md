# TGIE Red Team — Adversarial Fraud Simulation Platform

> **A controlled cyber range for financial fraud research.**
> Mission: *discover weaknesses before criminals do* — using only synthetic,
> explainable, reproducible, and auditable simulations.

The Red Team is a **standalone research environment** inside TGIE. It generates
realistic *synthetic* fraud scenarios, produces research datasets, and evolves
simulation complexity over time. It never facilitates real-world fraud and it
never touches real financial systems or real data.

---

## ⛔ Isolation Contract

The Red Team is **completely isolated** from the Blue Team (fraud detection).
This separation is intentional and enforced:

- ❌ No imports from `blue_team`, `anomaly_detection`, or `graph_engine`
- ❌ No shared databases, model weights, datasets, or APIs
- ❌ No feedback loop, retraining pipeline, or adversarial self-learning against the detector
- ✅ `red_team.core.safety.assert_isolation()` runs at import and refuses to start if the contract is broken

Future integration may happen in later TGIE versions, but it is **explicitly out
of scope** here. See [`documentation/ETHICS_AND_SAFETY.md`](documentation/ETHICS_AND_SAFETY.md).

---

## Architecture

```
red_team/
├── core/                  # models, config, safety/isolation guardrails
├── synthetic_data/        # synthetic identities + transaction-graph generators
├── simulators/            # fraud simulation engine (spec → dataset)
├── scenario_library/      # expandable catalog of beginner/intermediate/advanced scenarios
├── adversarial_research/  # parameter-space exploration (research only)
├── evolution_engine/      # GA loop that improves scenario realism & diversity
├── analytics/             # aggregate metrics + dashboard reporting
├── datasets/              # generated output (CSV / JSON / graph / report)
└── documentation/         # architecture, methodology, ethics, roadmap
```

Each generated artefact carries a `TGIE-RED-TEAM-SYNTHETIC` watermark in its
provenance so it can never be mistaken for real data in an audit.

---

## Quick start

```bash
# from the repository root, using the backend's Python environment
python -m red_team.cli list-scenarios

# generate one scenario's dataset (CSV + JSON + graph + report)
python -m red_team.cli generate --scenario A01-multi-stage-laundering

# generate datasets for every scenario + an analytics summary
python -m red_team.cli generate-all

# explore a scenario's parameter space, scoring realism & diversity
python -m red_team.cli explore --scenario I01-coordinated-smurfing --trials 12

# evolve a scenario for higher realism + diversity (Red-Team-internal fitness)
python -m red_team.cli evolve --scenario A02-mule-network --generations 8

# write an aggregate analytics report across all scenarios
python -m red_team.cli report
```

All commands are **deterministic** for a given `--seed` (default `1337`).

### Programmatic use

```python
from red_team.scenario_library import ScenarioCatalog
from red_team.simulators import FraudSimulator
from red_team.datasets import DatasetExporter

spec = ScenarioCatalog().get("A01-multi-stage-laundering")
scenario = FraudSimulator().run(spec, seed=42)
paths = DatasetExporter().export(scenario)
print(scenario.summary())
```

---

## Scenario library

| Tier | ID | Topic |
|------|----|-------|
| Beginner | `B01-single-suspicious-transfer` | Sub-threshold structuring |
| Beginner | `B02-account-takeover-burst` | Behavioural-baseline deviation |
| Intermediate | `I01-coordinated-smurfing` | Fan-out / out-degree anomaly |
| Intermediate | `I02-circular-flow` | Cycle detection |
| Intermediate | `I03-synthetic-identity-ring` | Synthetic-identity clustering |
| Advanced | `A01-multi-stage-laundering` | Placement → layering → integration |
| Advanced | `A02-mule-network` | Overlapping mule chains |
| Advanced | `A03-hybrid-operation` | Multi-vector blended operation |

Adding a scenario is a one-line append to `scenario_library/catalog.py`.

---

## Documentation

- [`documentation/ARCHITECTURE.md`](documentation/ARCHITECTURE.md)
- [`documentation/METHODOLOGY.md`](documentation/METHODOLOGY.md)
- [`documentation/ETHICS_AND_SAFETY.md`](documentation/ETHICS_AND_SAFETY.md)
- [`documentation/ROADMAP.md`](documentation/ROADMAP.md)

---

## Dependencies

Python 3.11+, `pydantic`, `numpy`, `pandas`, `networkx`, `faker`
(`pip install -r red_team/requirements.txt`). These are the Red Team's own
direct dependencies — it imports nothing from the Blue Team backend.
