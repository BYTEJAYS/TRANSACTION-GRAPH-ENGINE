# TGIE — Canonical Project Knowledge (UB ground truth)

> This document is the single authoritative reference UB retrieves from when answering
> questions about TGIE. It is deliberately precise and **honest about limitations** so UB
> never overclaims under cross-questioning. When code and this doc disagree, the code wins —
> but this doc is kept in sync with the canonical tree at `~/Desktop/TGIE`.

## 1. What TGIE is
**Transaction Graph Intelligence Engine (TGIE)** is a fraud-investigation platform. Financial
crime — especially money laundering — hides in the **relationships between accounts**, not in
single transactions. TGIE ingests transactions, builds them into a **live directed graph**
(accounts = nodes, transactions = edges), detects laundering patterns (layering, mule networks,
structuring, fan-out/fan-in, circular flow, cash-out), explains them, and supports an
investigator workflow (cases, recovery, evidence). It runs fully locally; the AI layer (UB) uses
a local Ollama model with **no cloud and no data egress**.

## 2. High-level architecture
- **Backend** (`backend/`, FastAPI, Python): transaction ingestion, the NetworkX graph engine,
  Blue Team fraud detection (V1 + V2), recovery engine, case management, auth, and the UB and
  Red Team API surfaces. Runs on **:8000**.
- **Frontend** (`frontend/`, React + Vite + TypeScript, react-force-graph-3d / Three.js): the
  3D investigation graph, panels, dashboards, and the in-app UB voice orb. Runs on **:3000**
  (Vite proxies `/api` → :8000).
- **UB — Universal Brain** (`ub/` + `backend/ub_service/`): local Ollama RAG cognitive layer.
  Runs on **:8001**, backed by Ollama on **:11434** (`llama3.1:8b`, `nomic-embed-text`).
- **BELS** (`bels/`): blockchain evidence ledger (internal PoW hash-chain anchoring evidence
  SHA-256 hashes; files stay off-chain).
- **Adversarial program** (`red_team/adversarial/`): research-grade Red Team that hardens the
  Blue Team via self-play (GA, MAP-Elites, PPO, GraphGAN surrogate).
- **Control suite** (`control/`): `start_tgie.command` / `stop_tgie.command` / `status` /
  `restart` launch Ollama, UB, backend, frontend in order. Nothing auto-starts.

## 3. Transaction ingestion & payment rails
- Transactions are submitted to `POST /transaction/manual` (a list); the backend processes them
  sequentially and streams graph updates over WebSocket to the originating session.
- `PaymentRail` (`backend/models/transaction.py`) values: **UPI, IMPS, RTGS, NEFT, CASH,
  CASH_IN, CASH_OUT**.

## 4. Cash In / Cash Out — FIRST-CLASS nodes (recent work)
This is important and frequently cross-questioned.
- **Problem that was fixed:** datasets using `payment_rail: "CASH_IN"` / `"CASH_OUT"` (with
  endpoints `CASH_SOURCE` / `CASH_EXIT`) used to fail. `CASH_IN`/`CASH_OUT` were not valid
  `PaymentRail` values, so ingestion silently coerced them to **UPI** (lenient path) or rejected
  them (strict path). Cash never reached the dedicated cash pipeline. The system originally only
  understood `payment_rail="CASH"` with direction inferred from the account name.
- **Fix (first-class graph nodes):** `CASH_IN` and `CASH_OUT` are now valid rails. `CASH_SOURCE`
  and `CASH_EXIT` become **real, connected graph nodes** classified as `account_type = "cash"`
  (`graph_engine/graph_manager.py`). A chain `CASH_SOURCE → ACC_1 → … → ACC_n → CASH_EXIT` is one
  connected component, so cash endpoints participate fully in BFS/DFS, connected components,
  cycle detection, community detection, recovery, and analytics. Cash analytics
  (`cash_inflows`/`cash_outflows`) are computed from the first-class cash edges.
- **Legacy path coexists:** `payment_rail="CASH"` still routes to the older off-graph
  satellite-cash handling (`add_cash_event`) for backward compatibility. So two cash conventions
  exist: first-class (`CASH_IN`/`CASH_OUT`) and legacy satellite (`CASH`).
- **Tests:** `backend/tests/test_cash_transactions.py` (deposit, withdrawal, deposit→transfer→
  withdrawal connectivity, multiple deposits, layered laundering, cash→ring→cash); regression
  confirms UPI/IMPS/NEFT/RTGS and legacy CASH are unaffected.

## 5. Graph layout engine — topology-aware (recent work)
- **Problem:** the 3D graph used a generic force simulation with random initial seeding, which
  produced twisted / diamond / zig-zag shapes that hid the fraud structure.
- **Fix:** `frontend/src/components/graphLayout.ts` analyses each connected component's directed
  topology and computes an **intelligent initial 3D placement**; the force engine then only
  **refines** (relaxes) it instead of defining it. A structural-anchor spring holds each node
  near its computed slot.
- **Adaptive layouts:** ring/cycle → circular; everything else → layered DAG (longest-path depth
  layering with barycenter sweeps to reduce edge crossings). This makes chains render as straight
  vertical lines, fan-outs as cones, fan-ins as convergence, layered fraud as stacked layers.
  Money flows **downward** consistently (depth → Y axis), so direction is obvious. The graph
  stays fully 3D, rotatable, zoomable, draggable. Rendering/interaction/glow were NOT changed —
  only the layout algorithm.

## 6. Cash-node rendering priority (recent work)
- **Rule:** node **type** owns the fill color; fraud is a non-destructive **overlay**. Priority:
  node type → fraud overlay → selection → hover.
- **Colors:** `CASH_SOURCE` (cash entered the network) = **emerald `#00E676`**; `CASH_EXIT`
  (cash left the network) = **gold `#FFC400`**. These identity colors are PERMANENT — even when
  the node is part of a fraud path, it never turns solid red. Fraud involvement is shown by a
  pulsing **red halo ring** around the cash node. Ordinary fraud accounts still fill red.
- Implemented in `frontend/src/store/graphStore.ts` (color) and `GraphScene.tsx` (the animation
  loop restores the identity fill every frame and drives the red halo). The legend
  (`LeftPanel.tsx`) shows: 🟢 Cash In, 🟡 Cash Out, 🔴 Fraud Account, 🔵 Normal Account,
  🟣 Selected, ⚪ Investigating. Hovering a cash node shows "Cash Deposit/Withdrawal — cash
  entered/exited banking network", never just "Account".

## 7. Blue Team (the defender / detector)
- Two engines behind `blue_team_v2/router.py` (env `ACTIVE_BLUE_TEAM`).
  - **V1**: ML/statistical — IsolationForest + XGBoost + GraphSAGE/GAE + a rule classifier,
    streaming-oriented.
  - **V2**: deterministic graph engine — per-node metrics → detectors → evidence → scoring →
    cluster verdict. Thresholds: LOG 0.38 / REVIEW 0.62 / HIGH_RISK 0.83.
- **Known V2 weaknesses (be honest):** V2 analyses each connected component **in isolation**
  (blind spot "B1") — no cross-component / cross-session / temporal correlation; it is stateless
  per call (slow time-distributed attacks unseen); the GraphSAGE/GAE GNN in V1 is effectively
  **untrained** (random weights); the IsolationForest has a label-leak issue ("B5").

## 8. Red Team (the attacker / hardener) and the adversarial program
- The Red Team is a **research-grade adversarial engine** (`red_team/adversarial/`) that evolves
  attacks to evade the Blue Team — GA (evolutionary engine), MAP-Elites quality-diversity (kills
  mode collapse), and PPO + a GraphGAN surrogate (pure NumPy, torch-free). Its purpose is to find
  the defender's missing capabilities, then supply them.
- **Engagement result:** the arc proved that a context-free, component-isolated detector is
  evadable on every axis, and that each axis is closed by injecting **context (memory)**. Six
  composed signals — V2 base + **provenance** (KYC identity) + **behavioural** (each account vs
  its own baseline) + **coordination** (linked hub-less crowd) + **relationship** (shared
  counterparty history) + **relationship-maturity** (history depth × age, ending the arms race in
  economics) — drive the full adversary to **0% attack success at 0% false positives** on
  construction-honest corpora.
- **Honest caveats:** the headline native-V2 false-positive rate on a **realistic** benign corpus
  is **56.7%** (it over-flags legit payroll/corporate payments) — the context signals fix this,
  but the context registries are currently **synthetic**, so the 0% FP rests on layer-respecting
  corpora and is **not production-validated**. "Strict" (on-graph) attack success is 0% — most GA
  wins are partition-dependent (the B1 blind spot). This is a research demonstration, not a
  shipped detector.
- **Red Team panel** (localhost only, `backend/api/redteam.py` + `RedTeamPanel.tsx`): generates
  attack candidates, shows the attack graph + per-generation evolution + deployed-vs-hardened
  verdicts, and lets a human review them. It is opt-in via `ENABLE_REDTEAM_PANEL` and never
  shipped to the deployed build.

## 9. Adversarial governance — human-in-the-loop learning (recent work)
This is the correct training philosophy and is frequently cross-questioned.
- **Principle:** the Red Team is the attacker and **never directly trains** the Blue Team. The
  Blue Team learns **only from investigator-approved cases**. Nothing enters the Blue Knowledge
  Base automatically.
- **Important truth:** the live interactive platform was **already human-gated** — there was no
  auto-poisoning bug in production. `blue_team_v2` is stateless and never mutated at runtime; the
  only auto-hardening is an **offline CLI research loop**, not wired into the running app.
- **Workflow:** Red generates an attack → Blue investigates → **Detected** ⇒ the Red Team must
  evolve a harder variant (the case is NOT used to train Blue); **Missed** (a real on-graph
  evasion) ⇒ the case enters a **Training Queue** for investigator review.
- **Governance layer** (`backend/adversarial_governance/store.py`, JSON-persisted): the Training
  Queue, an immutable **audit trail** (every enqueue/decision with who/when/outcome), **dedup**
  (a new pattern with an already-known signature MERGES instead of duplicating), and the Blue
  Knowledge Base. Endpoints: `/api/redteam/training/{queue,decide,audit,similar,reset}`. The only
  decision that adds to the knowledge base is **"Learn from this Case"**; reject/ignore/archive
  discard.
- **UI:** `frontend/src/components/panels/TrainingReviewPanel.tsx` (localhost "TRAINING" toggle) —
  per-case fields (Pattern ID, timestamp, detection status, Red/Blue confidence, fraud type, risk,
  why-Blue-missed explanation), the miss-dialog (Learn / Ignore / Review First) plus Reject /
  Archive / Review Graph / Compare Similar, and an Audit Trail tab.
- **Tests:** `backend/tests/test_training_governance.py` (only misses enqueue; nothing learns
  without a decision; learn adds + audits; duplicates merge; reject discards; similar detection).

## 10. Other components
- **Recovery engine** (`backend/recovery`, `/api/recovery/*`): a 10-factor "can we still recover
  the money?" scorer with age-decay, a funnel, ranked actions, and a simulator. First-class cash
  endpoints are visible to it.
- **Case management** (`backend/case_management`): investigator cases with timeline, evidence,
  notes, assignment, and JSON persistence.
- **Auth & navigation**: banking-grade investigator login (JWT/RBAC), global account search,
  account dossiers.
- **BELS**: PoW hash-chain evidence ledger; provider-abstracted for a future bank/RBI chain.

## 11. UB — the Universal Brain (this system)
- Local Ollama RAG over the actual codebase + these docs. **No fine-tuning** — UB "learns" by
  re-indexing (`python -m ub index`), which regenerates the summary JSONs and re-embeds every
  chunk with `nomic-embed-text`, then answers with `llama3.1:8b`.
- Six modes: `chat`, `founder`, `developer`, `presentation`, `demo`, `judge`. Judge mode answers
  hard questions directly and is **honest about limitations**.
- Every answer is grounded in: the auto-generated project/architecture summaries + top-k
  retrieved chunks + recent conversation history.

## 12. Honest limitations (UB must never hide these)
- **Production readiness ≈ 55/100.** TGIE is an advanced prototype / research platform, not a
  deployed bank system.
- Native V2 false-positive rate on realistic benign traffic is **~56.7%**; the 0% FP / 0% ASR
  hardened results depend on **synthetic** context registries and are **not** production-validated.
- "Strict" on-graph attack success is **0%** — most adversarial wins are partition-dependent
  (the B1 component-isolation blind spot).
- The V1 GNN is effectively untrained; IsolationForest has a label-leak ("B5"); XGBoost is
  overfit to its own synthetic generator.
- The adversarial work (`red_team/adversarial/`) and the recent cash / layout / governance work
  are not necessarily committed to git.
- Two cash conventions coexist (`CASH_IN`/`CASH_OUT` first-class vs legacy `CASH` satellite),
  which is intentional for backward compatibility but is a known design seam.
