# TGIE Percentage & Score Integrity Audit

> Mandate: every percentage a Union Bank investigator sees must originate from a
> backend computation, be bounded 0–100%, be explainable by contributing factors,
> and degrade to **N/A** when it cannot be computed — never a fabricated number.
>
> Date: 2026-06-30. Authoritative tree: `~/Desktop/TGIE`.

---

## 1. The root-cause defect ("FRAUD 1000%")

**Where:** `backend/api/routes.py` (ingest → Blue-Team verdict broadcast).
**What:** `v["risk_score"] = a["score"]` put the Risk Engine's **0–100** integer onto
the websocket field `risk_score`. But the entire frontend treats `risk_score` as a
**0–1 fraction** and renders it as `risk_score * 100`. A component scoring 85 was
transmitted as `85` and displayed as `85 * 100 = 8500%` (rounded variants showed
"FRAUD 1000%"). The same 0–100 value was also `clamp01()`-ed in
`ai/graphClassifier.ts` (silently capping all risk at 100%) and compared against
`0.6` thresholds in `GraphScene` — so coloring was wrong too.

**Why it mattered:** it was not random and not a placeholder — it was a unit/scale
mismatch on a *real* score. But the displayed number was mathematically meaningless,
which is exactly the trust failure the mandate targets.

**Fix:** the wire contract is now explicit — `risk_score ∈ [0,1]` (fraction), sourced
from the Risk Engine as `round(a["score"]/100, 4)`. The canonical 0–100 integer and
full explainability ride alongside as dedicated fields (`risk_points`, `risk_level`,
`risk_confidence`, `risk_factors`, `risk_contributors`, `risk_explanation`). When the
engine cannot score a component, `risk_score = null` + `risk_available = false`, and
the UI renders **N/A**.

---

## 2. Inventory — every percentage, its source, and verdict

Legend: **REAL** = backend-computed & bounded · **CLIENT** = computed in React (real
math, but wrong tier per the mandate — Phase 2) · **FIXED** = was invalid, now correct.

### 2.1 Case / Cluster Risk %
| Display site | Source | Status |
|---|---|---|
| `LeftPanel` GraphRow, `RightPanel`, `BlueTeamPanel`, `EvidenceModal`, `NodeInspector` cluster card | `risk_engine.assess()` → wire `risk_score` (0–1) | **FIXED** — was `×100` on a 0–100 value (the 1000% bug). Now `riskPct()` / `riskValue()`. |
| `App.tsx` voice + HUD stats (`worstRisk`, narration) | same | **FIXED** — arithmetic via `riskValue()`; risk/confidence conflation removed. |
| Backend formula | `risk_engine/engine.py`: per-factor `intensity[0..1] × weight → points`, `score = clamp(Σ points, 0, 100)` across 11 factors (amount, velocity, layering, fan-out/in, circular, cash, rails, dormant, new-beneficiary, complexity). False-positive suppression can only pull the score **down**. | **REAL & explainable** (`factors[]`, `explanation`). |

### 2.2 Node Risk %
| Display site | Source | Status |
|---|---|---|
| `GraphScene` glow/size thresholds, `NodeInspector` directRisk, tooltips | `node.risk_score` ∈ [0,1] from Blue-Team V2 metrics; backend also exposes `v2.node_risk_scores` + `v2.node_intelligence` (per-node explanation, evidence) | **REAL** (0–1, consistent). Per-node propagation currently re-derived in `ai/riskPropagation.ts` (**CLIENT** — Phase 2). |
| Backend formula | `blue_team_v2/core/scoring_engine/scorer.py`: 18-factor node metrics → detector evidence → `risk_score` 0–1, `confidence` 0–1. | REAL & explainable. |

### 2.3 Confidence %
| Display site | Source | Status |
|---|---|---|
| `NodeInspector` "Risk confidence" | wire `risk_confidence` (0–100) via `pctValue()` | **FIXED/NEW** — now a **distinct** backend metric, not a copy of risk. |
| `App.tsx` two voice lines previously said *"confidence {risk_score}%"* | — | **FIXED** — relabeled to "risk"; the conflation (risk≡confidence) is removed. |
| `GraphIntelHUD`, `graphClassifier` pattern confidence | `ai/graphClassifier.ts` (0–1) | **CLIENT** — real deterministic math, Phase 2 to backend. |
| Backend formula | `risk_engine`: `confidence = clamp((40 + active_factors·11)·data_completeness + cycle_bonus, 5, 99)` — more corroborating signals + more data ⇒ higher confidence. | REAL & explainable. |

### 2.4 Recovery Probability %
| Display site | Source | Status |
|---|---|---|
| `recovery/redesign/sections.tsx` `{a.recovery_probability}%`, `FactorGrid`, `RecoveryFunnel` | backend `recovery/engine.py` | **REAL** — already backend, no `×100` (value is already 0–100). |
| Backend formula | `recovery/engine.py`: every factor through `_clamp(v, 0, 100)`; age half-life decay, depth penalty/hop, dispersion penalty/recipient, still-in-network fraction, freeze success. Funnel/`FactorGrid` percentages are proportions `v/max·100` (bounded by construction). | Bounded & explainable. |

### 2.5 Fraud rate / share / progress %
| Display site | Source | Status |
|---|---|---|
| `stats.fraudRate`, `MetricsPanel` flagged share, transaction progress bars, recovery funnel retained % | ratios of two backend counts (`flagged/active`, `step/total`, `v/max`) | **REAL** — bounded by construction (numerator ≤ denominator). Not risk scores. |

### 2.6 Pattern / Path / Community confidence
| Item | Source | Status |
|---|---|---|
| Pattern confidence, path risk, community risk | Backend `rule_engine.extract_motifs`, `blue_team_v2` detectors (`confidence` 0–1), community intelligence | **REAL** in backend (each detector emits bounded `confidence`/`severity`). Where surfaced via the V2 explainability block they are 0–1; the default app does not yet render dedicated pattern/path/community % panels (Phase 2 to wire them through `pctFraction()`). |

---

## 3. Known placeholders flagged (not yet fabricated in the live risk path)

These are **not** in the live graph/verdict risk path but are placeholder defaults
worth removing for full audit-cleanliness (Phase 2):

- `case_management/store.py:208` — linked-account `risk: 50` fallback when no record.
- `case_management/store.py:264` — manual case `risk = int(risk_score or 60)` default.

Per the mandate these should become **N/A**/omitted rather than a default number when
no computed value exists. They affect seeded case narratives, not the graph scores.

**No `Math.random` exists in any risk/confidence/recovery path** — the only
`Math.random` usages are login-screen particle visuals (`IntelligenceParticleEngine`),
which carry no investigative meaning.

---

## 4. The display contract (frontend)

`frontend/src/utils/percent.ts` is now the **single** percentage formatter:

- `pctFraction(v)` — backend 0–1 → `%`; **N/A** for null/NaN/out-of-[0,1].
- `pctValue(v)` — backend 0–100 → `%`; **N/A** for null/NaN/out-of-[0,100].
- `riskPct(graph)` / `riskValue(graph)` — honour `risk_available`; show **N/A** when
  the engine could not score, `0` for arithmetic only.

It never clamps a *valid* value to hide a bug — an out-of-contract value is surfaced
as **N/A** (an honest "this is wrong / unavailable"), which also makes any future
unit-mismatch immediately visible instead of silently capping at 100%.

---

## 5. Validation

- `backend/tests/test_risk_engine.py` (32 cases) — score ∈ [0,100]; confidence ∈
  [5,99]; every factor `0 < points ≤ weight`; `score == clamp(Σ points)` (no black
  box); wire fraction ∈ [0,1]; empty component invents no risk; a huge amount alone
  cannot create a case.
- `backend/tests/test_graph_layout.py`, `test_layout_quality.py` — unaffected, pass.
- `npx tsc --noEmit` — clean.

---

## 6. Remaining work (Phase 2 — explicitly scoped, not silently skipped)

The mandate's "React contains **no** risk calculation logic" is not yet fully met.
Four client modules still compute (real, deterministic, bounded — but in the wrong
tier): `ai/riskPropagation.ts` (per-node propagated risk + roles), `ai/graphClassifier.ts`
(pattern type + confidence), `ai/riskModel.ts` (blended anomaly score),
`ai/graphAnalysis.ts` (topology summaries). The backend already computes equivalents
(`v2.node_risk_scores`, `v2.node_intelligence`, `evidence`, `contributors`), so Phase 2
is a **wiring** exercise: expose a `/api/graph/intel` endpoint returning per-node
risk/role/confidence/evidence, consume it in `GraphScene`/`NodeInspector`/HUD via
`pctFraction()`, and delete the client calculators. This is deferred because doing it
blind would break live graph coloring (which currently depends on `riskPropagation`),
and it deserves its own verified change — not a rushed removal.
