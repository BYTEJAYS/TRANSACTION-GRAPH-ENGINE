# Red Team — Fraud Simulation Methodology

This document describes *how* the platform models fraud. The intent is research
fidelity: the synthetic data should exhibit the **statistical and topological
signatures** of real fraud so that detection methodologies can be stress-tested,
**without** the platform ever describing how to perpetrate fraud in the real
world.

## Principle: model the shape, not the act

The platform models money movement as a graph of synthetic accounts and
transactions. It reproduces the *observable shape* of fraud — graph topology,
timing, amount dispersion, counterparty structure — and labels each artefact
with ground truth. It never produces operational steps, credentials, document
forgery techniques, or any real-world-actionable procedure.

## Scenario lifecycle

1. **Specify** — a `ScenarioSpec` declares category, complexity, objectives,
   ground-truth risk indicators, expected outcomes, and parameters.
2. **Populate** — `IdentityGenerator` builds a coherent population of synthetic
   identities and accounts, including a configurable fraction of mule/shell
   archetypes.
3. **Baseline** — a layer of benign activity is laid down so fraud is embedded
   in realistic noise (avoiding trivially-separable datasets).
4. **Inject** — the fraud topology for the scenario's category is added with
   ground-truth labels (`is_fraud`, `fraud_category`, `scenario_step`).
5. **Audit** — every artefact is verified to carry the synthetic watermark.
6. **Export** — CSV / JSON / graph / report.

## Modelled topologies

| Category | Signature modelled |
|----------|--------------------|
| Structuring | Amounts clustered just below round reporting thresholds; repeated counterparty |
| Smurfing / fan-out | One source → many recipients in near-equal shares (high out-degree) |
| Circular flow | Directed cycle returning value to origin with per-hop decay |
| Layering / laundering | Multi-layer split across intermediaries then reconsolidation |
| Mule network | Linear hop chains through shared mule accounts (community structure) |
| Account takeover | Sudden large-amount, high-velocity deviation from a baseline |
| Synthetic identity | Thin-file KYC, shared device fingerprints, anomaly flags |

## Realism & diversity scoring

Both the research engine and the evolution engine score datasets with two
**purely descriptive** heuristics computed from the synthetic data alone:

- **Realism** — fraud should be a believable minority (~5–25%) of activity, and
  amounts should show non-degenerate dispersion.
- **Diversity** — fraction of distinct counterparties and payment rails
  exercised.

These scores never involve the Blue Team detector. They measure dataset quality,
not evasion.

## Reproducibility & auditability

- Single-seed determinism across the whole pipeline.
- Ground-truth labels on every transaction enable precision/recall evaluation of
  *any* detection methodology a researcher chooses to test (separately).
- Watermarked provenance on every artefact supports audit.
