# Blue Team V2 — Architecture

## Pipeline

A single TGIE component (`{graph_id, node_ids, nodes[], edges[]}`) flows through:

1. **Graph Engine** (`core/graph_engine/builder.py`)
   Builds an isolated `networkx.DiGraph`, aggregating parallel transfers per
   ordered pair (summed amount, count, sorted timestamps, rails). Provides
   primitives: in/out volume, cycles (length-bounded on big graphs),
   articulation points, longest forwarding chain, centralities, fraud distances.
   *Only the given component is ever loaded → no cross-cluster contamination.*

2. **Risk Engine** (`core/risk_engine/node_intelligence.py`)
   Computes the 18-factor `NodeMetrics` per node and diffuses **risk inheritance**
   from origins outward along money-flow with 0.55 decay over 3 hops.

3. **Anomaly Engine** (`core/anomaly_engine/anomalies.py`)
   Temporal signals: log-compressed **velocity**, Fano-style **burstiness**, and
   **dormancy reactivation** (requires an absolute multi-hour quiet gap, so rapid
   bursts never masquerade as reactivation).

4. **Cluster Engine** (`core/cluster_engine/roles.py`)
   Discovers origins (low inflow + material outflow + downstream reach) and
   assigns each node a dominant **role** plus all qualifying traits. Roles carry
   a *mild* structural base risk — a prior, never a verdict.

5. **Detectors** (`detectors/*`) via **Pattern Engine** (`core/pattern_engine`)
   11 detectors, each **amount-gated** and each returning `Evidence`
   (implicated nodes, severity, confidence, structured data). Participation is
   written back into every node; a hybrid meta-finding fires when ≥3 distinct
   technique families co-occur.

6. **Scoring Engine** (`core/scoring_engine/scorer.py`)
   Independent per-node score: `base + (1-base)·f(earned factors)`. Weighting is
   **evidence-driven** — amount-gated pattern participation, fraud proximity, and
   temporal anomalies dominate; raw topology (centrality, bare fan degree) is a
   minor tie-breaker because it saturates on small benign clusters. Emits a
   normalized contributor map (faithful "why").

7. **AI Layer** (`ai/*`)
   `fraud_reasoning` → primary/secondary classification; `explanation_engine` →
   per-node + cluster narrative + contributor summary; `cluster_analysis` →
   investigator summary object for the assistant/UI.

8. **Engine** (`engine.py`) aggregates everything into a `ClusterAnalysis`.

9. **Adapter** (`adapter.py`) projects it to the **exact V1 verdict schema**,
   appending an additive `v2` intelligence block.

## Why scores differentiate (no blanket scoring)

Three independent sources of per-node variation stack:
- **Role base** — origin 0.30 vs peripheral 0.04.
- **Position** — fraud proximity (hops from origin), layer depth, bridge importance.
- **Behaviour** — own velocity, burst, pass-through ratio, inherited risk.

Two nodes in the same ring therefore almost never collapse to one number.

## Scalability

Expensive enumerations are size-bounded:
- `simple_cycles` uses `length_bound=8` above 4k edges.
- `longest_chain` samples the top-400 out-degree sources on cyclic graphs.
- Origin discovery computes full descendant reach only for the top-50 emitters.
- Betweenness switches to k-sampling above 1.5k nodes.

Targets 100 → 100,000+ nodes without redesign (see `python -m blue_team_v2 scale`).

## Module map

```
blue_team_v2/
├── types.py                 shared dataclasses/enums (no internal imports)
├── engine.py                orchestrator → ClusterAnalysis
├── adapter.py               → TGIE-compatible verdict (+ v2 block)
├── router.py                V1↔V2 selection (ACTIVE_BLUE_TEAM)
├── shadow.py                run both engines, compare
├── validation_panel.py      developer comparison metrics
├── api.py                   optional additive FastAPI router (/api/v2/*)
├── __main__.py              CLI (benchmark/demo/shadow/scale)
├── core/                    graph/risk/anomaly/cluster/pattern/scoring engines
├── detectors/               11 evidence-producing detectors
├── ai/                      explanation / fraud_reasoning / cluster_analysis
├── simulation/              labelled synthetic dataset generators
├── benchmark/               automated V1-vs-V2 scoring + report
├── tests/                   pytest suite (21 tests)
└── docs/                    this folder
```
