# TGIE — Detection & Adversarial Deep-Dive (UB ground truth)

> Companion to TGIE_PROJECT_KNOWLEDGE.md. Technical depth on how detection scores,
> how the Red Team attacks, and the context signals that harden the Blue Team.
> Honest about what is real vs synthetic. Code is the final authority.

## Blue Team V2 — how a verdict is produced
1. **Graph build:** transactions → directed graph; connected components are the unit of analysis.
2. **Per-node metrics:** degree, fan-in/out, velocity, value flow, betweenness/closeness
   (sampled at scale), dormancy, role (origin/hub/mule/relay/sink), etc.
3. **11 detectors** run over each component, each emitting explainable evidence:
   `layering`, `smurfing`, `mule_accounts`, `fan_in`, `fan_out`, `velocity`, `cashout`,
   `circular_flow`, `bridge_accounts`, `dormant_accounts`, `synthetic_networks`.
4. **Scoring:** an 18-factor per-node score; detector evidence dominates, role base risk caps
   ~0.34, topology is a tie-breaker. So a node with no detector firing tops out ~0.42 (LOG) —
   the verdict is effectively **detector-gated**.
5. **Cluster verdict:** aggregate component risk vs thresholds — **LOG 0.38 / REVIEW 0.62 /
   HIGH_RISK 0.83**. Verdicts are deterministic and reproducible; every flag has evidence + a path.

**Gate constants are absolute** (e.g. ~₹25k hop layering, mule/structuring band ~[46k,50k),
~₹150k/200k fan/velocity, 4-hop chain, 4-degree fan, 6h dormancy, 600s burst). That makes V2
auditable — and makes evasion margins computable in closed form, which the Red Team exploits.

**Documented weaknesses (B-series):**
- **B1 (dominant):** each connected component is scored in ISOLATION — no cross-component,
  cross-session, or temporal correlation. Partitioned operations are invisible.
- **B2:** stateless per call → slow, time-distributed attacks unseen.
- **B4:** the V1 GraphSAGE/GAE GNN is effectively **untrained** (random weights) — its
  embeddings are noise; embedding attacks on it are pointless.
- **B5:** the V1 IsolationForest reads ground-truth `fraud_pattern` (a **label leak**) — inflates
  V1; must be stripped from any honest eval.
- **B6/B8:** XGBoost overfits its own synthetic generator; V2 trusts attacker-set node attributes.

## Red Team — methods (all pure NumPy; deployment is torch-free)
- **Genetic algorithm** (`red_team/adversarial/red_team/evolutionary_engine`): warm-started GA;
  genome = ordered list of attack "moves"; deterministic per-genome via blake2b seeding (so runs
  reproduce); fitness ≈ 0.55·evasion + 0.25·stealth − 0.15·distortion − 0.05·complexity.
- **Attack moves (agents):** feature_mimicry, amount_dither, temporal_spread, relay_insertion,
  decoy_edges, sink_funnel, cross_component_split (the dominant B1 lever), plus heavier agents
  volume_dilution, profile_mimicry, account_takeover, conduit_split (mule mesh).
- **MAP-Elites quality-diversity** (`quality_diversity/map_elites.py`): descriptors =
  fragmentation × distortion (30-cell grid); quality = evasion+stealth. Finds **12 distinct
  evading families vs the scalar GA's 5** — kills mode collapse and yields the diverse corpus a
  detector-level hardener needs.
- **PPO RL agent** (`rl_agent`): the attack as a sequential one-edit-at-a-time MDP; 2-layer MLP
  actor-critic, clipped surrogate + GAE; reached ASR 0→0.56 on the cheap arsenal, reproducible.
- **GraphGAN surrogate** (`graph_gan`): a NumPy MLP distilled from real V2 scores (fidelity MAE
  ~0.033) to give PPO a fast reward model. A **static** surrogate causes **Goodhart** (high proxy,
  0 true ASR); the real GAN loop re-distills on on-policy attacks labelled by V2 each round →
  agreement climbs .56→.91 and true ASR rises — the equilibrium that closes the gap.

**Permissive vs strict success:** permissive ASR ~0.44–0.67; **strict on-graph ASR = 0.0** —
every GA win is partition-dependent (B1). Reported separately on purpose.

## Context signals — the hardening ladder (§16–§22)
Each signal was forced by a specific probe; each injects context V2's snapshot lacks.
1. **Provenance** (KYC identity): value-weighted unverified ratio; established customers attenuate,
   fresh mules floor to FRAUD. Fixed both error rates — realistic benign FP 56.7%→~0%, fraud held;
   orthogonal to graph shape so B1 fragmentation doesn't help. Limit: proves identity, not behaviour.
2. **Behavioural** (own baseline): a verified account whose throughput exceeds ITS OWN segment
   baseline is a conduit. Catches phished consumer accounts used as mules (account-takeover).
3. **Coordination** (operation level): flags a flow that is hub-less AND consumer-heavy AND
   fragmented — the mule mesh that bypasses every per-component signal. This is the direct B1 counter.
4. **Relationship** (counterparty history): floors value on verified↔verified edges between
   accounts with no shared history (novel counterparties) — closes corporate-seizure and the mesh.
5. **Relationship-maturity** (history depth × age): trusts a pair's flow only up to the genuine
   history it has built → seasoning a fake history costs value proportional to laundering, a year
   ahead. **The arms race ends in economics.**

Composed (V2 + all five) the capstone run drives the FULL adversary (incl. conduit-split mesh +
seasoning) to **0% ASR at 0% benign FP** — but see "real vs synthetic" below.

## Real vs synthetic (do not overstate)
- **Real:** the deterministic V2 engine + evidence; graph build/traversal/analytics; the cash
  pipeline (first-class CASH_IN/CASH_OUT); the GA/QD/PPO/GraphGAN running against the actual
  engine; UB's local RAG over real source; the governance training queue.
- **Synthetic / illustrative:** the benign corpus and the KYC / behavioural / relationship
  registries — so every "0% FP" is **construction-honest**, not production-measured; the V1 GNN is
  untrained. Production readiness ≈ **55/100**. Numbers must be recalibrated on real account
  history before being quoted as deployable.

## How this maps to the investigator experience
- Cash entry/exit points are emerald/gold first-class nodes (identity preserved even under fraud).
- The topology-aware layout makes chains, fans, rings, and layered laundering readable at a glance.
- Missed evasions flow to the Training Queue; only investigator-approved cases enter the Blue
  Knowledge Base (deduped + audited). Detected attacks push the Red Team to evolve, not the Blue
  Team to retrain.
