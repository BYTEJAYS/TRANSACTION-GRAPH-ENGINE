# Red Team — Complete Audit (Phase 1)

**Target of audit:** `adversarial/` (the coupled Red Team ⇄ Blue Team ecosystem).
**Scope note:** the legacy `red_team/` package is a *scenario realism/diversity*
generator under a hard no-coupling isolation contract — by design it is **not** an
attack-discovery engine and is excluded here except where noted.
**Method:** every claim below is grounded in the live source as of this audit, not
inferred. File\:line references are exact.
**Status:** *Analysis only. No code changed.* This is the prerequisite report the
directive asks for before any rebuild.

---

## 0. Executive summary

The current Red Team is a **well-engineered, white-box-grounded, single-objective
genetic search** over a fixed set of 7 hand-coded attack transforms, evaluated
against 9 fixed fraud graphs produced by the defender's own simulator. It is
**correct, reproducible-in-intent, and scientifically honest** (the README and
white-box report already flag their own limitations). For what it is — a vertical
slice that proves the defender has a dominant structural blind spot
(`cross_component_split`, B1) — it is good work.

It is **not yet** an autonomous attack-discovery engine. Measured against a
research-grade adversarial system (DeepMind/Anthropic/DARPA bar), it has **one
fundamental architectural gap and three fundamental scientific gaps**:

1. **Architectural:** the loop is *open*. The "self-play" Blue hardener is
   proposal-only (`self_play/loop.py:51`, returns a dict, never hardens). Red
   improves; Blue never changes. There is no co-evolution, so nothing in the
   system can produce the AlphaGo/GAN dynamic the directive targets.
2. **Mode collapse is already present and unmeasured.** The README's headline —
   "`cross_component_split` appears in *every* winning family" — is the textbook
   signature of convergence to a single strategy. The search has **no novelty,
   diversity, or quality-diversity machinery** to counteract it.
3. **Overfitting is structural, not incidental.** The agents hard-code the
   defender's exact constants (the 46k–50k band, 6 h dormancy, degree cap 4).
   The search optimizes against **9 specific graphs at one seed**. Nothing here
   is expected to transfer to a hardened V2, to V1, or to an unseen typology —
   and transfer is never measured.
4. **The system only remembers wins.** Failed and dead-end attacks are discarded
   (`attack_memory/store.py:114`), so there is no self-reflection, no failure
   corpus, no "attack wisdom," and the genealogy is a family-grouping, not a real
   lineage tree.

Everything the directive lists beyond these — meta-controller, specialized
species, swarms, open-ended evolution, world model, counterfactual/causal
engines, hierarchical RL, foundation model, meta-learning, uncertainty-aware and
black-box modes, the adversarial scientist — is **absent or scaffold-only**. That
is expected at this stage; the value of this report is to sequence them and to fix
the validity problems *first*, because several headline numbers are not yet
trustworthy.

**Verdict:** strong foundation, honest authors, but currently a *single-strategy
white-box evasion optimizer*, not a discovery ecosystem. The gap is closable, and
the existing abstractions (genome, oracle, agent registry, memory) are the right
ones to build on.

---

## 1. What exists today (grounded inventory)

| Subsystem | File | What it actually is |
|---|---|---|
| Attack representation | `common/attack_graph.py` | `AttackGraph` = list of components + `AttackObjective` (source-out / sink-in value ≥ floor). `distortion()` = weighted node/edge churn + amount drift + fragmentation. Solid. |
| Blue coupling | `common/oracle.py` | In-process wrapper over real V2; **operation-level** aggregation (worst component verdict). White-box: returns evidence patterns, per-node risk, cluster risk. V1 path raises `NotImplementedError` (oracle.py:96). |
| Attack agents | `red_team/agents.py` | 7 transforms: `feature_mimicry, amount_dither, temporal_spread, relay_insertion, decoy_edges, sink_funnel, cross_component_split`. Each keyed to a specific white-box gate. |
| Genome | `red_team/base.py` | Ordered `[Move(agent, intensity)]`; `apply_genome` replays then `resplit_components`. Clean symbolic representation. |
| Base graphs | `red_team/graph_generator.py` | 9 archetypes from `blue_team_v2.simulation.Simulator(seed=42)`; objective derived from source/sink volumes. **One instance per archetype, one seed.** |
| Search | `red_team/evolutionary_engine/engine.py` | Warm-started GA; scalarized fitness; tournament + elitism; cache keyed by genome string. |
| RL | `red_team/rl_agent/spec.py` | MDP fully specified in a docstring; `train()` raises `NotImplementedError`. |
| GraphGAN | `red_team/graph_gan/spec.py` | Surrogate-distillation formulation chosen; `train()` raises `NotImplementedError`. |
| Memory | `attack_memory/store.py` | JSONL; families = sorted agent-set; `genealogy()` = family grouping; `hard_examples()` = successes only. |
| Curriculum | `curriculum/ladder.py` | Hand-authored L1–L10; L9/L10 have population=0 (not runnable). |
| Self-play | `self_play/loop.py` | Loop implemented; `ThresholdHardener.harden()` returns a *proposal dict*, never mutates Blue. |
| Eval | `evaluation/metrics.py` | ASR, mean downgrade, distortion-on-success, silenced-detector table. |
| Visualization | `visualization/__init__.py` | Empty (0 LOC). |

Headline result on record: **66.7 % ASR (6/9)**, `cross_component_split` in every
winning family, cashout/fan-in consolidation the one robust gate.

---

## 2. Findings by subsystem

### 2.1 Architecture
- **Open loop (critical).** `SelfPlayLoop` never closes — the hardener is a
  proposal generator (`loop.py:51–66`). Without a Blue update step there is no
  arms race, no robustness-gain measurement, no curriculum signal. *This is the
  highest-leverage single fix in the whole system.*
- **Single target.** Only V2 is wired (`oracle.py:92`). V1 — which carries the
  *learned* attack surface (IsolationForest poisonable buffer, untrained GNN,
  XGBoost) — is unreachable, so the entire "latent / memory-poisoning / ensemble"
  half of the directive has no environment to run against.
- **No controller layer.** There is no meta-policy above the GA. Population size,
  mutation rate, agent allow-list, and difficulty are fixed constants or indexed
  by round number (`loop.py:115`, `level()`), not regulated by Blue competence.

### 2.2 Attack generators (agents)
- **Count and coverage.** 7 agents vs the directive's ~10 species. Mapping:
  Structural ≈ `relay_insertion` (degree only — no centrality/density/clustering
  targeting); Feature ≈ `feature_mimicry`; Temporal ≈ `temporal_spread`;
  Community — *partial* (`decoy_edges` dilutes; no Louvain/modularity-aware
  agent); Confidence-manipulation — *implicit only* (stealth reward, no agent
  that explicitly drives risk to threshold−ε and probes the band); Latent-space,
  Memory-poisoning, Attention, Explainability, Ensemble — **absent**.
- **White-box overfit (generalization).** Agents encode the defender's literal
  constants: the `[46_000, 50_000)` structuring band (`agents.py:93`), the 6 h
  dormancy floor (`agents.py:113`), the degree cap tied to the ≥4 fan gate
  (`agents.py:142`). These are evasions of *this* rule set, not of the *concept*
  the rule approximates. Against a retuned V2 or any other detector they likely
  fail, and nothing measures that.
- **Stochastic agents, single realization.** `amount_dither`, `decoy_edges`,
  `temporal_spread`, relay/sink node ids all draw from `rng`. Each genome is
  evaluated **once** with an apply-rng seeded from the genome hash
  (`engine.py:62`). Fitness is therefore a *point sample*, not an expectation — a
  genome that "evades" may do so only under its one lucky realization.

### 2.3 Evolutionary engine
- **Scalarized single-objective fitness** (`engine.py:79`): `W.evasion·(1−det) +
  W.stealth·stealth − W.distortion·dist − W.complexity·complexity`. No Pareto
  front, no MAP-Elites, no QD archive. The directive explicitly asks for
  NSGA-II / MAP-Elites — none present.
- **No novelty / diversity preservation.** Selection is tournament + elitism with
  a string-keyed cache. There is no fitness sharing, niching, crowding distance,
  or behavioural-descriptor archive. Combined with the warm-start seeds that
  already contain the winning `cross_component_split` combo (`engine.py:146–152`),
  the population provably collapses onto that recipe — which is exactly what the
  README reports as the "headline finding." **Mode collapse is being reported as a
  discovery.**
- **Fixed operator set.** Mutation ∈ {add, remove, tune, swap, reorder}
  (`engine.py:109`); agents are a frozen registry of 7. There is **no mechanism to
  invent new primitives or operators** → not open-ended (no POET/AlphaEvolve
  mechanic anywhere).
- **Feasibility cliff.** Objective failure returns a flat `−infeasible_penalty`
  (`engine.py:69`). The graded `objective.shortfall()` signal exists
  (`attack_graph.py:71`) but is **unused** — the search gets a binary wall where a
  smooth gradient was available.
- **Reproducibility bug.** `seed = hash(key) & 0xFFFFFFFF` (`engine.py:62`) uses
  Python's salted `str.__hash__`. Unless `PYTHONHASHSEED=0`, the per-genome
  realization (and thus every reported number) **changes run to run**. The
  determinism the docstring promises is not actually delivered.

### 2.4 RL agent
- Spec-complete, code-absent. MDP (state/action/reward/transition) is well posed
  in `rl_agent/spec.py`; `train()` is `NotImplementedError`. No torch, no rollout,
  no vectorized envs, no checkpoints. Hierarchical RL (macro strategy / micro
  action) is *not* in the spec — the directive wants two-level policies; the spec
  is flat.

### 2.5 Graph generators
- **Distribution of size 9, seed of size 1.** `make_base_attacks(seed=42)` yields
  one graph per archetype. The Red Team evolves against these exact 9 objects.
  There is no instance sampling, no held-out typology, no OOD set, no procedural
  variation. Any ASR is an in-sample number by construction.
- **No generative attacker.** Topologies are human-authored archetypes; the system
  cannot synthesize a *novel* scheme shape (the GraphGAN that would do this is a
  scaffold).
- **Validity question on the dominant evasion.** `cross_component_split` cuts
  interior edges; the objective only checks source-out and sink-in value
  (`attack_graph.py:53–61`), so fragmenting the middle into singletons trivially
  "preserves the objective" while destroying the on-graph laundering path. This is
  framed as off-graph completion — defensible — but it means the headline attack
  is partly a property of a *permissive objective definition*, not only of a Blue
  blind spot. A research-grade write-up must separate the two (see §4).

### 2.6 Mutation operators / reward shaping
- Reward shaping covers **2.5 of the directive's 8 objectives** (evasion, stealth,
  distortion-penalty, complexity-penalty). Missing as explicit objectives:
  **novelty, transferability, persistence, realism, interpretability.** "Realism"
  in particular is only structural distortion — there is no check that the
  perturbed graph's amount/time/degree distributions resemble the benign corpus,
  so "stealthy" attacks can be statistically bizarre yet score well.

### 2.7 Memory systems
- **Wins only.** `hard_examples()` and `remember()` capture successes
  (`store.py:114`). Failures, dead-ends, and "surprising near-misses" are dropped
  → no self-reflection corpus, no failure-conditioned learning.
- **Genealogy is not lineage.** `genealogy()` groups records by family signature
  (`store.py:95`); it does not reconstruct parent→child trees. `parent_ids` is a
  field but is never populated by the GA path (`__main__.py:60`, `loop.py:102`
  both omit it). "Attack DNA / evolution path" is therefore unrealized.
- **Coarse family key.** Family = *sorted set* of agents (`store.py:74`) → ignores
  order and intensity, collapsing genuinely different attacks together.
- **No semantic memory / retrieval / embeddings.** No way to ask "find attacks
  similar to X." The attack-foundation-model and strategic-memory tiers
  (episodic/semantic/evolutionary) are absent.

### 2.8 Training loop / self-play / curriculum
- Loop runs but does not co-evolve (§2.1). Curriculum promotes by `6+rnd`
  (`loop.py:115`), not by mastery; L9/L10 are non-runnable stubs
  (`ladder.py:59–64`). There is no automatic difficulty regulation (no POET
  minimal-criterion coevolution, no competence-based promotion).

### 2.9 Attack database
- JSONL store is fine for inspection and small N. Family/hard-example queries are
  O(N) scans; no index for similarity, no vector store. Adequate now, a bottleneck
  once attacks number in the 10⁴–10⁶ the directive implies.

### 2.10 Visualization
- Empty package. No genealogy tree render, no fitness/ASR curves, no
  behaviour-space (QD archive) map, no detector-silencing heatmap. All the data
  exists in `history`/memory; nothing draws it.

---

## 3. Cross-cutting weaknesses (the directive's checklist)

| Concern | Status | Evidence |
|---|---|---|
| Missing capabilities | Large surface absent | meta-controller, species, swarm, world model, counterfactual, causal, foundation model, meta-learning, black-box — none exist |
| Bottlenecks | Oracle is the bottleneck | synchronous, in-process, single-thread V2 call per component; no batching/parallelism/surrogate |
| Weak reward shaping | Yes | scalarized; 2.5/8 objectives; `shortfall` unused; no realism term |
| Exploration limits | Severe | no novelty search, no QD, warm-start biases toward the known winner |
| Overfitting | Structural | hard-coded thresholds + 9 fixed graphs + single seed; no holdout |
| Mode collapse | Present, unmeasured | one strategy dominates every family |
| Attack diversity | Not optimized | no diversity metric in fitness or selection |
| Generalization | Untested | no transfer eval to V1 / hardened-V2 / OOD typologies |
| Scalability | Limited | O(pop·gen·archetype·component) real-V2 calls; per-archetype caches don't share |
| Compute efficiency | Limited | no surrogate world-model to amortize oracle; no vectorization; no GPU |
| **Scientific validity** | **At risk** | IF label leak (report §B5) not yet stripped; n=9, single seed, no CIs; hash-seed nondeterminism |

---

## 4. Validity issues to fix *before* trusting any number

These are ordered first deliberately — a discovery engine that reports
unreliable metrics is worse than no engine.

1. **Strip the eval label leak** (report §B5) and add an **out-of-typology
   holdout** before any ASR is quoted as a result.
2. **Pin determinism**: replace `hash()` seeding with a stable hash
   (`hashlib`), or set `PYTHONHASHSEED=0` in the runner; otherwise results are
   not reproducible.
3. **Evaluate stochastic genomes as expectations** (k realizations, report mean ±
   CI), not single samples.
4. **Report variance**: seed sweep over base-graph and GA seeds; ASR with
   confidence intervals, not 6/9 as a point.
5. **Disambiguate `cross_component_split`**: report it two ways — (a) under the
   current permissive operation-objective, and (b) under a stricter objective that
   requires an *on-graph* path from source to sink — so the reader can see how much
   of the 66.7 % is a real blind spot vs an objective-definition artifact.

---

## 5. Capability gap matrix vs the SOTA directive

Legend: ✅ present · 🟡 partial/scaffold · ⬜ absent.

| Directive capability | State | Note / nearest existing hook |
|---|---|---|
| Meta-Red-Team controller | ⬜ | curriculum is a fixed ladder, not a learned controller |
| Specialized species (Structural/Community/Temporal/Latent/Confidence/Mimicry/Memory/Attention/Explainability/Ensemble) | 🟡 | ~3.5 of 10 exist as single agents; 6 absent |
| Swarm / cooperative multi-agent attacks | ⬜ | genome is a solo sequence; no role/fitness-per-agent population |
| Open-ended evolution (POET/AlphaEvolve) | ⬜ | fixed agents + fixed operators |
| Quality-Diversity archive (MAP-Elites) | ⬜ | scalarized GA only |
| Novelty search | ⬜ | no novelty term anywhere |
| Attack genealogy / DNA tree | 🟡 | family grouping only; parent_ids unused |
| World model / Blue digital twin | ⬜ | GraphGAN surrogate is a scaffold |
| Counterfactual engine | ⬜ | — |
| Causal Red Team | ⬜ | — |
| Hierarchical RL | ⬜ | RL itself is spec-only; spec is flat |
| Multi-objective (NSGA-II/MAP-Elites) | ⬜ | linear scalarization |
| Transferability (future Blue / ensembles / OOD) | ⬜ | single fixed target, no transfer eval |
| Self-reflection / attack journal | ⬜ | failures discarded |
| Strategic memory (episodic/semantic/evolutionary) | 🟡 | episodic-of-wins only |
| Attack language / grammar / reusable programs | 🟡 | genome *is* a symbolic program; no grammar, composition, or library learning |
| Attack foundation model (embeddings/retrieval/generation) | ⬜ | — |
| Meta-learning (few/zero-shot to new Blue) | ⬜ | — |
| Uncertainty-aware attacks | ⬜ | oracle exposes `confidence`; never used to target ambiguity zones |
| Black-box mode (surrogate/boundary/query-efficient) | ⬜ | fully white-box; query cost untracked |
| Adversarial scientist (propose new theories/typologies) | ⬜ | — |

**Honest score: roughly 3 of 21 directive capabilities are realized, ~4 partial,
~14 absent.** The 3 that exist (symbolic genome, operation-level oracle,
finding-driven agents) are the right foundation; the rest is greenfield.

---

## 6. Recommended build order (no code changed — sequencing only)

Grouped by dependency, each phase enabling the next. Rationale: fix truth first,
then close the loop, then add diversity, then add the heavy ML.

**Phase A — Make the numbers trustworthy (prereq for everything).**
§4 items 1–5. Cheap, high-value, unblocks honest measurement.

**Phase B — Close the loop (unlocks co-evolution).**
Wire `ThresholdHardener` (and a successor logistic-calibration hardener) to a real
**V2 config object**; measure robustness gain (ASR before/after) and benign
false-positive cost. Promote the curriculum on *measured* Blue competence, not
round index. This is what turns the system from "evasion optimizer" into
"self-play," and it is mostly plumbing on top of what exists.

**Phase C — Kill mode collapse (unlocks discovery).**
Replace scalarized fitness with a **MAP-Elites / QD archive** over behaviour
descriptors (e.g. #components, agents-used, distortion bin, dominant-residual
detector) + a **novelty term**. This is the single change that most moves the
system toward "discover attacks humans never designed," and it reuses the existing
genome and oracle unchanged.

**Phase D — Specialize and cooperate.**
Add the missing species as agents (Community/Louvain-aware, Confidence-band
prober, Explainability, plus Latent/Memory/Ensemble *once V1 is wired*), then a
**swarm layer** (a population with per-agent roles/fitness composing one
operation). Add the **meta-controller** to manage population/diversity/mutation.

**Phase E — Generalize and go black-box.**
Wire V1 as a second oracle target; add **transfer evaluation** (attacks found vs
V2 measured on V1 / hardened-V2 / held-out typologies); add **black-box mode**
(surrogate + query budget). This is where overfitting gets measured and beaten.

**Phase F — The heavy ML and the scientist.**
Build the PPO trainer (then hierarchical RL), the **surrogate world model** (which
also unblocks GraphGAN and counterfactual search), the **attack foundation model**
(embeddings → retrieval → generation), meta-learning, and finally the
**adversarial-scientist** layer that proposes new typologies from the QD archive
and genealogy. These depend on A–E being real.

---

## 7. Bottom line

The Red Team today is a **disciplined, honest, white-box single-strategy evasion
optimizer with an open self-play loop.** Its abstractions (symbolic genome,
operation-level oracle, finding-driven agents, JSONL memory) are sound and worth
keeping. Its gaps are not bugs to patch but **whole missing layers** — closed-loop
co-evolution, quality-diversity, generalization measurement, and the world-model /
foundation-model / scientist stack.

The correct next move is **not** to start building species or world models. It is
to (A) make the existing numbers trustworthy and (B) close the loop — because
until Blue adapts and until ASR is measured out-of-sample with variance, every
exotic capability added on top would be optimizing an unreliable signal. Do those
two, add quality-diversity to break the mode collapse, and the system finally
earns the name *attack-discovery engine*.

---

## 8. Phase A — IMPLEMENTED (validity fixes)

Status: **done & verified.** Code changed in `engine.py`, `config.py`,
`attack_graph.py`, `evaluation/metrics.py`, `__main__.py`. No search behaviour was
altered beyond making evaluation robust; the optimization target is unchanged.

1. **Deterministic seeding.** `engine.stable_seed()` (blake2b) replaces the
   process-salted builtin `hash()`. Verified: identical ASR / downgrade / oracle
   calls across repeated runs (previously drifted with `PYTHONHASHSEED`).
2. **Expectation over agent randomness.** Each genome is now evaluated over
   `eval_samples` realizations (default 3). A genome counts as a success only if
   it evades in a `success_quorum` fraction of them (default 1.0 → must evade in
   *every* realization). `Individual` now carries `evasion_rate`, `obj_ok_rate`,
   `detection_std`. This removes the single-lucky-draw failure mode.
3. **Variance reporting.** `--trials N` reruns the whole campaign over N seed
   pairs and reports ASR as **mean ± 95% CI** with range, not a point.
4. **Strict-objective disambiguation.** `AttackObjective.on_graph_satisfied()`
   requires value to reach a sink along a connected on-graph source→sink path (no
   off-graph-completion credit). The campaign now reports
   `attack_success_rate_strict` and `partition_dependent_evasions` alongside the
   permissive ASR.

**Headline empirical result of the fix (smoke runs):** permissive ASR reproduces
(~0.56–0.67 depending on seed) but **strict ASR is 0.0 — every winning attack is
partition-dependent.** The genealogy confirms `cross_component_split` is present
in *every* winning family. Interpretation: the previously reported ASR conflates
two things — a genuine detector blind spot (component isolation, B1) **and** a
permissive objective that grants free credit for off-graph completion. Both are
real, but they must be reported separately. This is exactly the artifact §4.5
warned about, now quantified.

**Still open from §4 (carried forward):** the IsolationForest label leak (§B5)
lives in the **V1** eval path; it is *not* in the current adversarial measurement
loop (the oracle targets V2 only), so it is deferred to Phase E when V1 is wired
as a second target. An out-of-typology holdout (train on a subset of archetypes,
measure transfer to held-out ones) is the remaining Phase A item and pairs
naturally with the Phase E transfer harness.

---

## 9. Phase B — IMPLEMENTED (closed the self-play loop)

Status: **done & verified.** The loop now co-evolves: Blue's decision surface
actually changes between rounds and the robustness gain + benign false-positive
cost are measured, not proposed.

**Non-destructive override seam.** `blue_team_v2/types.py` gains a `Thresholds`
dataclass (defaults = shipped constants); `engine.py` takes an optional
`thresholds=` and uses it for every verdict decision. Verified: a default engine
is **byte-identical** to the shipped one on all 9 archetypes (verdict + cluster
risk), so the deployed detector is unchanged unless a tightened config is supplied.
`adversarial/common/blue_config.py` (`BlueConfig`) is the adversarial-side handle;
the oracle is built from it.

**Real hardener.** `ThresholdHardener` (in `self_play/loop.py`) lowers the REVIEW
threshold to re-flag near-threshold evasions, bounded by a benign-FP budget. Both
the re-flag rate and the FP rate are **closed-form** over stored risks (cluster
risk is threshold-invariant), so the measurement is exact. `make_benign_corpus()`
supplies the legitimate-traffic validation set.

**Closed loop.** `SelfPlayLoop.run()` measures ASR *before* and *after* hardening
each round (robustness gain), the benign FP cost, and promotes the curriculum on
mastery (`asr_after ≤ mastery_asr`) rather than by round index. CLI:
`python -m adversarial.self_play --rounds 4 [--fp-budget 0.05]`.

**Headline finding from the closed loop (this is the important part).** At a
realistic **5% FP budget, hardening yields zero gain** — because V2's benign risk
distribution is *hot*: the simulator's own `normal()` graphs score a **median
cluster risk ≈ 0.52**, with the FP rate at the shipped 0.62 threshold running
**8%→52% as graph size grows** (not a small-graph artifact — median is flat across
sizes; one benign graph even scores 0.962/FRAUD). The Red Team's evasions land in
exactly that **0.52–0.61 band**, i.e. *statistically embedded inside benign
traffic*. To re-flag them you must drop REVIEW to ~0.55, which pushes benign FP to
**50–80%**. Raising the budget to 30% does let the loop work — round 0 hardens
0.620→0.605, cutting ASR 0.56→0.22 (gain +0.33) at FP 15%→20%, after which Red
re-adapts to a ~0.44 equilibrium — but the FP cost is unacceptable for production.

**Conclusion:** global-threshold hardening is the *wrong lever*. It cannot
separate fraud-evasions from benign traffic because the detector does not separate
them in *risk space* to begin with. This empirically confirms the audit's claim
that `ThresholdHardener` is too weak and motivates the next hardener: **per-detector
gate tightening / a learned calibration of the 16 scoring factors** that increases
fraud–benign *margin*, not just shifts a global cutoff. That is the concrete entry
point for Phase C/D.

---

## 10. Phase C — IMPLEMENTED (quality-diversity kills the mode collapse)

Status: **done & verified.** The scalar GA's convergence to a single recipe is
replaced (additively — the GA is untouched and still available) by a MAP-Elites
illuminator that keeps the best attack of *every kind*.

**Design.** `red_team/quality_diversity/map_elites.py`. Behaviour descriptors =
**fragmentation** (num_components, 5 bins) × **distortion** (6 bins) → a 30-cell
grid. Quality = pure **evasion + stealth** (distortion is now a *diversity axis*,
not a penalty), so each cell holds "the strongest evasion achievable at this
fragmentation and this distortion." Selection is **curiosity-biased** (cells that
recently produced archive improvements are sampled more) with a uniform fallback —
maintaining exploration instead of collapsing. It reuses `EvolutionaryRedTeam` for
evaluation (inheriting the Phase-A expectation eval + genome cache) and for the
mutation/crossover operators, so QD and the GA are directly comparable.
CLI: `python -m adversarial.qd --evaluations 2000 [--detail hybrid --compare]`.

**Verified result (1,200 evals/archetype, eval_samples=2).**

| | scalar GA | MAP-Elites |
|---|---|---|
| distinct evading technique families (all archetypes) | **5** | **12** |
| evading operating points kept | 5 (one per archetype) | **33 cells** |
| `hybrid` archetype families | 1 | **6** |
| cheapest `hybrid` evasion found | (single point) | distortion **0.33** at 6 components |

The illumination grid for `hybrid` fills an entire frontier across fragmentation
4–15 and five distortion levels — a *family* of viable evasions at different
cost/fragmentation operating points — where the GA kept exactly one. Every evading
family still contains `cross_component_split` (consistent with §8's strict-ASR = 0:
partitioning is *necessary*), but QD now discovers the rich diversity *around* that
necessity (different combinations of dither / decoy / relay / sink-funnel / temporal
/ feature mimicry). The diverse evasions are written to attack memory, giving the
next (detector-level) hardener the varied corpus §9 showed it needs — directly
connecting Phase C back to Phase B.

**Why this matters for the program:** the system now *discovers a space of
attacks* rather than optimizing toward one. This is the prerequisite for everything
downstream — a meaningful curriculum, a hardener that must close many gaps at once,
novelty/genealogy that has real variety to organise, and an attack foundation model
with a diverse corpus to learn from.

---

## 11. Phase D (first slice) — IMPLEMENTED (detector-level hardener)

Status: **done & verified.** This is the successor §9 called for — hardening that
adds fraud–benign *margin* instead of shifting a global cutoff — and it closes the
loop the threshold hardener could not.

**Design.** `self_play/detector_hardener.py`. A logistic calibration over V2's own
**16 scoring factors**, aggregated per cluster (p90 of each factor signal), fit on
a labelled corpus: diverse MAP-Elites evasion fragments (positive) vs benign
traffic (negative). The calibrated probability rides on top of native V2 risk as
`risk' = max(native_risk, P(evasion))`, so a benign cluster keeps its native
sub-threshold risk while an evasion is pushed over the line. Wired through the
oracle's existing Detection interface (`calibrator=`), so nothing shipped is
mutated and the whole loop/metrics work unchanged. Campaign:
`python -m adversarial.self_play.detector_harden`.

**Verified result.**

| measure | value |
|---|---|
| evasion-fragment re-flag (held-out) | **100%** |
| calibrator benign FP (held-out) | **1.2%** |
| native V2 benign FP (pre-existing) | ~11–15% |
| hardened benign FP | ~12.5% (**+1.2%** from calibration) |
| **ASR, Red re-evolving vs hardened** (ga 30×14) | **0.556 → 0.000** (gain +0.556) |

Even with a larger Red search budget, Red re-evolving against the hardened detector
finds **no** evasion. The gain is real, not memorised, because the dynamic test
uses fresh attacks.

**Mechanism (and why it is robust).** The dominant calibrated factor is **volume
(+1.55)**. The laundering objective *requires* delivering ≈target_value to the
sinks; benign traffic is low-value. So every evasion has a high-volume tell — most
sharply at the sink-bearing component — that Red **cannot remove without breaking
its own objective**. The calibrator found the one invariant the attack space cannot
escape, and which V2 demotes (volume weight 0.06). This is the margin the global
threshold could not provide.

**Honest caveats (carried as next-step work):**
- The benign corpus (`Simulator.normal`) is **low-value**; the volume signal would
  raise false positives on *legitimate high-value* transfers, which the corpus does
  not contain. The +1.2% incremental FP is therefore optimistic — a realistic
  benign corpus with large legit flows is needed before quoting an FP number.
- The ~11–15% **native** benign FP is V2's own pre-existing problem (Phase B), not
  introduced here, and remains unaddressed.
- A future "volume-dilution" agent (split sink inflow across many sub-threshold
  components while still delivering target_value) is the obvious probe against this
  hardener; the current 7 agents do not express it. That is exactly the kind of
  next attack species Phase D's arsenal expansion should add — and the self-play
  loop would then pit it against this calibration.

---

## 12. Phase D (second slice) — IMPLEMENTED (volume-dilution agent + arms race)

Status: **done & verified.** Added the `volume_dilution` attack agent (an 8th
agent, wired into the registry / curriculum / GA seeds) and a multi-round
**detector arms race** (`self_play/arms_race.py`) in which Blue *refits* the
16-factor calibration on everything Red has produced and Red re-evolves against the
strengthened detector each round.

**The probe.** `volume_dilution` pads each component with low-volume benign nodes so
the unavoidable high-volume sink falls outside the hardener's p90 aggregation. To
survive `cross_component_split` it roots the pad mass at sinks via *protected*
(target=sink) edges, with bounded fan-in so it does not trip the fan-in gate.

**Result — Blue wins decisively.**

| | value |
|---|---|
| arms race round 0: ASR before → after first calibration | **0.89 → 0.00** |
| arms race rounds 1–4 (Red re-evolving) | ASR stays **0.00** |
| direct `volume_dilution` probe vs the calibrated detector | **0 / 9 evasions** (risk 0.87–1.00) |

**Interpretation (the real finding).** A *single-axis* dilution cannot beat the
learned hardener, and the reason is deeper than "volume is the tell": the 16-factor
logistic captures a **multi-factor fraud signature**. A laundering cluster still
contains real sources, sinks, relays and chains whose joint factor profile differs
from benign random traffic across *many* axes at once, so burying one axis (volume)
leaves the rest intact and the cluster still reads as fraud. To evade, Red would
have to dilute/mimic *all* discriminative factors simultaneously while preserving
the objective — a far harder problem than skirting any single gate. This is the
margin-based robustness the per-gate detectors and the global threshold lacked.

**Caveat (unchanged and important).** This robustness is conditioned on the current
**low-value benign corpus**; a richer benign corpus with legitimate high-value /
structured activity could narrow the fraud–benign margin and give dilution/mimicry
more room. A realistic benign corpus + a **multi-factor mimicry agent** (the natural
next probe) are the open items that would genuinely stress this result.

> **CORRECTION — see §13.** Both probes were then built, and they *overturn* the
> optimistic conclusion above. On a realistic benign corpus the hardener's low-FP
> claim collapses. Read §13 as the corrected verdict for Phases B–D.

---

## 13. Realistic benign corpus + multi-factor mimicry — the Phase D claim, CORRECTED

Status: **done & verified.** Both items from §12's caveat were implemented:
`make_benign_corpus(realistic=True)` now includes legitimate traffic that
*structurally resembles* fraud (payroll fan-outs, merchant fan-ins, high-value
corporate payments, recurring households), and `profile_mimicry` is an 8th… 9th
agent — a coordinated multi-factor benign-profile match (identity + temporal +
amount texture + cover traffic) composing with `volume_dilution` /
`cross_component_split` on structure. Both are wired into the registry, curriculum,
and GA seeds.

**The realistic corpus demolishes the earlier FP numbers.**

| benign category | native V2 false-positive rate |
|---|---|
| normal (low-value random) | **5%** |
| merchant fan-in | 35% |
| household recurring | 45% |
| corporate high-value | **85%** |
| payroll fan-out | **100%** |
| **aggregate (realistic mix)** | **56.7%** (vs 11.7% on the simple corpus) |

V2 flags **every** legitimate payroll, **85%** of large supplier payments, and
nearly half of ordinary household activity as SUSPICIOUS/FRAUD. It only reliably
passes trivial low-value noise. The hardened (calibrated) detector is **63.3%** FP
on the same realistic mix — the calibration adds margin on top of an already broken
baseline.

**The "Blue wins" result was an illusion of the corpus.** The dynamic test still
shows the calibrator driving ASR to 0 (baseline 0.444 → calibrated 0.000) *even
when trained on realistic benign* — but it now does so by being **trigger-happy**,
not by *separating* fraud from legitimate activity. The volume/structure signals
that suppress laundering are the **same** signals that fire on legitimate high-value
and structured business. Phase D's headline "ASR → 0 at +1.2% FP" was a pure
artifact of a benign corpus that never contained legitimate big money.

**The real, corrected finding (the most important of the whole engagement):**
fraud and legitimate structured/high-value activity are **not separable by V2's 16
factors**. Neither V2 (≈57% FP) nor a volume-margin calibration (≈63% FP) is
deployable on realistic traffic. `profile_mimicry` is integrated and available to
the search, but it does not help Red — because the detector's failure is on the
**false-positive side**, not the evasion side. Real hardening cannot come from
re-weighting these factors; it needs signals that distinguish laundering from
*legitimate* fan-in/fan-out/high-value flows (provenance, account history,
counterparty legitimacy, cross-operation context) that the current feature set
simply does not contain.

**This vindicates the Phase A discipline:** an honest evaluation corpus turned a
celebrated +1.2%-FP "win" into a 63%-FP non-result. Every gain in this program must
be quoted against the realistic corpus from here on.

**Engineering note (scalability, audit §3 confirmed):** `volume_dilution` /
`profile_mimicry` produce large, heavily fragmented graphs, and per-component V2
analysis makes QD corpus-building with these agents slow enough to need a surrogate
world-model (the deferred Phase F item) before scaling these runs up.

---

## 14. Provenance detector — IMPLEMENTED (the missing signal §13 demanded)

Status: **done & verified.** §13 concluded that real hardening needs a signal that
distinguishes laundering from *legitimate* structured/high-value activity — not a
re-weighting of the 16 structural factors. This builds exactly that and it resolves
both failure modes at once.

**Design.** `common/provenance.py`. A `ProvenanceRegistry` models the bank's KYC /
account-history base: each established customer has an *establishment* score from
verified account age + prior legitimate volume — data the **attacker cannot write**
(it can forge a node's `transaction_count` in the submitted graph, but it cannot
mint a KYC identity in the bank's records). `ProvenanceScorer` computes a
value-weighted **unverified ratio** per component and adjusts risk two ways: it
*attenuates* clusters of established customers (clearing the legitimate
payroll/corporate false positives) and *floors* the risk of value moving through
unverified accounts (catching fresh-account laundering). Wired through the oracle
via `provenance=` alongside the calibrator; benign generators now draw their
participants from the KYC customer pool, fraud/attack accounts stay outside it.

**Verified result — both error rates hit the floor at once.**

| | native V2 | volume calibration (§11) | **provenance** |
|---|---|---|---|
| benign FP (realistic corpus) | 43.8% | 63.3% | **0.0%** |
| payroll / corporate / merchant / household FP | 100 / 95 / 50 / 65 % | — | **0 / 0 / 0 / 0 %** |
| fraud archetypes flagged | 9/9 | 9/9 | **9/9** |
| ASR, Red re-evolving (GA) | 0.444 | 0.000 | **0.000** |

Where the volume calibration drove ASR to zero only by over-flagging everything
(63% benign FP), provenance drives ASR to zero **at 0% benign false positives** —
the first hardener in the program that is actually deployable on realistic traffic.

**Why it is robust where structural hardening was not.** The signal is *orthogonal
to graph shape*: (1) it **fixes false positives** because legitimate big money moves
between established customers, so hub/high-value structure no longer condemns it;
(2) it is **immune to fragmentation (B1)** — splitting a scheme into singletons does
not make fresh mules verified, so every fragment keeps unverified-ratio ≈ 1 and
floors to FRAUD; (3) it **cannot be spoofed** by `feature_mimicry` /
`volume_dilution` / `profile_mimicry`, which manipulate the submitted graph but not
the KYC store. This is why ASR collapses even though Red has its full arsenal.

**Stated limitation = the next Red probe.** Provenance is defeated by
**account-takeover**: routing laundering through a *real* customer's verified
account drops the unverified ratio and slips under the floor. This is the correct
hard residual (ATO is genuinely the difficult case in production AML), and an
`account_takeover` agent — compromise a verified node and originate/relay through it
— is the obvious next adversary that would push this arms race forward honestly.

**Arc conclusion.** A→D plus §13–§14 trace a complete adversarial-science loop:
trustworthy metrics → closed loop → diversity → a hardener that *looked* decisive →
an honest corpus that *falsified* it → and finally the orthogonal signal that
genuinely separates fraud from legitimate activity. The system found not just
attacks but the **defender's true missing capability**, which is the point of the
whole program.

---

## 15. End-to-end self-play, folded (provenance in the loop)

Status: **done & verified.** The whole co-evolution now runs as one escalating
loop (`self_play/arms_race.py`), scored on the realistic KYC-drawn benign corpus
every round so robustness and false positives are never traded silently.

**Escalating defense stack (additive, non-destructive):** native V2 → + provenance
→ + learned 16-factor calibration. Blue deploys provenance on its first breach and
refits the calibration (the residual responder) on every evasion fragment seen.

**Verified run.**

```
round 0: faced[native V2]                ASR 0.44 → 0.00  benign_FP 0%   (Blue deploys provenance + calibration)
round 1: faced[native V2+provenance+cal] ASR 0.00 → 0.00  benign_FP 0%
round 2: faced[native V2+provenance+cal] ASR 0.00 → 0.00  benign_FP 0%
round 3: faced[native V2+provenance+cal] ASR 0.00 → 0.00  benign_FP 0%
```

Red breaches native V2 (ASR 0.44); Blue responds by deploying the provenance signal
and refitting the calibrator; from round 1 on, Red — with its full arsenal including
`volume_dilution` and `profile_mimicry` — cannot regain a single evasion, and the
benign false-positive rate stays at **0%** throughout. End state: laundering blocked
at a deployable false-positive cost, in a single end-to-end loop.

This is the consolidated deliverable of the program: a closed Red ⇄ Blue ecosystem
in which Red's pressure drove Blue from a 44%-evadable / 44%-false-positive detector
to one that blocks the full attack arsenal at zero false positives — and the one
remaining way through (account-takeover, §14) is identified and left armed for the
next turn.

---

## 16. Account-takeover — IMPLEMENTED (the §14 residual, realised)

Status: **done & verified.** §14 stated provenance's one admitted weakness in its own
docstring: it floors fresh-account value but *trusts value moving between established
customers*, so a scheme **routed through real customer accounts the attacker has
seized** defeats it. That was left "armed for the next turn." This realises it as an
attack agent and measures whether the predicted breach is real. It is.

**Design.** New agent `account_takeover` (`red_team/agents.py`) plus a finite pool of
compromised verified accounts (`set_compromised_accounts()`), which a runner must draw
from the *same* registry the Blue Team's `ProvenanceScorer` trusts — the agent can only
"verify" accounts the defender genuinely knows. Provenance's unverified ratio is
value-weighted and a rupee counts as trusted only when **both** edge endpoints are
established (`trust = min(est(src), est(tgt))`). So the agent spends its takeover budget
greedily on the **highest-value edges**, relabelling both endpoints to seized verified
identities (reusing already-seized nodes for free, so a predecessor→sink consolidation
path gets fully verified once the shared node is taken). Only identities change — amounts,
edges and topology are untouched and the objective's source/sink sets are relabelled in
lock-step — so the laundering goal is exactly preserved. The cost is realism/exposure:
every breach is paid for in accounts seized, which the search trades off.

**Controlled experiment** (`self_play/account_takeover.py`): one provenance-hardened
Blue, one Red search, one base-graph set, the full agent arsenal — the *only* thing that
varies is the attacker's seizure budget. Budget 0 makes `account_takeover` a no-op, which
reproduces the §14 "provenance vs the standard arsenal" control exactly.

**Verified result — provenance is breached, and cheaply.**

```
seizure-budget sweep (ASR vs the provenance-hardened Blue Team, full Red arsenal):
   seized=  0    ASR = 0.00   [—]                                  (no takeover — §14 control)
   seized=  8    ASR = 0.89   [account_takeover×8, cross_component_split×1]
   seized= 24    ASR = 1.00   [account_takeover×9, cross_component_split×1]
   seized=120    ASR = 1.00   [account_takeover×9, cross_component_split×1]

mechanism (cashout_network, native risk forced to 1.0):
   unverified-value ratio   1.00 → 0.00
   provenance-adjusted risk 1.00 → 0.25     (REVIEW 0.62 / HIGH 0.83)
```

The control reproduces §14 (ASR 0.00 — provenance holds against the entire standard
arsenal). Granting the attacker a takeover capacity flips it: **just 8 seized verified
accounts → ASR 0.89; 24 → 1.00.** The small budget is the alarming part — because
provenance weights by value and the agent spends on the largest edges first, the attacker
only needs to own the few high-value consolidation accounts, not the whole scheme. The
mechanism panel shows it directly: routing the cash-out path through seized identities
collapses the unverified-value ratio 1.00→0.00, so provenance *attenuates* the cluster
to 0.25 (LOGGED) instead of flooring it.

**What this means.** This is not a flaw in provenance — it is the exact boundary §14
claimed, now demonstrated rather than asserted: provenance proves an account is
*established*, not that an established account is *behaving normally*. The honest
conclusion of the whole A→§16 arc: each defensive signal closes the gap the last attack
opened and exposes the next one. The residual now armed for the following turn is a
**behavioural** signal on verified accounts — pass-through velocity, balance throughput,
and dormancy-break measured against each account's *own* history — which catches a seized
account being used as a conduit even though its KYC standing is genuine. That is the next
Blue build; `account_takeover` is the adversary that will hold it honest.

**Backward-compatibility checked.** With no pool set, `account_takeover` is a no-op: the
main GA still reports ASR 0.667 (all partition-dependent) and the end-to-end arms race
still drives ASR→0.00 at 0% benign FP, both byte-identical to before this agent existed.

---

## 17. Behavioural-conduit detector — IMPLEMENTED (the §16 counter)

Status: **done & verified.** §16 ended with the residual armed: provenance proves an
account is *established*, not that an established account is *behaving normally*, so a
seized real customer defeats it. This builds the missing behavioural signal, closes the
§16 breach, confirms it costs no new false positives, and identifies where Red goes next —
a complete arms-race round.

**Design.** `common/behavioral.py`. The bank knows not just *that* a customer is
established but *how it behaves*: a per-account **baseline** (typical throughput +
transaction size, by customer segment — household / retail / salaried / merchant / SME /
corporate), held in its records and, like establishment, **unforgeable by the attacker**.
`BehavioralScorer.conduit_anomaly` measures, for each *verified* account carrying a
meaningful share of a component's value, how far its observed throughput exceeds *its own*
baseline; `adjust` re-floors risk on that anomaly. It only ever **raises** risk, so it
composes after provenance (which does the clearing) — wired through the oracle's new
`behavioral=` param. To make the false-positive test sound, the realistic benign corpus is
drawn **segment-consistently** (a corporate payment between corporate-baseline accounts, a
household transfer between household accounts) and each benign account is sized to operate
*within* its own envelope by construction.

**Controlled experiment** (`self_play/behavioral_detector.py`): escalating defense
(native → provenance → +behavioural), Red running its full arsenal including
`account_takeover` each time, three conditions varying only the defense and the *kind* of
account the attacker can seize.

**Verified result.**

| condition | defense | seized accounts | ASR |
|---|---|---|---|
| **A** | provenance | any verified (phished consumers) | **1.00** |
| **B** | provenance + behavioural | any verified (phished consumers) | **0.00** |
| **C** | provenance + behavioural | high-baseline (corporate / SME) | **1.00** |

```
benign FP (segment-consistent corpus):  provenance 0%   provenance+behavioural 0%
mechanism (cashout_network, native risk forced to 1.0):
   seize household conduit   provenance→0.43   conduit_anomaly 0.97   final risk 0.92  (HIGH — caught)
   seize corporate account   provenance→0.42   conduit_anomaly 0.00   final risk 0.42  (within envelope — evades)
```

The §16 breach (A: ASR 1.00) is **completely closed** by the behavioural signal (B: ASR
0.00) at **0% added benign false positives**: a phished household pushing laundering-scale
value sits at ~25× its own baseline (anomaly 0.97 → risk re-floored to 0.92/HIGH), while a
legitimate corporate ₹2M payment sits at ≤1× and is untouched. provenance proves the
*identity*; behavioural checks the *behaviour*; together they separate a hijacked customer
from a normal one.

**The next residual (C).** The signal is a per-account *envelope*, so the surviving attack
is to seize accounts whose envelope already supports the volume — corporate / SME
identities whose baseline is laundering-scale (ASR recovers to 1.00, anomaly 0.00). That is
the honest boundary, and it is a far costlier attack: those accounts are ~7% of the base
(vs the household majority a phishing campaign actually harvests) and much harder to take
over, or the attacker must split the flow across enough seized accounts that each stays in
profile. Either way the cost climbs — the recurring lesson of this engagement: each Blue
signal does not end the game, it raises the price of the next evasion.

**Caveat (carried forward, per §13 discipline).** The 0% behavioural FP is partly *by
construction*: benign accounts are sized to their baseline, and the baseline itself is
synthetic. In production the baseline is an estimated high-percentile of real account
history, so both the FP rate and the tolerance must be re-measured on real data before the
number is quoted — exactly the realism caveat §13/§14 attached to every corpus claim. What
transfers is the *mechanism*: a per-account behavioural envelope is the signal that
separates an account-takeover conduit from a legitimate established customer, which neither
the 16 structural factors nor provenance can.

**Backward-compatibility checked.** The new `behavioral=` oracle param defaults off; the
segment-aware benign path is gated on an optional `registry=` (the flat-`pool` path is
preserved by a single (k+1)-draw helper). The main GA still reports ASR 0.667, the
account-takeover probe still 0.00→0.89→1.00, and the end-to-end arms race still ASR→0.00 at
0% FP — all unchanged.

---

## 18. Conduit-split mule mesh — IMPLEMENTED (the §17 residual) + full-stack arms race

Status: **done & verified.** §17 closed simple account-takeover but named two residuals:
seize baseline-appropriate accounts, or *split the flow so each seized account stays in
profile*. This builds the second — the harder, more general one — adds an arsenal-isolation
control so each capability can be measured cleanly, and folds the whole defense into one
escalating end-to-end loop. The honest conclusion points back at B1.

**The obstacle the agent had to solve.** Provenance is value-weighted and flags *any*
component, so the whole value-path must be verified end-to-end; the behavioural detector
flags any verified account moving past its baseline. A consumer mule (baseline ~₹20k) can
neither carry a ₹120k laundering edge (over baseline) nor leave it unverified (provenance).
The only escape is to **subdivide the value itself**.

**Design.** New agent `conduit_split` (`red_team/agents.py`) + a per-account capacity
estimate the attacker learns from a seized victim's statements
(`set_compromised_accounts(ids, capacities=)`). It reconstitutes the laundering as a thin
**mule mesh**: many small transfers from seized origin-mules to seized cash-out-mules, every
edge verified end-to-end (beats provenance), every account within its own envelope (beats
behavioural), degree ≤3 and low-value (beats the structural detectors). The objective is
preserved — the mesh moves the full target value — at the cost of *maximum distortion* (the
original graph is gone) and a *large seized-account count* (≈ value ÷ consumer-baseline per
side). To measure each capability in isolation, the GA gained an `allowed_agents` arsenal
restriction (`EvolutionConfig.allowed_agents`).

**Verified — the behavioural detector (§17) is breached by the mesh, and only by it.**
GA, provenance + behavioural defense, household seized pool:

```
arsenal WITHOUT conduit_split   ASR = 0.00     (simple takeover stays closed, §17)
arsenal WITH    conduit_split   ASR = 1.00     (conduit_split in 9/9 winners)
```

Extended `behavioral_detector.py` (FP measured on the segment-consistent corpus):

| cond | defense | seized | arsenal | ASR |
|---|---|---|---|---|
| A | provenance | household | takeover | **1.00** |
| B | + behavioural | household | takeover | **0.00** |
| C | + behavioural | corporate/SME | takeover | **1.00** |
| D | + behavioural | household | **+ conduit_split** | **0.89** |
| | benign FP | | | **0% / 0%** |

B closes the simple takeover at 0% FP (§17); C and D are the two residuals §17 predicted,
now realised — C buys evasion with rare hard-to-seize corporate accounts, D buys it with a
mesh of ~100 in-profile consumer mules.

**Full-stack escalating arms race** (`self_play/full_stack.py`): one closed loop, Blue's
defense escalating native V2 → + provenance → + behavioural → + calibration, Red running the
full arsenal (incl. `account_takeover` + `conduit_split`) against a fixed seized-consumer
pool, scored every round on the realistic benign corpus.

```
 round 0: faced[native V2]                          ASR 0.89→0.33  FP 0%  → +provenance
 round 1: faced[native V2+provenance]               ASR 1.00→1.00  FP 0%  → +behavioural
 round 2: faced[native V2+provenance+behavioural]   ASR 1.00→1.00  FP 0%  → +calibration
 round 3: faced[…+calibration]                      ASR 1.00→1.00  FP 0%  [conduit_split×9]
 round 4: faced[…+calibration]                      ASR 1.00→1.00  FP 0%  [conduit_split×9]
 start: ASR 0.89 vs native V2   end: ASR 1.00 vs the full stack   benign FP 0% throughout
```

Once `conduit_split` is in the arsenal it dominates from round 0 — every Blue layer is
deployed in turn and **none lowers ASR**, while benign FP stays at 0% (Blue is not
over-flagging; it simply cannot see the fragmented mesh). This is exactly why the
arsenal-isolation control matters: the clean "behavioural closes simple takeover" result is
only visible in the pinned-arsenal A–D table above; in the open loop the strongest evasion
masks the per-layer contributions. The loop's verdict is that the whole **per-component**
defense stack is bypassed by the mesh at no false-positive cost.

**The honest end state — the residual is B1.** `conduit_split` wins by *fragmenting* the ring
into many small hub-less consumer components. Each component, in isolation, is a handful of
verified accounts moving in-profile money — indistinguishable from benign. Provenance and the
behavioural detector are both **per-component** signals, and so is the V2 architecture they
sit in; none can see that fifty such components are one coordinated mule network. A learned
per-component calibration can't separate the mesh from benign without over-flagging (the §13
lesson). The signal that *would* catch it — many freshly-coordinated verified consumer
accounts forming one fragmented flow — is **cross-component / cross-session**, i.e. exactly
the **B1 blind spot** flagged in the white-box report on day one. The engagement closes where
it opened: every orthogonal per-component signal (provenance, behavioural) raises the
attacker's cost, but the deepest residual is the architectural one — V2 analyses each
component in isolation — and only an operation-level correlator can close it.

**Backward-compatibility checked.** `allowed_agents` defaults to the full registry; the
capacity arg defaults empty; `conduit_split` is a no-op with no seized pool. The main GA
still reports ASR 0.667, the account-takeover probe 0.00→0.89→1.00, the §15 arms race
ASR→0.00 at 0% FP — all unchanged.

---

## 19. Cross-component coordination detector — IMPLEMENTED (the B1 counter)

Status: **done & verified.** §18 ended at the architectural residual: the mule mesh is invisible
to every PER-COMPONENT signal because it fragments one ring into many hub-less consumer
components, each benign in isolation. The only thing that can catch it is a signal that sees
ACROSS components — the B1 capability the engagement flagged on day one. This builds it.

**Design.** `common/coordination.py` + a new operation-level seam in the oracle
(`OperationDetection.coordination_verdict`, oracle `coordination=` param). `CoordinationScorer`
scores an OPERATION — the set of components a cross-session linkage (shared device / funding
source / timing burst) has tied together — not a component. Across that linked set the mesh has
a signature no legitimate operation has at once:

  * **hub-less** — a legitimate fan (payroll, merchant, supplier run) is anchored by a
    high-baseline business account; the mesh is deliberately hub-less so its value never
    concentrates. A single high-baseline account present ⇒ legitimate fan ⇒ risk 0.
  * **consumer-heavy** — dozens of distinct low-baseline verified identities carrying value,
    which only happens when an attacker has seized a crowd of them.
  * **fragmented** — the same flow split across many disconnected components.

A legitimate operation is never all three: it is one component, or has a hub, or involves few
accounts. The mesh is all three; the scorer raises such an operation to a conduit floor. This
is wired at `oracle.detect()` (operation level), leaving the per-component path untouched.

**Verified — coordination catches the mesh the per-component stack could not.**

```
mechanism (household pool):  conduit_split mesh, every archetype → coordination_verdict FRAUD, evaded=False
                             account_takeover via CORPORATE accounts → coordination risk 0.00 (hub anchors)
benign FP (operation level, segment-consistent corpus):  0 / 80

GA, full mesh arsenal, household seized pool (`coordination_detector.py` conditions):
   [A] provenance + behavioural                  ASR = 1.00   (§18 residual — mesh wins)
   [B] provenance + behavioural + coordination    ASR = 0.22–0.56  (mesh largely closed; 0% FP)
   [C] + coordination, takeover via CORPORATE     ASR = 1.00   (hub-anchored — honestly spared)
```

Coordination drops the mesh from **ASR 1.00 to a 0.22–0.56 residual at 0% benign false
positives** — the magnitude depends on *which* accounts the attacker seizes (a fixed pool
gives 0.22, a shuffled draw 0.56), because the residual is small low-value operations whose
mesh stays under the "crowd" size and `profile_mimicry`-hybrids that avoid the mesh shape. A
threshold sweep (min-consumers 15→8, min-fragments 4→2) does **not** lower it — those survivors
are not under-tuned meshes but a genuinely different evasion route (the hub-anchored §17-C path,
condition C, ASR 1.00, which coordination is honestly not the signal for), so the conservative
default thresholds are kept. Coordination is the **decisive** layer that breaks the otherwise
unstoppable mesh; it is not, and does not claim to be, a total close.

`behavioral`/`coordination_detector.py` condition C confirms the honest boundary: an
account-takeover routed through **corporate** accounts (§17-C) has a real high-baseline hub,
so coordination spares it (risk 0) — it is not the signal for that path. Coordination closes
the *consumer-mesh* residual; the corporate-seizure residual stays open and costlier.

**Full-stack arms race, now with the B1 layer** (`self_play/full_stack.py`,
native → provenance → behavioural → **coordination** → calibration):

```
 round 0: faced[native V2]                          ASR 0.89→0.33  FP 0%  → +provenance
 round 1: faced[+provenance]                        ASR 1.00→1.00  FP 0%  → +behavioural
 round 2: faced[+behavioural]                       ASR 1.00→0.11  FP 0%  → +coordination   ← decisive
 round 3: faced[+coordination]                      ASR 0.33→0.33  FP 0%  → +calibration
 round 4: faced[+coordination+calibration]          ASR 0.22→0.22  FP 0%
 start: ASR 0.89 vs native V2   end: ASR 0.22 vs the full stack   benign FP 0% throughout
```

The per-component layers (rounds 0–1) cannot touch the mesh — ASR holds at 1.00. The moment the
OPERATION-level coordination signal is deployed (round 2) it collapses the standing mesh evasions
to **0.11**; Red re-evolves against it and the loop settles at **~0.22 at 0% benign FP** — the
hub-anchored corporate residual coordination is honestly not meant to catch. Coordination, the
B1 capability, is the single decisive layer in the entire stack.

**The arc closes where it opened.** Every per-account signal the engagement had built by this
point — provenance (identity), behavioural (per-account behaviour) — raised the attacker's cost
but was bypassed by fragmenting the ring. The signal that catches the mesh here is an
**operation-level** one that LINKs the components into an operation: exactly the cross-session
correlation the deployed per-component V2 lacks — **B1**, the first finding of the white-box
report. (§20 then shows this was not the *only* way: a per-component counterparty-history signal
also catches the mesh, and more — see that section; the common thread is that every fix injects
context V2's isolated snapshot lacks.) The engagement is one closed loop: it began by naming V2's
dominant blind spot (component isolation) and ends by proving, adversarially, that closing it is
among the highest-value architectural investments — every orthogonal signal only raises the price
of an evasion that the snapshot-only view still ultimately permits.

**Honest caveats.** (1) Coordination's power is entirely conditional on the linkage capability;
this harness hands it the linked component set, a real deployment must earn it from device /
timing / funding-source evidence, and that linkage will itself have error. (2) The 0% benign FP
holds because legitimate operations here are single components with hubs; a real benign stream
with linked multi-session legitimate activity must be re-measured (the §13 discipline).
(3) Coordination is bypassable by keeping each linked operation under the crowd threshold —
which caps the attacker's per-operation throughput, a cost, not a free pass.

**Backward-compatibility checked.** The `coordination=` param and `coordination_verdict` default
off/`CLEAN`; the per-component path and every prior result are unchanged (main GA 0.667, §15
arms race ASR→0 @ 0% FP, §16 probe 0→0.89→1.00).

---

## 20. Counterparty-relationship detector — IMPLEMENTED (corporate-seizure counter + synthesis)

Status: **done & verified.** §19 left the corporate-account seizure (§17-C) as the last open
residual and named the consumer mesh as needing cross-component correlation. This builds the
counterparty-history signal that closes the corporate residual — and, in doing so, reveals that
the same signal closes the mesh too, refining §19's conclusion into the engagement's synthesis.

**Design.** `common/relationships.py`. The bank knows not only who its customers are (provenance),
how they behave (behavioural) and which transactions co-occur (coordination), but **who they
normally transact with**. Modelled as relationship *circles* — business ecosystems (a corporate
anchor, SME suppliers, a merchant, salaried employees, household/retail customers) that genuinely
transact with each other, held in the bank's records and unforgeable by the attacker. A new
`relationship=` oracle param (per-component, after behavioural). `RelationshipScorer` floors the
risk of value moving between two VERIFIED accounts in *different* circles — verified counterparties
with no shared history — leaving unverified value to provenance and within-circle value trusted.
The existing benign generators draw a circle-coherent operation via a `CircleView`, so every legit
counterparty pair is an established relationship (novel-value ratio 0 by construction).

**Verified — relationship closes the last residual, and the mesh, at 0% FP.**

```
benign FP (circle-coherent corpus, operation level):
   prov + behav + coordination                 FP = 0%
   prov + behav + coordination + relationship   FP = 0%

GA, seized pool 200:
   [A] +coordination, seize CORPORATE, takeover   ASR = 1.00   (§17-C — coordination misses the hub-anchored seizure)
   [B] +relationship, seize CORPORATE, takeover   ASR = 0.00   (§17-C CLOSED)
   [C] +relationship, seize HOUSEHOLD, mesh        ASR = 0.00   (the §18 mesh, caught per-component too)
```

A seized account betrays itself by paying verified **strangers**. Counterparty history catches the
corporate seizure coordination could not (B: 1.00→0.00) **and** the consumer mesh (C: 0.00), all
**per-component** — at the cost of the strongest data assumption (a complete relationship graph)
and, in production, real false positives from legitimate first-time business payments.

**Synthesis — what §16–§20 actually proved.** Five orthogonal capabilities were each driven into
existence by a Red probe that defeated everything before it:

| signal | question it asks | the probe that demanded it |
|---|---|---|
| provenance (§14) | *is the account KYC-established?* | partition / fresh-mule laundering |
| behavioural (§17) | *is it acting within its own baseline?* | account-takeover (§16) |
| coordination (§19) | *is this a linked crowd with no hub?* | the conduit_split mule mesh (§18) |
| relationship (§20) | *do these verified parties have shared history?* | corporate-account seizure (§17-C) |

The §19 framing — "the mesh needs cross-component correlation" — was true for the signals built by
then, but §20 shows it was not the *only* route: a per-component counterparty-history signal closes
the mesh as well, and more. The common thread, and the engagement's real conclusion, is sharper
than any single blind spot: **every effective defence injects CONTEXT that V2's isolated
transaction-graph snapshot does not contain** — KYC identity, account baseline, operation linkage,
counterparty history. B1 (component isolation) is the most visible instance, but the root is that
V2 scores a context-free snapshot. The highest-value Blue investment is not a better structural
detector; it is *memory* — the external context each of these signals supplies. Every probe in this
engagement ultimately won by exploiting the absence of one such context, and was closed by
supplying it.

**The standing residual.** Relationship is eroded by an attacker patient enough to **season**
genuine history between the accounts it controls — months of small legit-looking traffic before the
laundering run — which manufactures the shared history the signal trusts, at a large time cost.
That is the honest next Red probe, and it points at the temporal/history dimension the current
snapshot-plus-context model still under-weights.

**Backward-compatibility checked.** `relationship=` defaults off; the per-component path is
unchanged with it absent. Main GA still 0.667, §15 arms race ASR→0 @ 0% FP, §16 probe 0→0.89→1.00,
§19 coordination unchanged.

---

## 21. Relationship seasoning + maturity counter — IMPLEMENTED (where the arms race ends)

Status: **done & verified.** §20's named residual was *seasoning*: an attacker patient enough to
build genuine-looking history between its mules before the run manufactures the shared history the
counterparty signal trusts. This realises the probe and its counter and shows the engagement
terminates not in a perfect detector but in the attacker's **economics**.

**Model.** Relationships are no longer only god-given circles; the bank also *learns* them from
observed traffic (`RelationshipRegistry.learned`, a `LearnedRelationship` with count / cumulative
value / age). `season()` injects such learned relationships across the seized cohort — the attacker
running prior small transfers among its mules. Two detector modes: the §20 **binary** check (any
shared history ⇒ related) and a §21 **maturity** check (`RelationshipScorer(maturity=True)`) that
trusts a relationship only up to `matured_capacity = total_value · min(1, age/1yr) · min(1, count/10)`
— flow beyond that counts as novel. Genuine circle relationships are aged/deep ⇒ effectively
unlimited; seasoned ones are bounded by the history actually purchased.

**Verified — the probe defeats §20, the counter defeats the probe, and the residual is priced out.**

```
benign FP (circle-coherent corpus): binary 0%   maturity 0%

GA, seize a 40-account corporate cohort, takeover arsenal (avg laundering ≈ ₹607,519):
   [A] BINARY detector,   no seasoning      ASR = 0.00   (§20 result — closed)
   [B] BINARY detector,   cheap seasoning   ASR = 1.00   (probe defeats §20)
   [C] MATURITY detector, cheap seasoning   ASR = 0.00   (counter closes it again)
   [D] MATURITY detector, deep  seasoning   ASR = 0.89   (defeats maturity — at what cost?)

seasoning footprint (value pre-moved as legit traffic to launder ₹607,519):
   cheap (5 txns, ₹10k, 14 days/pair)  ≈ ₹39,000,000     64× the laundered amount — and STILL caught by maturity
   deep  (50 txns, ₹2L, 400 days/pair) ≈ ₹7,800,000,000  ~12,800× the laundered amount, over a year
```

A **binary** "do they have any history?" check is defeated by trivial seasoning (B: ASR→1.00). The
**maturity** check forces the seasoned history to be deep, aged, and value-proportionate to the
flow (C: cheap seasoning → ASR 0.00). Defeating maturity (D) requires deep seasoning — and the
arithmetic is the point: because maturity charges each counterparty pair's flow against *that
pair's* purchased history, the attacker must legitimately pre-move value comparable to what it
intends to launder, a year in advance. Here that is **₹7.8 billion of seasoning to launder
₹0.6 million** — the cure costs ~12,800× the disease. Even the cheap seasoning that beats the
binary check already costs 64× the laundered sum and still fails maturity.

**Where the engagement ends.** The arms race does not terminate in a perfect classifier — none
exists. It terminates in **economics**: a maturity-weighted history signal makes the only remaining
evasion (manufacture deep aged relationships) cost far more than the laundering yields. That is the
realistic win condition for a fraud defender, and reaching it required the one dimension V2's
context-free snapshot never had — **time / history**. The §16–§21 ladder, end to end: identity
(provenance) → behaviour (behavioural) → linkage (coordination) → relationship (relationship) →
**relationship maturity over time** (seasoning/maturity). Each rung is a different slice of the same
missing thing — *memory* — and the last rung is the temporal depth of that memory. The attacker's
final move exists but is self-defeating; the defender wins not by seeing every trick but by pricing
the last one out of viability.

**Honest caveats.** (1) The ₹39M/₹7.8B figures season the *complete* cohort graph (780 pairs); a
surgical attacker seasons only the pairs it will use, lowering the absolute total — but maturity's
per-pair value-proportionality is the binding constraint regardless: each laundering path needs
aged history of comparable value, so the cost scales with what is laundered however few pairs are
touched. (2) `matured_capacity`'s weights (1-year age, depth/10) are illustrative; real values must
be calibrated to genuine relationship-age and throughput distributions, and legitimate
relationship-formation bursts (a new supplier, a house purchase) will create real FP that this
construction-clean corpus does not show (the §13 discipline, one last time).

**Backward-compatibility checked.** `RelationshipScorer` defaults to `maturity=False` (the §20
binary view) and `learned` defaults empty, so §20 and every prior result are unchanged; the new
behaviour is opt-in. Main GA 0.667, §15 arms race ASR→0 @ 0% FP, §16 probe 0→0.89→1.00 all hold.

---

## 22. Final defended system — the capstone (whole stack vs whole adversary)

Status: **done & verified.** Every section above isolated one signal against one probe. This is the
only measurement a deployment actually needs: the **entire** Blue stack armed at once against the
**entire** adversary, on the honest benign corpus — the engagement's bottom line.

**Configuration.** Blue = native V2 + provenance + behavioural + coordination + relationship
(**maturity** mode). Red = the full agent arsenal including `account_takeover` and the
`conduit_split` mule mesh, a **mixed seized pool** (200 phished consumers for the mesh + 50 seized
corporate accounts for the hub-anchored path), and **cheap relationship seasoning** applied across
the whole cohort (the attacker's best low-cost move). Benign = 120 circle-coherent operations,
scored at the operation level.

**Result.**

```
 Red ASR vs the full stack = 0.00     benign false positives = 0%
 surviving evasions: none found

 §16–§21 ladder (each rung forced by the probe below it):
   native V2       structural snapshot            ← partition / fresh-mule laundering
   + provenance    KYC identity                   ← account-takeover via verified accounts
   + behavioural   each account vs own baseline   ← the conduit_split mule mesh
   + coordination  operation-level linked crowd   ← corporate-account seizure (a real hub)
   + relationship  shared counterparty history    ← seasoning fake history between mules
   + maturity      history depth × age over time  ← (priced out: cost ≫ laundered value)
```

The fully-armed defender drives the complete adversary's ASR to **0.00 at 0% benign false
positives**. The full arsenal — partition, feature/amount/temporal mimicry, relay throttling,
volume dilution, account-takeover, the mule mesh — plus a mixed corporate+consumer seized pool plus
cheap seasoning produces **no evasion**. The single evasion that remains *possible*, deep seasoning,
the maturity signal has already priced out of economic viability (§21).

**What this does and does not claim.** It claims that the five context signals built here, composed,
close every attack this Red Team can produce at zero false positives *on construction-honest
corpora*. It does **not** claim production-readiness: every layer's 0% FP rests on a corpus built to
respect that layer (KYC pool, baseline-sized amounts, single-component or circle-coherent legitimate
ops), and §13–§21 log that each FP rate and threshold must be re-measured on real data with real
linkage error before deployment. The transferable result is **structural, not numerical**: a
context-free, component-isolated snapshot detector (V2) is evadable along every axis, and each axis
is closed by injecting a specific kind of *memory* — identity, behaviour, linkage, relationship, and
the temporal depth of relationship. The fully-armed system is the existence proof that those five
contexts, together, are sufficient against this adversary; the engineering work remaining is to earn
each context from real data at an acceptable false-positive cost.

**The engagement, in one line.** It began (white-box report, B1) by naming the cost of V2 seeing each
component in isolation, and ends by proving — adversarially, probe by probe, counter by counter —
that the cure for an isolated snapshot is *memory*, and that with enough of it the defender wins not
by perfect detection but by making the last evasion cost more than it yields.


## 23. Learning attackers — PPO Red Team + GraphGAN surrogate (IMPLEMENTED)

Status: **done & verified (2026-06-24).** The remaining "F"-tier directive capabilities — a
reinforcement-learning attacker and the GAN generator-vs-discriminator dynamic — were the two
scaffolds left as `NotImplementedError` (`rl_agent/spec.py`, `graph_gan/spec.py`). Both are now built.
The engine is deliberately torch-free (deployment removed PyTorch), so both are **pure NumPy** with
hand-derived backprop — faithful to the algorithms and to the codebase's discipline.

### 23.1 PPO Red Team (sequential-edit evasion)

Where the GA searches a whole genome at once, the PPO agent makes **one edit at a time** conditioned
on the Blue Team's current reaction — the MDP fixed in `rl_agent/spec.py`. New `rl_agent/env.py`
(`AttackEnv`) wraps the real `BlueTeamOracle` + the registered agents as a sequential environment:
a 32-d fixed-length state (graph aggregates · Blue feedback verdict/risk/evidence · per-node risk
distribution · budget), a discrete `(agent × intensity)` action, and a shaped reward (per-step
detection drop + stealth gain − distortion − step cost, terminal bonus on a feasible evasion, hard
penalty if the laundering objective breaks). New `rl_agent/ppo.py` is a two-layer-tanh MLP
actor-critic with clipped surrogate, GAE(λ=0.95), entropy bonus and Adam — one env per archetype,
one shared policy. Evidence is bucketed with a **stable** hash (crc32, not the salted builtin) so the
state is reproducible.

**Result (real V2, 7 cheap structural agents, 40 updates, 53 s):**

```
 greedy ASR vs the REAL engine:  0.00 (untrained) → 0.56 (trained)   [5/9 archetypes]
   EVADE → LOGGED:  layering · smurfing · fan_out · hybrid · large_org
   held SUSPICIOUS: fan_in · mule_network · cashout_network · bridge_network
 learning curve:  train_asr 0.14→0.85   entropy 3.32→1.78 (annealing)   return +0.03→+1.15
 reproducible:    two identically-seeded runs → identical ASR (0.2222), bit-for-bit
```

The PPO agent independently reaches the **same ASR band as the GA (0.44–0.67)** by a different
search — sequential credit assignment rather than population search — and converges on the same
B1 lever (every evasion fragments via `cross_component_split`). The four holdouts are exactly the
fan-in / consolidation-gated archetypes prior sections flagged as the robust gate. *Caveats:* ASR is
on the **permissive** objective (the §A strict on-graph ASR remains 0 — every win is
partition-dependent); verification used the cheap structural arsenal because `volume_dilution` /
`profile_mimicry` build very large fragmented graphs that make per-step scoring slow (the §13 ENG
note — the surrogate world-model below is the intended fix at scale); V2 only (V1 still secondary).

### 23.2 GraphGAN — distilled differentiable discriminator + the re-distillation loop

V2 is non-differentiable, so the recommended formulation (spec) is **surrogate-distillation**: train a
differentiable proxy of V2's verdict, then use it where speed or gradients are needed. New
`graph_gan/surrogate.py` (`VerdictSurrogate`) is that proxy — a NumPy MLP regressor over pure
structural + attribute features (including the node attrs V2 trusts, B8, and the amount bands its
gates key on), distilled from the real engine's detection scores.

```
 surrogate fidelity on the distillation distribution:  MAE 0.033   flag-agreement 0.997
```

Wired as an **optional fast reward model** for PPO (`AttackEnv(surrogate=…)`), rollouts skip the real
engine (~10× faster: 5 s vs 53 s) while true evasion is always re-checked on the real V2 at greedy
eval. This immediately exposed the honest failure mode of a *static* surrogate:

```
 static surrogate-accelerated PPO:  ~10× faster, but greedy true-ASR = 0.00
   on-policy fidelity collapses:  MAE 0.033 → 0.233,  flag-agreement 0.997 → 0.56
```

i.e. the policy is an adversary that **Goodharts the proxy** — it learns the region where surrogate
and real engine disagree, not real evasions. The cure (spec: "periodically re-distil against the real
V2") is the actual GAN loop, now implemented in `GraphGAN.train`: alternate (a) PPO updates against
the surrogate with (b) re-distilling the surrogate on the generator's **on-policy** attacks, labelled
by the real V2.

```
 GraphGAN re-distillation loop (generator PPO ⇄ discriminator surrogate):
   round   true ASR (real V2)   on-policy MAE   flag-agreement
     0          0.11               0.233            0.56
     1          0.11               0.117            0.71
     2          0.11               0.073            0.82
     3          0.11               0.080            0.87
     4          0.22               0.089            0.91
```

Each re-distillation shrinks the adversarial gap — on-policy flag-agreement climbs **0.56 → 0.91**,
MAE collapses ~3× — and as the proxy becomes faithful the generator's proxy-wins convert into real
evasions (true ASR begins to rise). That is the GAN equilibrium the spec named: the discriminator
chases the generator's current distribution, the generator is forced off proxy-exploits toward
fooling the real engine. *Caveat:* the loop is a demonstration on a short budget — the trend (gap
closing monotonically) is the result, not the absolute ASR.

### 23.3 What this adds and what it does not

Adds the two learning attackers the directive's SOTA tier asked for, both reproducible and both wired
to the **real** engine (`python -m adversarial.rl [--surrogate] [--compare]`). The PPO agent is a
genuinely different search that corroborates the GA's findings (same ASR band, same B1 lever) rather
than a re-skin. The surrogate is the reusable accelerator the §13 ENG note called for, and the
re-distillation loop turns it from a Goodhart liability into a faithful fast proxy. Does **not** change
any prior result: `rl_agent/` and `graph_gan/` are additive, the GA/QD/self-play/integration core is
byte-unchanged, and `blue_team_v2/` is untouched. Open threads unchanged (PPO at scale needs the
surrogate world-model to afford the heavy agents; strict on-graph objective; V1 secondary target).
