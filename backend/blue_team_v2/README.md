# Blue Team V2 — Next-Generation Fraud Intelligence Engine

> **Experimental.** Blue Team V2 is an *independent, opt-in* intelligence layer for
> TGIE. It does **not** replace, modify, or depend on the production `blue_team`
> package. Production behaviour is unchanged until V2 is explicitly selected and
> validated. See [`docs/MIGRATION.md`](docs/MIGRATION.md).

Blue Team V2 behaves like a professional bank/AML fraud-intelligence platform
rather than a simple graph-risk calculator. Every node gets an **independent**
18-factor analysis, every cluster gets an **auto-generated role hierarchy**, and
every score is **explainable** with a faithful contributor breakdown.

---

## Why V2 exists — problems it fixes

| Symptom in the old engine | How V2 fixes it |
|---|---|
| Identical risk scores across a whole cluster | Per-node 18-factor scoring + structural role base → every node scores independently |
| Every node looks equally risky | Evidence-driven scoring; periphery and origin land far apart |
| Shallow fraud propagation | Risk inheritance diffuses from origins with decay along money-flow |
| Placeholder-like scoring | 11 amount-gated detectors produce *evidence*, not just numbers |
| Weak explanations | Explanation engine: contributors, classifications, narrative |
| Limited graph understanding | Origin discovery, bridges, cycles, layering chains, cash-out tracing |

### Measured result (10 fraud + 10 normal clusters, 5 seeds)

| Metric | Blue Team V1 | **Blue Team V2** |
|---|---|---|
| Graph F1 | 0.76 | **0.96** |
| Node F1 | 0.83 | **0.96** |
| False positives (avg) | 6.4 | **0.8** |
| Processing time | ~170 ms | **~12 ms** |

Run it yourself: `python -m blue_team_v2 benchmark`

---

## Architecture

```
component (TGIE snapshot)
        │
        ▼
core/graph_engine     build isolated working graph + primitives
core/risk_engine      18-factor NodeMetrics for every node
core/anomaly_engine   velocity · burst · dormancy
core/cluster_engine   origin discovery + role hierarchy
detectors/*           11 evidence-producing fraud detectors
core/pattern_engine   orchestrate detectors → evidence + hybrid meta
core/scoring_engine   independent per-node score + contributions
ai/*                  classify · explain · cluster narrative
        │
        ▼
engine.py  →  ClusterAnalysis (rich)
        │
        ▼
adapter.py →  TGIE-compatible verdict  (+ additive `v2` block)
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full breakdown.

---

## The 18 node factors

velocity · frequency · incoming volume · outgoing volume · fan-in · fan-out ·
degree centrality · betweenness · closeness · fraud distance · layer distance ·
circular participation · burst activity · historical behaviour · risk
inheritance · pattern participation · bridge importance · cluster role.

## Cluster roles (auto-assigned)

origin · collection · distribution · bridge · mule · cashout · sink · terminal ·
circular · layering · pass-through · peripheral · normal.

## Detector library

layering · smurfing/structuring · circular flow · fan-out · fan-in · mule
networks · bridge accounts · velocity/burst · cash-out · dormant reactivation ·
synthetic rings · hybrid networks (meta).

---

## ML models — what TGIE uses and where

Blue Team V2 is, **by design, a deterministic heuristic engine** — not a trained
model. Every verdict comes from the 18-factor scoring engine and the 11
evidence-producing detectors above, with no `.fit()`/`.predict()` step. This is a
deliberate trade-off: it is **fully explainable** (every score has a faithful
contributor breakdown), **fast** (~12 ms/cluster), and needs **no training data
or model artifacts** — which is why it ships with no ML dependency beyond
`networkx`.

TGIE's **machine-learning layer is a separate stage in the main backend**, applied
*before* clusters reach Blue Team. Those models are real and trained at runtime
on the synthetic transaction stream:

| Model | Library | Role | Location |
|---|---|---|---|
| **Isolation Forest** (`n_estimators=100`, configurable contamination, `StandardScaler` inputs) | scikit-learn | Unsupervised per-transaction anomaly score (0–1) over velocity/amount/time features | `backend/anomaly_detection/isolation_forest_detector.py` |
| **XGBoost** (`XGBClassifier`, 200 trees, depth 4) | xgboost | **Supervised** fraud probability (0–1) over the same 12-feature vector; trained at start-up on a synthetic labelled set (holdout AUC ≈ 0.93) | `backend/ml/xgboost_classifier.py` |
| **SHAP — TreeExplainer** | shap | Per-prediction feature attribution explaining *why* the Isolation Forest scored a node anomalous | `backend/anomaly_detection/shap_explainer.py` |
| **GraphSAGE GNN** + **GAT** layers (`SAGEConv`/`GATConv`); plus a SAGE encoder–decoder `GraphAnomalyDetector` | PyTorch Geometric | **Optional/experimental** graph-level node embeddings + reconstruction-based anomaly detection | `backend/ml/gnn_model.py` |

> The supervised (**XGBoost**) and unsupervised (**Isolation Forest**) models share
> the exact 12-feature vector from `FeatureExtractor`, so the same evidence drives
> both. Blue Team V2 itself stays deliberately heuristic — it consumes these
> signals but adds no opaque model of its own, keeping every verdict explainable.

---

## Usage

### Drop-in (same signature as `blue_team.adapter`)
```python
from blue_team_v2.adapter import analyze_all_components
verdicts = await analyze_all_components(components)   # list[dict] in V1 schema
```

### Rich programmatic access
```python
from blue_team_v2 import BlueTeamV2Engine
analysis = BlueTeamV2Engine().analyze_component(component)
print(analysis.narrative, analysis.cluster.to_dict())
```

### Engine router (V1 ↔ V2 toggle)
```python
from blue_team_v2.router import route_all_components
# selection: arg > ACTIVE_BLUE_TEAM env > default "v1"
verdicts = await route_all_components(components, engine="v2")
```
```bash
export ACTIVE_BLUE_TEAM=v2   # route production traffic to V2
```

### Shadow mode (run both, compare)
```python
from blue_team_v2.shadow import run_shadow
comparison = await run_shadow(components)   # {v1, v2, comparison, agreement}
```

### CLI
```bash
python -m blue_team_v2 demo        # analyse a sample hybrid fraud cluster
python -m blue_team_v2 benchmark   # V1 vs V2 benchmark report
python -m blue_team_v2 shadow      # side-by-side shadow comparison
python -m blue_team_v2 scale 100 1000 10000 50000
```

### Optional API endpoints (additive, never overrides existing routes)
```python
from blue_team_v2.api import router as blue_team_v2_router
app.include_router(blue_team_v2_router)   # adds /api/v2/*
```

---

## Output contract (backward compatibility)

`adapter.analyze_*` returns **exactly** the V1 verdict schema, so every existing
consumer (graph rendering, risk badges, fraud labels, hover panels, AI assistant,
analytics dashboard, cluster view) keeps working unchanged:

```json
{ "graph_id", "status", "verdict", "risk_score", "flagged",
  "flagged_nodes", "suspicious_reason", "transactions_scored", "nodes", "mode",
  "v2": { …additive richer intelligence, ignored by V1 consumers… } }
```

`verdict ∈ {CLEAN, LOGGED, SUSPICIOUS, FRAUD}` — identical to V1.

---

## Tests

```bash
pytest blue_team_v2/tests -q     # 21 tests: contract, no-blanket-scoring,
                                 # per-archetype detection, isolation, router, shadow
```

## Safety guarantees

- Never imports or mutates the production `blue_team` package.
- Defaults to V1 everywhere — V2 is strictly opt-in.
- Each component analysed in isolation → no phantom edges / cross-cluster contamination.
- No new hard dependencies beyond what TGIE already uses (`networkx`).
