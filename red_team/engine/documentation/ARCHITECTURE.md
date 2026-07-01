# Red Team — System Architecture

The Red Team is a layered, deterministic pipeline. Data flows in one direction:
a declarative scenario specification is materialised into synthetic entities and
transactions, optionally explored/evolved for realism, then exported and
analysed. **No stage communicates with the Blue Team.**

```
ScenarioSpec ──▶ FraudSimulator ──▶ GeneratedScenario ──▶ DatasetExporter ──▶ files
     ▲                │                      │
     │                ▼                      ▼
ScenarioCatalog   synthetic_data        AnalyticsEngine
     ▲          (identities + txns)
     │
EvolutionEngine ◀── StrategyExplorer   (both score realism/diversity only)
```

## Layers

### 1. Core (`core/`)
- **`models.py`** — Pydantic models for every artefact. Independent of Blue Team
  models by design. Every model carries a `Provenance` watermark.
- **`config.py`** — `RedTeamConfig`: seed, output directory, locale, population
  defaults. Reads only `REDTEAM_*` environment variables.
- **`safety.py`** — isolation enforcement (`assert_isolation`) and synthetic
  provenance helpers (`stamp`, `verify_all_synthetic`).

### 2. Synthetic Data Engine (`synthetic_data/`)
- **`identity_generator.py`** — fictional customers/businesses, KYC profiles,
  device fingerprints, behavioural profiles, and accounts via `faker`.
- **`transaction_patterns.py`** — labelled transaction-graph topologies
  (normal, circular, smurfing/fan-out, layering, mule chain, structuring,
  account-takeover burst) plus a `networkx` view.

### 3. Simulation Engine (`simulators/`)
- **`fraud_simulator.py`** — orchestrates a `ScenarioSpec` into a fully
  populated `GeneratedScenario`: build population → benign baseline → inject
  fraud topology → stamp & audit. Deterministic per seed.

### 4. Scenario Library (`scenario_library/`)
- **`catalog.py`** — curated specs across three complexity tiers, plus a
  runtime `register()` for evolved scenarios.

### 5. Adversarial Research (`adversarial_research/`)
- **`strategy_explorer.py`** — samples a scenario's numeric parameter space and
  scores each variant's **realism** and **diversity**. Research only — no
  detector in the loop, no actionable fraud instructions.

### 6. Evolution Engine (`evolution_engine/`)
- **`evolver.py`** — a genetic-algorithm loop (seed → evaluate → select →
  crossover → mutate) whose fitness is the same realism/diversity heuristic.
  Goal: a richer, more varied scenario library.

### 7. Analytics (`analytics/`)
- **`dashboard.py`** — aggregate metrics (scenario counts, category/complexity
  distributions, dataset statistics, network sizes) rendered to JSON + Markdown.

### 8. Dataset Platform (`datasets/`)
- **`exporter.py`** — writes per-scenario CSV, JSON, graph JSON, and a Markdown
  report; also the default output directory.

## Determinism

Every stochastic component is driven by a single seed sourced from
`RedTeamConfig.seed` (default `1337`, override with `--seed` or `REDTEAM_SEED`).
The same seed reproduces the same datasets byte-for-byte in the labelled fields.
