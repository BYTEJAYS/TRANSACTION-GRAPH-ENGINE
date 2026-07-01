# Blue Team Audit

> Scope: the three Blue Team implementations in the TGIE ecosystem —
> **V1** (`backend/blue_team`, ML/statistical, production default),
> **V2** (`backend/blue_team_v2`, deterministic graph engine), and
> **BLING** (`blue_team/bling`, the Union Bank :8001 forensic service).
> Findings are grounded in the white-box analysis in
> `red_team/adversarial/reports/BLUE_TEAM_WHITEBOX_REPORT.md` and the adversarial engagement (§16–§22).

---

## 1. Architecture Review

### V1 — ML / Statistical (production default)
- IsolationForest (anomaly) + XGBoost (classifier) + GraphSAGE/GAE (embeddings) + rule classifier.
- Streaming-oriented (Kafka/Flink in the heavy build; disabled in deploy).
- Emits the canonical verdict schema: `graph_id/status/verdict/risk_score/flagged/flagged_nodes/suspicious_reason/nodes/mode`.

### V2 — Deterministic Graph Engine
- Pipeline: **18-factor `NodeMetrics` → 11 detectors → evidence → per-node scoring → cluster verdict.**
- Thresholds (`types.py`): `LOG 0.38 / REVIEW 0.62 / HIGH_RISK 0.83`.
- 11 detectors: `layering, smurfing, mule_accounts, fan_in, fan_out, velocity, cashout, circular_flow, bridge_accounts, dormant_accounts, synthetic_networks`.
- Drop-in via `blue_team_v2.adapter.analyze_all_components()`; engine selected by `ACTIVE_BLUE_TEAM` env (shadow mode runs both).

### BLING — Union Bank Forensic Service (:8001)
- FastAPI + SQLAlchemy/Postgres + **Neo4j** graph store + Redis/Celery workers.
- Modules: `api, core, detection, evidence (forensic PDF), graph, integrations, models`.
- ML bridges: IsolationForest training, BAF/Kaggle augmentation, `deepesh_bridge`.

---

## 2. Detection Logic

| Layer | Mechanism | Strength |
|---|---|---|
| Per-node scoring (V2) | role base risk (cap 0.34) + evidence-weighted factors | Fixes V1's "identical risk across cluster" bug |
| Top scoring weights (V2) | pattern_participation 0.22, fraud_proximity 0.15, velocity 0.12, **volume only 0.06** | Volume under-weighted — exploited later |
| Detector gates | absolute ₹ constants (₹25k hop, ₹46–50k mule/structuring band, ₹150k/200k fan/velocity, 4-hop chain, 4-degree fan, 6h dormancy, 600s burst) | Deterministic & explainable — but evasion margins computable in closed form |
| Verdict | detector-gated & bimodal: no detector firing + no origin maxes ≈0.42 (LOG) | Evading the 11 detectors ≈ evading all of V2 |

---

## 3. Weaknesses

- **B1 (dominant): component isolation.** V2 analyses each connected component in isolation — no cross-component / cross-session / temporal correlation. *Partitioned operations are invisible.* This is the single highest-value architectural gap; the entire adversarial engagement converges on it.
- **B2: statelessness.** V2 is stateless per call → slow, time-distributed attacks unseen.
- **B3: closed-form evadability.** Every detector gate is an absolute constant → an attacker can compute exact evasion margins.
- **B4: untrained GNN.** GraphSAGE/GAE ships with **random weights** (`_is_trained` never set) → embeddings/risk classes are noise. Embedding attacks pointless; signal is dead weight.
- **B5: label leakage (V1).** `IsolationForest.score` reads ground-truth `txn.fraud_pattern` → inflates V1 metrics. Must be stripped from any honest eval harness.
- **B6: overfit XGBoost (V1).** Tuned to its own synthetic generator.
- **B8: attacker-controlled attributes.** V2 trusts attacker-set node attrs (`account_type`, `risk_score`, `detected_patterns`).
- **High benign FP on realistic traffic.** Native V2 FP on a *realistic* benign corpus = **56.7%** (payroll 100%, corporate 85%, household 45%) vs 11.7% on simple corpus. V2 flags legit structured/high-value activity as fraud. **This is the most important Blue Team finding** — fraud and legitimate high-value/structured activity are not separable by V2's 16 factors alone.

---

## 4. Blind Spots

| ID | Blind spot | Closed by |
|---|---|---|
| B1 | cross-component coordination (mule mesh) | `coordination` signal (operation-level) — adversarial §19 |
| B2 | temporal / slow distribution | `relationship-maturity` (temporal depth) — §21 |
| identity | fresh mules vs verified customers | `provenance` (KYC) — §14 |
| behaviour | seized verified account used as conduit | `behavioural` baseline — §17 |
| counterparty | novel counterparties between strangers | `relationship` circles — §20 |

**Engagement synthesis:** every effective defence injects **context** that V2's isolated snapshot lacks. The root cause is not just B1 — it is that V2 scores a **context-free snapshot**. The highest-value Blue investment is **memory/context**, not more structural detectors. With 6 composed signals the capstone (`final_stack.py`) drives a full adversary to **0.00 ASR @ 0% FP** on construction-honest corpora.

---

## 5. Scalability

- V2 scales to ~100k nodes in ~22s: closeness skipped >3k nodes, bridge detector pre-filters cut-points, cycles length-bounded (≤8), `longest_chain` samples 400 sources.
- **Decay risk:** these same optimisations *weaken detection at scale* (cycle bound misses long rings >4000 edges; chain sampling misses sources >400 nodes; betweenness/closeness sampled or zeroed).
- BLING adds Postgres+Neo4j+Celery → horizontally scalable but heavier ops surface.

---

## 6. Security Risks

- Static `BLUE_TEAM_API_KEY` (`tgie-secret-2025`) in env docs — rotate, move to secret manager.
- B8 attribute trust = an API caller can self-declare low risk.
- BLING DB defaults (`bling_user/trust`) must never reach a public surface.
- Detector exceptions are swallowed → silent detection gaps.

---

## 7. Performance Bottlenecks

- V2 betweenness/closeness centrality dominate cost on dense graphs (mitigated by sampling, at accuracy cost).
- V1 IsolationForest tuned down for Railway free tier (`n_jobs=1`, `n_estimators=100`) — latency vs accuracy tradeoff.
- BLING Neo4j round-trips per component; Celery queue depth is the throughput ceiling.

---

## 8. Subsystem Scorecard

Scores are 0–10 (higher = healthier), reflecting current code state.

| Subsystem | Score | Rationale |
|---|---:|---|
| V2 per-node scoring | 8 | Real per-node differentiation; explainable; well-weighted except volume. |
| V2 detector suite | 7 | 11 solid detectors; let down by closed-form-constant evadability. |
| V2 verdict aggregation | 6 | Bimodal & detector-gated; conservative but brittle to partitioning. |
| Cross-component correlation | 2 | Absent natively (B1); only via adversarial `coordination` add-on. |
| Temporal / stateful detection | 2 | Stateless (B2). |
| GNN embeddings | 1 | Untrained, random weights (B4) — effectively dead. |
| V1 ML pipeline | 4 | Works but label leakage (B5) + overfit (B6) inflate metrics. |
| Benign false-positive rate | 2 | 56.7% FP on realistic legit traffic — not deployable as-is. |
| Context/provenance signals | 7 | Strong *prototype* (adversarial integration); needs real KYC/history data. |
| BLING forensic/evidence | 7 | Mature service (Neo4j + PDF evidence), separate ops burden. |
| Scalability | 6 | 100k nodes/22s but detection decays at scale. |
| Explainability | 8 | Evidence-driven, deterministic, auditable. |
| **Overall Blue Team** | **5.5 / 10** | Excellent deterministic core undermined by context-blindness (B1/B2) and high benign FP; the hardened context-signal stack is the credible path to production. |

---

## 9. Recommendations (priority order)

1. **Close B1** — add operation-level cross-component/cross-session correlation (the proven highest-value fix).
2. **Fix benign FP** — wire the `provenance` (KYC) signal into the real engine; it drove FP 43.8%→0% in the prototype.
3. **Strip B5 label leak** from V1 and re-benchmark honestly.
4. **Remove or train the GNN** (B4) — stop emitting noise as a risk class.
5. **Stop trusting attacker attributes** (B8) — derive `risk_score`/`detected_patterns` server-side only.
6. **Promote V2 to default** once FP is controlled (faster + more accurate than V1 on benchmark: graph-F1 0.96 vs 0.76).
7. **Recalibrate every 0% FP claim on real data** — current honesty rests on construction-honest synthetic corpora.
