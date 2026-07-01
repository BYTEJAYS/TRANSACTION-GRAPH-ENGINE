# Phase 5 — ML Engine (DESIGN DOC, for approval)

> Status: **APPROVED · Wave A BUILT & VERIFIED.** Platform in `backend/ml/platform/` (interfaces, registry, features, ensemble, drift, explain, training) + `backend/ml/models/` (random_forest, isolation_forest, xgboost-graceful). Verified on sklearn-only env (xgboost/shap/lightgbm absent → fallbacks exercised): training CLI ensemble ROC-AUC **0.933 ≥ 0.85 gate** → registered active; 6 platform tests + full regression **47 passed**. Wave B (graph/community + structural_ml hooks) and Wave C (real GNNs) pending optional libs / Neo4j.
> Sign-off: ML as capped risk factor (weight 0 default) ✅ · Wave-A-first ✅ · local artifact storage (`ml/_artifacts/`) ✅
> Builds on: Phase 3 (Postgres/Redis for feature store + registry metadata), Phase 4 (Wave 3 `structural_ml` detector hooks call into this engine).
> Iron rule: **ONLY ADD.** The shipped `IsolationForest`, `XGBoost`, `SHAP`, and the `blue_team_v2/ai/*` reasoners are preserved and *registered* into the new platform — not rewritten. Everything degrades gracefully when an optional lib (lightgbm/torch/torch_geometric/lime) is absent, exactly like the current xgboost/gnn fallbacks.

---

## 1. Goals
1. Turn ad-hoc, per-boot models into a **governed ML platform**: feature store → model registry → scoring → explainability → drift monitoring → retraining.
2. Add the missing model families behind **clean, swappable interfaces** (Random Forest, LightGBM, Autoencoder, Node2Vec, GraphSAGE/GCN/GAT, Temporal GNN, community/link-prediction) with real impls where libs exist and graceful fallbacks where they don't.
3. Produce a **calibrated ensemble risk score** that feeds the existing `risk_engine` as *one additional factor* — ML never overrides the explainable rule-based gate.
4. Make every ML output **explainable** (SHAP + LIME + reason codes) under one contract.
5. Wire the Phase 4 **Wave 3 `structural_ml` detectors** (community, clique, motif, embeddings, temporal) to this engine, with NetworkX fallbacks so they work before the heavy models land.

## 2. Current state (audited)
- `anomaly_detection/isolation_forest_detector.py` — real sklearn IF + `FeatureExtractor` (12 features, `FEATURE_NAMES`), rolling per-account history. **Keep as the canonical feature definition.**
- `ml/xgboost_classifier.py` — real XGBoost, synthetic labelled training, graceful fallback (handles missing libomp). **Keep, register.**
- `ml/gnn_model.py` — PyG GraphSAGE/GAT, but torch_geometric absent → `main.py` logs `"rule-based fallback"`. **Becomes a real impl behind the GraphModel interface; fallback preserved.**
- `anomaly_detection/shap_explainer.py` — SHAP. **Keep, fold into unified Explanation.**
- `blue_team_v2/ai/{cluster_analysis,explanation_engine,fraud_reasoning}` — rule-based NLG/reasoning. **Keep; the ML explanation feeds these.**
- Gaps: no persisted artifacts, no registry, no feature store, no drift/retraining, models rebuilt every boot.

## 3. Target architecture
```
backend/ml/                      # existing files preserved
  xgboost_classifier.py          # kept; registered as a wrapped estimator
  gnn_model.py                   # kept; becomes GraphModel impl
  platform/                      # NEW — the governed ML platform
    interfaces.py                # Model / GraphModel / Explainer / DriftMonitor Protocols
    registry.py                  # versioned artifacts (models/<name>/<version>/) + metadata (Postgres ml_models)
    feature_store.py             # online (Redis: per-account rolling vector) + offline (Postgres/parquet)
    features.py                  # canonical feature spec = FEATURE_NAMES + graph features (degree/betweenness/embedding)
    ensemble.py                  # RiskEnsemble — calibrated blend of model scores → [0,1] + reason codes
    drift.py                     # PSI / KS feature drift + performance monitor → retrain trigger
    explain.py                   # unified Explanation (SHAP + LIME + rule reason codes)
    training.py                  # retraining pipeline (callable as Celery task or CLI)
  models/                        # NEW — estimator wrappers behind interfaces.Model
    isolation_forest.py random_forest.py xgboost.py lightgbm.py autoencoder.py
  graph/                         # NEW — graph ML behind interfaces.GraphModel
    node2vec.py graphsage.py gcn.py gat.py temporal_gnn.py community.py link_prediction.py
blue_team_v2/detectors/structural_ml/   # Phase 4 Wave 3 hooks → call ml.graph.* (nx fallback)
```

## 4. Core interfaces (the contract everything implements)
```python
class Model(Protocol):
    name: str; version: str
    def fit(self, X, y=None) -> "Model": ...
    def predict_proba(self, X) -> np.ndarray: ...   # fraud probability [0,1]
    def explain(self, x) -> Explanation: ...
    def available(self) -> bool: ...                # False if optional lib missing

class GraphModel(Protocol):
    def embed(self, G) -> dict[str, np.ndarray]: ...        # node → vector
    def score_nodes(self, G) -> dict[str, float]: ...
    def communities(self, G) -> dict[str, int]: ...
    def available(self) -> bool: ...
```
`Explanation` = `{score, reason_codes:[(feature, contribution)], shap:{...}, lime:{...}, narrative}` — one shape consumed by the evidence builder (Phase 8) and the explainability panel (Phase 7).

## 5. Model families (Part 5 coverage)
| Model | Lib | Impl plan | Fallback |
|---|---|---|---|
| Isolation Forest | sklearn ✓ | wrap existing | — |
| Random Forest | sklearn ✓ | new wrapper | — |
| XGBoost | xgboost ✓ | wrap existing | already graceful |
| LightGBM | lightgbm (opt) | new wrapper | → XGBoost/RF |
| Autoencoder (recon-error anomaly) | torch (opt) / sklearn MLP | new | sklearn `MLPRegressor` recon error |
| Node2Vec | node2vec/gensim (opt) | random-walk + skip-gram | numpy random-walk + truncated-SVD embedding |
| GraphSAGE / GCN / GAT | torch_geometric (opt) | promote `gnn_model.py` | feature-propagation (1-hop mean) embedding |
| Temporal GNN | torch_geometric (opt) | time-bucketed snapshots | EWMA over per-bucket node features |
| Community detection | networkx ✓ | Louvain/greedy modularity | greedy modularity (always present) |
| Link prediction | networkx ✓ | Adamic-Adar / Jaccard | same |
| Ensemble | — | logistic/weighted blend, isotonic calibration | mean of available models |

## 6. Feature store
- **Canonical feature spec** = the existing 12 `FEATURE_NAMES` + graph features (degree/betweenness/closeness from `TransactionGraph.centralities`, plus node embedding when available). One `features.py` so training and serving never skew.
- **Online** (Redis): per-account rolling feature vector, updated on ingest — sub-ms serving for live scoring. Falls back to in-process `FeatureExtractor` history (today's behaviour) when Redis absent.
- **Offline** (Postgres/parquet): materialized feature snapshots for training + drift baselines.

## 7. Model registry
- Artifacts: `models/<name>/<version>/model.pkl` (+ scaler, metadata.json). Metadata row in Postgres `ml_models(name, version, metrics, created_at, status[shadow|active|retired])`.
- `registry.load(name)` returns the **active** version; `promote(name, version)` flips active after shadow eval beats incumbent (mirrors the existing `blue_team_v2/shadow.py` discipline).
- Solves "rebuilt every boot": train once → persist → load.

## 8. Ensemble & how it feeds the risk engine
- `RiskEnsemble.score(account/cluster)` blends available model probabilities → a single calibrated `ml_risk ∈ [0,1]` + reason codes.
- This is injected into `risk_engine` as **one additional, capped factor** (like any other) — it **cannot** single-handedly open a case (preserves the no-single-factor-trips philosophy). Config-gated weight in `risk_engine/config.py`.

## 9. Explainability (unified)
- `explain.py` produces `Explanation` from: SHAP (existing, tree/kernel), LIME (optional lib; fallback = local feature perturbation), and rule reason codes. Feeds the Phase 7 explainability panel + Phase 8 evidence ("ML Explanation").

## 10. Drift & retraining
- `drift.py`: **PSI** + **KS** per feature vs the offline baseline; performance drift via rolling precision on confirmed cases. Threshold breach → emits a `retrain` signal (logged + optional Celery enqueue).
- `training.py`: deterministic synthetic + (when available) confirmed-case labels → trains each estimator → registers a new shadow version → drift/shadow eval → optional promotion. Runnable as CLI now, Celery task in Phase 9.

## 11. Build order (waves)
- **Wave A (now, verifiable — sklearn/xgboost/shap present):** interfaces, registry, feature_store (in-proc + Redis-optional), features.py, RandomForest + IsolationForest + XGBoost wrappers, ensemble, drift (PSI/KS), unified explain (SHAP + perturbation-LIME fallback), training CLI. Verified on synthetic data with a metrics gate (e.g. ROC-AUC ≥ 0.85 on the synthetic split).
- **Wave B (graceful interfaces):** LightGBM, Autoencoder, Node2Vec (numpy fallback), community/link-prediction (nx), wire `structural_ml` detectors. Verified via fallback paths.
- **Wave C (heavy, optional libs):** real GraphSAGE/GCN/GAT/Temporal-GNN when torch_geometric is installed; promote `gnn_model.py`.

## 12. Risks & mitigations
| Risk | Mitigation |
|---|---|
| Optional libs absent (torch/lightgbm/lime) | every model `available()`-gated; ensemble averages only available models; fallbacks defined |
| ML overrides explainable rules | ML is a capped factor in risk_engine; never opens a case alone |
| Train/serve skew | single `features.py` spec for both; offline store mirrors online |
| Synthetic-only labels overfit | drift monitor + shadow eval + isotonic calibration; real labels from confirmed cases feed retraining |
| Per-boot cost | registry persists artifacts; load active version at startup |

## 13. Testing strategy (gate to Phase 6)
- Estimator contract test: each wrapper implements `Model`, `predict_proba` in [0,1], `available()` honest, never raises.
- **Metrics gate**: ensemble ROC-AUC ≥ target on the synthetic holdout; calibration error bounded.
- Fallback test: with optional libs "absent" (monkeypatched), platform still scores via fallbacks.
- Drift test: injected distribution shift trips PSI threshold.
- Registry round-trip: train → save → load → identical predictions.
- Explanation test: `explain()` returns reason codes summing ≈ score; SHAP path covered.
- No-regression: existing IF/XGB/SHAP outputs unchanged.

## 14. Expected output
- `ml/platform/`, `ml/models/`, `ml/graph/` with interfaces, registry, feature store, ensemble, drift, unified explain, training CLI.
- Existing models registered + persisted (no per-boot rebuild).
- ML risk wired as a capped factor into `risk_engine` (off by default until tuned).
- `structural_ml` Wave 3 detectors functional via nx fallbacks.

## 15. Open questions for sign-off
1. ML score as a **capped additional factor** into the risk engine (never overrides rules). **Recommended: yes**, weight 0 by default until tuned.
2. **Wave A first** (registry + tabular ensemble + drift + explain, all verifiable on synthetic data now) before graph/heavy models. **Recommended: yes.**
3. Artifact storage: **local `models/` dir now**, object store (S3/BELS-anchored) later. **Recommended: local now.**
