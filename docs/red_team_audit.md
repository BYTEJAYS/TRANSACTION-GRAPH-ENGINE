# Red Team Audit

> Scope: the three Red Team capabilities —
> **`red_team/adversarial`** (Red⇄Blue self-play research program, the primary system),
> **`red_team/engine`** (in-repo isolated red team with scenario datasets), and
> **`red_team/crucible`** (CRUCIBLE evolutionary fraud-genome engine, Union Bank).
> Grounded in `red_team/adversarial/reports/RED_TEAM_AUDIT.md` and the §16–§23 engagement log.

---

## 1. Attack Simulations

### Adversarial program (primary)
- **Agents (11):** `feature_mimicry` (B8), `amount_dither` (smurfing), `temporal_spread` (velocity/burst/dormancy), `relay_insertion` (degree-throttle tree), `decoy_edges`, `sink_funnel`, `cross_component_split` (B1 — appears in every winning family), `volume_dilution`, `profile_mimicry`, `account_takeover`, `conduit_split` (mule mesh).
- **Search engines:** warm-started GA (`evolutionary_engine`), **MAP-Elites** quality-diversity (`quality_diversity`), **PPO** RL agent (pure-NumPy actor-critic), **GraphGAN** surrogate (NumPy MLP distilled from V2).
- **Objective:** drive a laundering operation FRAUD→LOGGED while preserving sources→sinks value delivery; distortion + stealth tracked.

### CRUCIBLE (Union Bank)
- Continuous evolution of synthetic fraud "genomes"; nightly generates thousands of variants, keeps detection-evading ones, routes to **human reviewers** (`human_gate`), learns when a predicted pattern later appears in real fraud (`prophecy`, `learning`).
- Subsystems: `core, mutation, critics, learning, prophecy, human_gate, workers, db, api, sandbox`.

### In-repo engine
- Curated scenario datasets: `A01-multi-stage-laundering, A02-mule-network(-evo), A03-hybrid-operation, B01-single-suspicious-transfer, B02-account-takeover-burst` + analytics. Hard import-time isolation contract (`assert_isolation()`) forbids blue_team coupling.

---

## 2. Coverage Analysis

| Attack family | Realized | Result vs V2 |
|---|:--:|---|
| Layering / hop chains | ✅ | cheap evasion (distance ~0.15) |
| Smurfing / amount dither | ✅ | evades structuring band |
| Mule network | ✅ | gated by cashout/fan-in consolidation |
| Cross-component split | ✅ | **in every winning family** (B1) |
| Account takeover | ✅ | breaks provenance cheaply (ASR 0→1.0 with 24 seized accts) |
| Conduit-split mule mesh | ✅ | bypasses the entire per-component stack |
| Volume dilution / profile mimicry | ✅ | huge graphs → slow, needs surrogate world-model |
| Embedding attacks on GNN | ❌ | pointless (GNN untrained, B4) |
| V1 as target | ❌ | V2 is primary target; V1 secondary (open) |
| Black-box / transfer | ❌ | white-box only; transfer never measured |

---

## 3. Detection Evasion Analysis

- **Permissive ASR reproduces** ~0.56–0.67 by seed; **PPO** independently reaches the same band (0.00→0.56) by a different search — both lean on the **same B1 lever** (every win uses `cross_component_split`).
- **Strict (on-graph) ASR = 0.0** — *every* winning attack is partition-dependent. The headline 66.7% conflated a real B1 blind spot with a permissive objective granting free off-graph completion credit. Phase A now reports `attack_success_rate_strict` + `partition_dependent_evasions` separately. **This honesty correction is the audit's most important methodological finding.**
- Arms race terminates in **economics**: `relationship-maturity` forces the attacker to pre-move legit value ∝ laundering a year ahead (e.g. ₹7.8B to launder ₹607k) — self-defeating.

---

## 4. Training Effectiveness

- **GA:** warm-start seeding raised ASR 11%→67% (critical); deterministic per-genome (blake2b stable seed) → reproducible, fitness-cacheable.
- **MAP-Elites:** found **12 distinct evading families / 33 cells** vs scalar GA's 5 — kills mode collapse the audit flagged.
- **PPO:** learning curve train_asr .14→.85, entropy 3.32→1.78; reproducible across seeds; hits same ASR band as GA.
- **GraphGAN surrogate:** distillation fidelity MAE 0.033 / flag-acc 99.7%; static surrogate → **Goodhart** (true ASR 0 as policy exploits proxy gap); the re-distillation GAN loop closes it (on-policy agreement .56→.91).
- **Human-in-the-loop gate (frontend panel):** only human-approved, *Blue-missed* evasions feed Blue. Measured: training on garbage hurts (benign FP 15%, quality −0.04) vs clean-only (FP 5%, quality +0.06).

---

## 5. Missing Attack Patterns

- **Relationship-seasoning at scale** (deep, surgical) — armed but priced out by maturity; surgical (fewer pairs) variant unexplored.
- **Multi-factor simultaneous mimicry** — the open probe: dilute/mimic *all* discriminative factors at once while preserving objective.
- **Baseline-appropriate seizure** (corporate/SME conduits within profile) — residual that behavioural detection can't catch.
- **Black-box / query-limited attacks** and **transfer across detector configs** — never built.
- **V1 as a first-class target** — secondary, deferred.
- **Cashout-buster agent**, world-model-scaled QD (for the heavy graph-exploding agents).

---

## 6. Fundamentals Flagged (from RED_TEAM_AUDIT.md)

1. Self-play loop *was* open (ThresholdHardener proposal-only) → **closed in Phase B**; real co-evolution now runs (`arms_race.py`, `full_stack.py`).
2. Mode collapse (`cross_component_split` everywhere) → **addressed by MAP-Elites** novelty/QD (Phase C).
3. Overfitting is structural (hard-coded gate constants, fixed graphs, single seed) → multi-seed CI + held-out eval added; transfer still unmeasured.
4. Only wins remembered → genealogy is family-grouping not true lineage (`parent_ids` unpopulated) — open.

---

## 7. Subsystem Scorecard (0–10)

| Subsystem | Score | Rationale |
|---|---:|---|
| Attack agent library | 8 | 11 well-motivated agents, each mapped to a Blue finding. |
| GA / evolutionary engine | 8 | Reproducible, warm-started, cached; proven. |
| MAP-Elites quality-diversity | 8 | Real diversity, kills mode collapse. |
| PPO RL agent | 6 | Works in pure NumPy, reproducible; permissive objective only. |
| GraphGAN surrogate | 6 | High-fidelity distillation; Goodhart unless GAN loop runs. |
| Self-play loop closure | 7 | Genuinely closed Red⇄Blue; settles at honest equilibria. |
| Objective validity / honesty | 9 | Strict-vs-permissive separation is exemplary discipline. |
| Coverage breadth | 6 | Strong on graph-structural; missing black-box/transfer/V1. |
| Genealogy / lineage tracking | 3 | `parent_ids` unpopulated; family-grouping only. |
| CRUCIBLE human-gate + prophecy | 7 | Real closed loop with human review + real-fraud feedback. |
| Reproducibility | 8 | blake2b seeding, multi-trial CI. |
| **Overall Red Team** | **7.0 / 10** | A disciplined, honest white-box adversarial-science engine; primary gaps are black-box/transfer realism, V1 targeting, and true lineage. |

---

## 8. Improvement Recommendations (priority order)

1. **Measure transfer** — train on some graphs/seeds, evaluate on held-out typologies; report generalization, not in-distribution ASR.
2. **Build black-box / query-limited attacks** — the realistic threat model.
3. **Target V1** as a first-class objective (oracle is V2-only today).
4. **Populate true genealogy** (`parent_ids`) for lineage analysis and self-reflection on failures, not just wins.
5. **Multi-factor simultaneous mimicry agent** — the honest next adversary against the context-signal stack.
6. **Scale QD with the GraphGAN world-model** so volume_dilution/profile_mimicry don't time out.
7. **Recalibrate on real data** — every ASR figure rests on synthetic corpora; quote production numbers only after real account-history calibration.
