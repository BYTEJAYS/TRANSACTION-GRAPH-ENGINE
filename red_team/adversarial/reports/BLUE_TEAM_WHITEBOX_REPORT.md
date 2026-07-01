# Blue Team — White-Box Analysis & Vulnerability Report

**Target:** TGiE (Temporal Graph Intelligence Engine) fraud-detection stack
**Classification:** White-box (full source, weights-as-code, thresholds, training data)
**Purpose:** Establish a precise, code-grounded model of the defender before any
Red Team component is written. Every gate, weight, and threshold cited below is
quoted from the live source, not inferred.
**Status:** Step 1 of the adversarial program — *analysis only, no attack code yet.*

---

## 0. Executive summary

TGiE ships **two independent Blue Team generations** behind a single router:

| | V1 (`backend/blue_team`, `ml/`, `anomaly_detection/`, `fraud_classifier.py`) | V2 (`backend/blue_team_v2/`) |
|---|---|---|
| Paradigm | Learned + statistical + streaming | Deterministic graph heuristics |
| Core | IsolationForest, XGBoost, GraphSAGE, GAE autoencoder, rule classifier | 18-factor node metrics → 11 detectors → evidence → scoring |
| Learned params | XGBoost (synthetic data); IF (online); **GNN never trained** | none — all constants hand-tuned |
| State | IF rolling buffer (poisonable) | stateless per call |
| Production default | **`ACTIVE_BLUE_TEAM` unset → V1** (`router.py:27`) | opt-in (`=v2`) |

**The single most important structural fact:** V2 analyses **each connected
component in complete isolation** (`core/graph_engine/builder.py` docstring;
`fraud_distances`, `centralities` are component-local). There is **no
cross-component, cross-session, or temporal-cross-analysis correlation**. An
operation split across disconnected components is, by construction, invisible.

**The second most important fact:** V2's risk is **bimodal**. A node cannot
cross the REVIEW band (0.62) on raw topology alone — the role base risk caps at
0.34 (`roles.py:ROLE_BASE_RISK`) and structural factors are deliberately
demoted to tie-breakers (`scorer.py` weighting comment). Real risk is *earned*
almost entirely from **detector participation** (weight 0.22) + **fraud
proximity** (0.15). Therefore: **evade the 11 detectors and you evade the entire
V2 verdict.** The whole defender reduces to 11 hand-coded gates, each with an
exact, quoted numeric threshold.

**Third:** every detector gate is an *absolute* constant (₹25k hop, ₹50k mule,
₹50k structuring band, ₹200k velocity, 4-hop chain, 4-degree fan, 6-hour
dormancy, 600-second burst window). None are adaptive, percentile-relative, or
learned. This makes the evasion margin *computable in closed form* — the
defining property a white-box Red Team exploits.

---

## 1. System overview

### 1.1 Request path

```
TGIE API (api/routes.py)
   └─ blue_team_v2.router.route_all_components(components)
        ├─ ACTIVE_BLUE_TEAM=v1 (DEFAULT) ─► blue_team.adapter ─► ML/stat stack
        └─ ACTIVE_BLUE_TEAM=v2            ─► blue_team_v2.adapter ─► graph engine
```

Verdict schema is identical across engines (`Verdict ∈ {CLEAN, LOGGED,
SUSPICIOUS, FRAUD}`); V2 adds an additive `v2` intelligence block the UI
consumes. Components are pre-split into connected components upstream and handed
in one at a time.

### 1.2 V2 pipeline (the richer, graph-native target)

```
component dict (nodes[], edges[])
  → TransactionGraph        build directed multigraph, aggregate (src,tgt) edges,
                            keep summed amount + count + sorted timestamps + rails
  → RiskEngine.compute()    18-factor NodeMetrics per node + ClusterIntelligence
        ├─ ClusterEngine    origin discovery, role assignment (13 roles), base risk
        ├─ AnomalyEngine    velocity / burstiness (Fano) / dormancy per node
        └─ inheritance       diffuse risk 3 hops from origins/high-prior, decay 0.55
  → PatternEngine.run()     11 detectors → Evidence[]; writes pattern_participation
        └─ hybrid meta       fires if ≥3 distinct pattern families co-occur
  → ScoringEngine.score_all()  per-node score = role_base + (1-base)·min(1, earned·1.6)
  → engine aggregate        cluster_risk = max(evidence_severity_blend,
                                              0.6·p90(node_risk) + 0.4·p75(node_risk))
  → score_to_action → action_to_verdict   (thresholds 0.38 / 0.62 / 0.83)
  → classify + explain      primary/secondary label + per-node "why" + narrative
```

### 1.3 V1 stack (the learned/statistical target)

- **FeatureExtractor** (`anomaly_detection/isolation_forest_detector.py`): the
  canonical **12-dimensional** per-transaction vector, reused by both IF and
  XGBoost — `[normalized_amount, amount_z_score, amount_rail_ratio, velocity,
  fan_out, payment_rail, hour_of_day, is_night, is_weekend, is_round_amount,
  near_threshold, account_age_proxy]`. Velocity = txns in last 60 s; fan-out =
  cumulative unique recipients; z-score vs a 200-deep rolling per-account
  history.
- **IsolationForest**: bootstrapped on 500 standard-normal samples (20 ×10 as
  seed anomalies), `contamination=0.1`, `max_samples=256`; retrains on a rolling
  1000-vector buffer (min 50). Online and **stateful**.
- **XGBoost** (`ml/xgboost_classifier.py`): 200 trees, depth 4, trained at
  startup on a **synthetic** labelled set drawn from hand-specified
  gamma/normal distributions with 7 % label-noise. Reports a synthetic-holdout
  AUC.
- **GraphSAGE + GAE** (`ml/gnn_model.py`): 12-feature node classifier (4 risk
  classes) + reconstruction-error autoencoder.
- **ManualFraudClassifier** (`fraud_classifier.py`): 4 rules — chain depth > 3,
  amount repeated ≥ 3×, cycle present, fan-out ≥ 4.
- **Streaming**: Kafka producer/consumer + Flink processor (`streaming/`).

---

## 2. Detection logic — the exact decision surface

### 2.1 Thresholds (`types.py`)

```
LOG = 0.38   REVIEW = 0.62   HIGH_RISK = 0.83
score < 0.38 → PASS/CLEAN      ≥0.38 → LOG/LOGGED
              ≥0.62 → REVIEW/SUSPICIOUS    ≥0.83 → HIGH_RISK/FRAUD
```

### 2.2 Per-node scoring (`scorer.py`)

`score = base + (1 - base)·min(1, earned·1.6)`, where `earned = Σ wᵢ·sigᵢ`.
Factor weights (sum ≈ 1.0):

| factor | weight | signal source |
|---|---|---|
| pattern_participation | **0.22** | # distinct detectors touching the node |
| fraud_proximity | **0.15** | `exp(-hops_to_origin / 2)`; 0 if no origin |
| velocity_anomaly | 0.12 | value/min, log-compressed |
| risk_inheritance | 0.08 | diffused from origin (0 if no origin) |
| burst_activity | 0.07 | Fano burstiness |
| volume | 0.06 | log-sat of in+out |
| pass_through | 0.05 | relay balance |
| dormancy_reactivation | 0.05 | 6 h+ gap then activity |
| layering / historical | 0.04 each | chain depth / prior risk |
| bridge / circular | 0.03 each | articulation / cycle flag |
| fan_out / fan_in | 0.025 each | degree saturation |
| betweenness / frequency | 0.02 each | centrality / count |

**Closed-form evasion margin:** a `NORMAL`-role node (base 0.03) needs
`earned ≥ (0.62-0.03)/((1-0.03)·1.6) ≈ 0.38` to reach REVIEW. With **no detector
firing and no origin in the component**, the maximum reachable `earned` from
pure topology + behaviour is dominated by velocity (0.12) + burst (0.07) +
volume (0.06) ≈ 0.25 fully saturated → `score ≈ 0.03 + 0.97·min(1,0.4) ≈ 0.42`
(LOG at most, never SUSPICIOUS). **Conclusion: no detector → at most LOGGED, and
in practice CLEAN.** The detectors are the only path to a fraud verdict.

### 2.3 The 11 detector gates (the real attack surface)

| detector | fires when (all conditions) | quoted constants |
|---|---|---|
| **circular_flow** | a cycle len ≥ 2 carries ≥ ₹50,000 | `MIN_LOOP_VALUE=50_000` |
| **layering** | longest chain ≥ 4 hops, **mean hop ≥ ₹25,000**, ≥1 pass-through relay | `MIN_DEPTH=4`, `MIN_HOP_AMOUNT=25_000` |
| **smurfing** | ≥3 identical amounts > ₹1,000, **or** ≥3 transfers in [₹46,000, ₹50,000) | `STRUCTURING_THRESHOLD=50_000`, `NEAR=0.92` |
| **fan_out** | ≥4 successors, out-vol ≥ ₹150,000, avg ≥ ₹25,000 | `THRESHOLD=4`, `MIN_OUT_VOLUME=150_000`, `MIN_AVG_AMOUNT=25_000` |
| **fan_in** | symmetric to fan_out (collection hub) | `THRESHOLD=4` |
| **mule_accounts** | in-vol ≥ ₹50,000, out ≥ 0.6·in, pass-through ≥ 0.6 | `MIN_MULE_VOLUME=50_000` |
| **bridge_accounts** | articulation point with in≥1 & out≥1 | — |
| **velocity** | velocity ≥0.5 & vol ≥ ₹200k; **or** burst ≥0.7 & freq ≥4; **or** cluster ₹500k in ≤600 s | `200_000 / 0.7 / 600 s / 500_000` |
| **cashout** | sink/cash-type, fan_in ≥2, in-vol ≥ ₹100,000 | `100_000`, `CASH_TYPES` |
| **dormant_accounts** | reactivation ≥0.45 (gap ≥6 h) & vol ≥ ₹50,000 | `_MIN_DORMANCY_SECONDS=6h`, `50_000` |
| **synthetic_networks** | score ≥0.45 from: density ≥0.25, degree-uniformity ≥0.7 (n≥6), fresh-ratio ≥0.6 | `0.25 / 0.7 / 0.6` |
| **hybrid_network** (meta) | ≥3 distinct families co-occur | `len(families) ≥ 3` |

---

## 3. Strengths (what it handles well)

1. **In-distribution typologies.** Cycles, fan-in/out hubs, multi-hop layering,
   structuring near ₹50k, mule chains, burst dispersal, dormant reactivation,
   synthetic rings — each has a dedicated, well-reasoned detector with a
   monetary significance gate that suppresses benign look-alikes (multi-payee
   bill paying, lunch-settling loops). Recall on the in-house simulator's
   patterns is high *by design*.
2. **Low false-positive posture on benign structure.** The role-base ceiling
   (≤0.34) and the "topology demoted to tie-breaker" weighting keep structurally
   busy but legitimate clusters (merchants, payroll fan-out) CLEAN. This is a
   genuine, deliberate engineering achievement of V2 over V1.
3. **Faithful explainability** (see §9) — every score decomposes into
   normalized contribution shares; the cluster narrative is evidence-grounded.
4. **Corroboration bonus.** `pattern_participation` rewards nodes appearing in
   multiple independent detectors, and the hybrid meta-detector escalates
   multi-technique clusters — professional operations that light up many gates
   are scored *more* harshly, not averaged down.
5. **Graceful degradation & robustness to crashes.** Missing libs (torch,
   xgboost, libomp) fall back instead of failing; a detector exception is
   swallowed so it cannot take down the pipeline (`pattern_engine` try/except).
6. **Scalability guards.** Cycle length-bounding, betweenness sampling,
   closeness skipping, and source-sampled longest-path keep it within the
   100k-node target. (Each guard is also an attack surface — see §5.)

---

## 4. Weaknesses & blind spots

### 4.1 Architectural blind spots (highest severity)

- **B1 — Cross-component blindness.** No correlation across connected
  components. *Any* operation whose sub-rings share no edge is analysed as N
  independent benign graphs. This defeats every detector simultaneously and
  requires no per-detector evasion. **This is the dominant blind spot.**
- **B2 — Stateless V2 / no temporal memory across analyses.** Each call sees
  only the current snapshot. Fraud spread across *time* (re-analysed snapshots)
  never accumulates. Slow-drip infiltration over many windows is invisible to
  V2 entirely; the only temporal signals (velocity/burst/dormancy) are *intra*
  window and absolute-gated.
- **B3 — Bimodal verdict.** Because risk is detector-gated, the system has
  effectively two states. Adversarial graphs tuned just under every gate sit
  permanently in CLEAN with large margin; there is no smooth risk ramp to catch
  near-misses.

### 4.2 Learned-model weaknesses (V1)

- **B4 — Untrained GNN.** `GNNManager` instantiates GraphSAGE and the GAE with
  random weights and **never calls a training loop** (`_is_trained` is set only
  in `_bootstrap`/IF, never for the GNN). `infer_risk` runs random-weight
  inference; reconstruction error is normalized noise. Any decision weight given
  to GNN risk classes/embeddings is effectively random. *Embedding-space attacks
  against this GNN are meaningless because the embedding itself is meaningless* —
  but so is any defensive value it claims.
- **B5 — Label leakage in IsolationForest.** `score()` does
  `if txn.fraud_pattern != NORMAL: anomaly_score = max(anomaly_score,
  txn.risk_score)`. The detector reads the ground-truth label off the
  transaction. Apparent IF performance is inflated; a transaction submitted with
  `fraud_pattern=NORMAL` / `risk_score=0` removes this floor and is scored on
  raw IF only.
- **B6 — XGBoost overfit to a synthetic generator.** Trained solely on
  hand-specified gamma/normal distributions. Inputs outside those distributions
  (i.e. real or adversarial) get arbitrary, uncalibrated probabilities. The
  reported AUC measures fit to the generator, not fraud.
- **B7 — IF cold-start & buffer drift.** Boundary and scaler are defined by
  whatever traffic flows first; early volume dominates the contamination
  estimate.

### 4.3 Feature-level weaknesses

- **B8 — Attacker-controlled node attributes.** V2 reads `account_type`,
  `risk_score` (→ `prior_risk`/`historical_behavior`), `detected_patterns`,
  `transaction_count` straight from the input node dict. In any node-injection
  setting these are attacker-set: declaring `account_type="normal"`,
  `risk_score=0`, `detected_patterns=[]`, `transaction_count` high directly
  zeros the `historical_behavior` factor, defeats the synthetic-ring fresh-ratio
  test, and prevents `cashout` cash-type classification.
- **B9 — Round-number / threshold features are trivially mimicable.**
  `is_round_amount`, `near_threshold` are deterministic functions of the amount;
  an attacker simply avoids those amounts.

---

## 5. Failure modes

1. **F1 — Scale-induced detector decay.** On graphs > 4,000 edges, cycle search
   is length-bounded to 8 → loops longer than 8 hops are missed (circular_flow
   silently blind). On > 400 nodes, longest-chain only samples the 400 highest
   out-degree sources → a layering chain seeded from a low-degree node is missed.
   On > 1,500 nodes betweenness is k-sampled; on > 3,000 closeness is set to 0 →
   bridge/centrality signals vanish. **Operating at scale is itself an evasion.**
2. **F2 — Silent detector disablement.** `pattern_engine` swallows any detector
   exception. A crafted component that triggers an unhandled path in one detector
   (e.g. degenerate timestamps, NaN amounts pre-sanitization) disables *that*
   detector with no log at INFO and no verdict impact recorded.
3. **F3 — Origin-discovery collapse.** `discover_origins` only labels emitters
   with `in_deg==0` or (`out/in > 3` and `in_deg ≤ 1`), capped to the top-5 by
   volume×reach. Inject funds through a node with `in_deg ≥ 2` or `out/in ≤ 3`
   and **no origin is found** → `fraud_distance = 999` for everyone →
   `fraud_proximity` (0.15) **and** `risk_inheritance` (0.08) both collapse to 0.
   0.23 of total scoring weight removed by one structural choice.
4. **F4 — Empty-edge / tiny-component PASS.** `num_edges()==0` returns CLEAN
   immediately; most detectors early-return below 3 edges / 5 nodes. Operations
   decomposed into ≤2-edge fragments are individually un-analysable.

---

## 6. Assumptions the model makes about graph behaviour

| # | Assumption | Where encoded | Falsified by |
|---|---|---|---|
| A1 | Fraud is structurally distinctive (cycles, fans, chains) | all detectors | structure-free relay through degree-≤3 nodes |
| A2 | Fraud crosses absolute monetary gates (₹25k/50k/100k/150k/200k) | every detector's amount gate | sub-gate "dust" laundering |
| A3 | Fraud is fast / bursty / threshold-hugging | velocity, smurfing, dormancy | slow, randomized-amount, off-threshold flow |
| A4 | A laundering operation is one connected component | graph builder isolation | partitioned operations (B1) |
| A5 | Ring accounts are fresh / low-history | synthetic_networks fresh-ratio | aged or warmed-up mule accounts |
| A6 | Input node attributes are honest | risk/role/type ingestion | feature mimicry (B8) |
| A7 | Reporting threshold = ₹50,000; 4 named rails with fixed typicals | smurfing / FeatureExtractor | amounts chosen off the modelled threshold |
| A8 | The current snapshot contains the whole behaviour | stateless V2 | time-distributed attacks (B2) |

---

## 7. Overfitting risks

- **O1 — Detector/simulator co-design.** The 11 detectors and the in-house
  `simulation/generators.py` / `simulator/transaction_generator.py` model the
  *same* typologies. High measured recall is partly tautological: the defender
  is evaluated on the exact patterns it was written to catch. Out-of-typology
  fraud has unknown (likely poor) recall.
- **O2 — XGBoost ↔ its synthetic generator** (B6): a textbook closed-world
  overfit; the model has never seen a distribution it didn't generate.
- **O3 — Constant overfitting.** The absolute gates (₹25k, 0.6 pass-through,
  4-degree, 6 h, 600 s) are tuned to the simulator's parameter ranges. They are
  brittle to any operation that simply lives in the gaps between them.
- **O4 — Label leakage (B5)** inflates V1 evaluation specifically and will mask
  regressions in self-play unless removed from the eval harness.

---

## 8. White-box vulnerability taxonomy (for Red Team targeting)

### 8.1 Structural
- Degree assumption: stay ≤3 unique counterparties everywhere → no fan/role.
- Community assumption: keep density <0.25 and degree CV >0.3 → synthetic-ring
  miss; embed malicious nodes among high-history benign nodes (B8) → fresh-ratio
  miss.
- Articulation assumption: avoid being the sole cut-vertex (add a parallel
  benign path) → no bridge role.
- **Component assumption (primary): partition the operation (B1).**

### 8.2 Temporal
- Velocity gate is absolute (≥0.5 index, ≥₹200k, or ≤600 s/₹500k). Spread the
  same value over a wider window → index < 0.5, window > 600 s.
- Burstiness is Fano-style on inter-arrival gaps; near-periodic spacing →
  burst < 0.7.
- Dormancy needs a ≥6 h gap. Keep max inter-arrival gap < 6 h → reactivation 0.
- **Slow poisoning (B2): distribute across re-analysed snapshots → no
  accumulation.**

### 8.3 Feature
- Mimicry: set injected-node attributes to benign (B8).
- Amount masking: avoid round numbers and the [₹46k, ₹50k) band; randomize
  amounts so no value repeats ≥3× → smurfing fully evaded.
- Distribution shift (V1): operate outside the XGBoost synthetic support → B6.

### 8.4 Embedding / latent
- V2 has no learned embedding; its "latent space" is the 18 hand-engineered
  factors + role base. The exploitable directions are explicit:
  **drive `pattern_participation`, `fraud_proximity`, `risk_inheritance`,
  `velocity` jointly to 0** and the score cannot exceed ~0.42 (LOG).
- V1's GNN embedding is untrained (B4) → no meaningful latent direction exists
  to attack; gradient attacks on it are noise.

### 8.5 Threshold / confidence
- Verdict is a pure step function of `cluster_risk` against fixed cuts. Craft
  `cluster_risk` to land in [0, 0.38) for guaranteed CLEAN with margin, or probe
  the 0.62 boundary to study detector sensitivity. Because thresholds are
  static, boundary-hugging never triggers adaptation.

### 8.6 Memory poisoning
- V2: not applicable (stateless).
- V1 IsolationForest: **poisonable.** Feed many adversarial-but-benign-looking
  vectors into the rolling 1000-buffer to shift the scaler/contamination
  boundary so subsequent real anomalies score lower. This is the one genuine
  long-term-memory attack surface in the stack.

---

## 9. Explainability — which features dominate

- **V2** (faithful, by construction): scores decompose into contribution shares
  ≥2 % (`scorer.py`). Across the weighting, predictions are dominated by, in
  order: **pattern_participation (0.22) → fraud_proximity (0.15) → velocity
  (0.12) → risk_inheritance (0.08)**. In practice a FRAUD verdict is driven by
  *detector hits + proximity to a discovered origin*. Remove those two and the
  explanation engine has nothing material to attribute.
- **V1**: XGBoost `feature_importances_` (gain) + a SHAP explainer module
  (`anomaly_detection/shap_explainer.py`). Dominant features are whichever have
  the widest legit/fraud gap in the synthetic generator — structurally
  `amount_z_score`, `velocity`, `fan_out`, `near_threshold`. These are exactly
  the features an attacker can flatten (B9).

---

## 10. Attack-surface scorecard (where Red Team pressure pays off)

| Surface | Severity | Effort | Defeats |
|---|---|---|---|
| Cross-component partitioning (B1) | ★★★★★ | low | entire V2 verdict |
| Sub-gate "dust" amounts (A2) | ★★★★★ | low | every monetary-gated detector |
| Origin-discovery collapse (F3) | ★★★★☆ | low | 0.23 of scoring weight |
| Feature mimicry on injected nodes (B8) | ★★★★☆ | low | synthetic ring, cashout, history |
| Slow/temporal distribution (B2,8.2) | ★★★★☆ | medium | all temporal detectors |
| Randomized off-threshold amounts (8.3) | ★★★★☆ | low | smurfing |
| Scale-induced decay (F1) | ★★★☆☆ | medium | cycle/chain/centrality |
| IF buffer poisoning (8.6) | ★★★☆☆ | medium | V1 long-term sensitivity |
| GNN/embedding attacks (B4) | ★☆☆☆☆ | n/a | nothing — model is untrained |

---

## 11. Implications for the Red Team design (no code yet)

1. **Primary objective function.** Maximize Attack Success Rate (verdict ≤ LOG
   on a truly fraudulent graph) subject to minimal graph distortion. The
   white-box gates make distortion *measurable*: distance to each gate is a
   differentiable-enough surrogate for a stealth loss.
2. **Two distinct targets.** V2 (deterministic, gate-based) calls for a
   constraint-satisfaction / evolutionary / RL search over the gate margins. V1
   (learned) calls for distribution-shift + IF-buffer-poisoning + (pointless)
   GNN attacks — useful mainly to *prove* B4/B5/B6 empirically.
3. **The cross-component attack must be first-class**, because it dominates
   everything; the Red Team's graph generator should be able to emit partitioned
   operations and the evaluation harness must score the *whole* operation, not
   per-component, to even detect that the attack succeeded.
4. **Fix the eval harness before self-play.** Remove the IF label leak (B5) from
   any measurement path, and add an out-of-typology holdout, or robustness gains
   will be illusory.

---

## 12. Two decisions required before writing Red Team code

These genuinely change the architecture and are the user's to make:

- **D1 — Isolation contract.** The existing `red_team/` package enforces a hard
  import-time isolation contract (`red_team.core.safety.assert_isolation()` — no
  imports from blue_team, no feedback loop, no adversarial self-learning). The
  requested self-play system *requires* coupling Red↔Blue. Recommended:
  **leave the legacy `red_team/` untouched and build the coupled adversarial
  ecosystem under the new top-level `adversarial/`** (this report already lives
  there), so nothing violates the existing safety assertion. Alternative: retire
  the isolation contract and build inside `red_team/`.
- **D2 — Which Blue Team is the canonical target?** Recommended: **target V2 as
  the primary defender** (it is the real graph-native detector and the future
  default) while keeping V1 as a secondary target used specifically to
  demonstrate B4/B5/B6. Self-play retraining is only meaningful for components
  that *can* learn — i.e. it will harden V2's thresholds/weights and V1's
  XGBoost/IF, not the untrained GNN (which should either be trained or removed
  first).

---

*Prepared as Step 1 of the TGiE adversarial program. No Red Team attack code has
been written. Proceed to Red Team architecture only after D1/D2 are settled.*
