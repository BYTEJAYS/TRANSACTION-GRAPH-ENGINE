<div align="center">

# TGIE — Transaction Graph Intelligence Engine
### Complete Project Dossier · Technology, Architecture & Differentiators

*Real-time, relationship-first financial-crime investigation platform — graph engine,
adversarial Blue/Red self-play, voice "Universal Brain", recovery engine, and a forensic
Union-Bank-grade case + evidence stack — assembled into one production-shaped workspace.*

</div>

---

## 0. One-paragraph pitch

Financial crime — especially money laundering — does not live inside any single transaction.
It lives in the **relationships between accounts**: the chains, fans, rings, mule meshes, and
cash entry/exit points that connect them. Most fraud systems score transactions one at a time.
**TGIE scores the graph.** It ingests transactions, builds a live directed graph (accounts =
nodes, transactions = edges), detects laundering *topologies* with fully explainable evidence,
renders them in an investigator-readable 3D scene, and continuously hardens its own detector
through an adversarial Red⇄Blue self-play loop that ends not in a model tweak but in
**economics**. A local voice "brain" narrates and answers cross-questions with no cloud and no
data egress.

---

## 1. What makes us different from other fraud systems

These are the points that distinguish TGIE from a conventional fraud/AML stack. Each is backed
by real code in this repo (honesty about what is real vs synthetic is kept in §9).

| # | Differentiator | Why it matters |
|---|---|---|
| **1** | **Graph-native, relationship-first detection.** The unit of analysis is the *connected component*, not a row. | Layering, smurfing, mule rings and structuring are invisible to row-level scoring; they are obvious as topology. |
| **2** | **Deterministic, fully explainable verdicts (Blue Team V2).** 11 detectors, 18-factor node scoring, absolute gate constants. Every flag carries evidence + a path. | Auditable for a bank/regulator. No "the model said so." Reproducible verdicts you can defend in a case file. |
| **3** | **Built-in adversarial immune system.** A research-grade Red Team (GA + MAP-Elites + PPO + GraphGAN) attacks the *real* detector and supplies the exact context the detector is missing. | The system finds its own blind spots and closes them, instead of waiting to be breached in production. |
| **4** | **The arms race terminates in economics, not in an endless model chase.** The *relationship-maturity* signal forces a launderer to pre-seed genuine value a year ahead, proportional to what they want to launder. | A principled stopping point: evasion becomes more expensive than the crime. |
| **5** | **Human-in-the-loop governance is the *only* learning path.** The Red Team **never** trains the Blue Team directly. Only investigator-approved, Blue-*missed* cases enter the Knowledge Base — deduped + fully audited. | No auto-poisoning, no silent drift. Every change to the detector's knowledge has a who/when/why audit trail. |
| **6** | **Cash is first-class.** `CASH_IN`/`CASH_OUT` create real connected graph nodes (`CASH_SOURCE` emerald / `CASH_EXIT` gold) that participate in every traversal, not off-graph satellites. | You can see and reason about where physical cash *enters and leaves* the banking network — the laundering endpoints. |
| **7** | **Topology-aware 3D layout.** The layout engine reads each component's directed structure and places nodes intelligently (chains = vertical lines, fans = cones, rings = circles, layering = stacked layers); the force engine only *refines*. Money always flows downward. | An investigator reads the fraud *shape* at a glance instead of fighting a vibrating hairball. |
| **8** | **"Can we still recover the money?" engine.** A 10-factor recovery scorer with age-decay, a funnel, ranked actions and a simulator. | Most systems stop at detection. TGIE optimizes the *outcome the bank actually cares about*: recovered funds. |
| **9** | **Tamper-evident evidence (BELS).** An internal Proof-of-Work hash-chain anchors evidence SHA-256 hashes (files off-chain), provider-abstracted for a future bank/RBI chain. | Court-/regulator-grade chain of custody for every piece of evidence. |
| **10** | **Fully local, zero data egress AI (UB).** The "Universal Brain" is a local Ollama RAG layer over the actual source + docs — no cloud, no fine-tuning, honest under cross-questioning. | A bank can run the intelligence layer on-prem; nothing leaves the building. |
| **11** | **Radical honesty as a design principle.** Strict on-graph ASR (0%) is reported *separately* from permissive ASR; benign false-positive rate (native ~56.7%) is published, not hidden; production readiness is scored ~55/100. | Trustworthy by construction — the system refuses to overstate its own numbers. |

---

## 2. System map

```
                         OBSERVER (analyst / browser)
                                    │ HTTPS / WSS
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ FRONTEND — Vite + React 18 + TypeScript + three.js  (:3000)               │
│   GraphScene (3D force graph) · Risk-Intel layer · panels/dashboards ·    │
│   UB voice orb (wake word + intents + narration)                          │
└──────────────┬───────────────────────────────────────────┬───────────────┘
   WS /ws/live │                        POST /transaction/manual            │
               ▼                                                            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ TGIE CORE BACKEND — FastAPI  (:8000)                                       │
│   simulator → graph_engine (NetworkX) → anomaly_detection (IsolationForest)│
│                         │                                                  │
│            Blue Team router  ──select(ACTIVE_BLUE_TEAM)──►                 │
│               ├── V1  ML: IsolationForest + XGBoost + GNN + rules          │
│               └── V2  deterministic: 18-factor metrics → 11 detectors      │
│                         │                                                  │
│   recovery · case_management · auth(JWT/RBAC) · evidence · streaming ·     │
│   ub_service · adversarial_governance · api(routes, ws, redteam[gated])    │
└───────┬───────────────────────────────────────────────┬───────────────┬──┘
        │ verdict schema                                 │               │
        ▼                                                ▼               ▼
┌──────────────────────┐        ┌─────────────────────────────┐  ┌──────────────┐
│ BELS evidence ledger │        │ ADVERSARIAL PLANE (offline) │  │ UB (Ollama)  │
│ PoW hash-chain :8200 │        │ GA · MAP-Elites · PPO ·     │  │ RAG :8001 /  │
│ SHA-256 anchors      │        │ GraphGAN · 6 context signals│  │ :11434       │
└──────────────────────┘        │ + CRUCIBLE genome engine    │  └──────────────┘
                                └─────────────────────────────┘
```

**Live path:** ingress → graph construction → Blue Team scoring → WS broadcast (~1s heartbeat)
→ 3D render → UB narration.

---

## 3. Complete technology stack & the role of each

### 3.1 Backend — core engine (`backend/`, Python 3.11, FastAPI, `:8000`)

| Technology | Version | Role in TGIE |
|---|---|---|
| **FastAPI** | 0.111.0 | The core API server — transaction ingress, verdict APIs, recovery/case/auth/evidence routes, WebSocket live stream. |
| **Uvicorn[standard]** | 0.29.0 | ASGI server that runs the FastAPI app (`uvicorn main:app … :8000`). |
| **websockets** | 12.0 | Pushes graph deltas + verdicts to the browser over `WS /ws/live` (~1s heartbeat). |
| **Pydantic / pydantic-settings** | 2.7.1 / 2.2.1 | Schema + validation for transactions, verdicts, config; the de-facto shared verdict contract. |
| **python-multipart** | 0.0.9 | File/form uploads (evidence attachments). |
| **NetworkX** | 3.3 | **The graph engine.** In-memory directed graph: nodes/edges, connected components, cycle detection, BFS/DFS, centrality — the live source of truth for the demo/hot path. |
| **SciPy** | 1.13.0 | Numerical backing for graph analytics / centrality / scoring math. |
| **Neo4j (driver)** | 5.23.0 | Phase 2+ persistent banking knowledge graph — the durable graph source of truth (used by the BLING Union-Bank service). |
| **scikit-learn** | 1.4.2 | Blue Team V1 **IsolationForest** anomaly detector + statistical features. |
| **XGBoost** | 2.0.3 | Blue Team V1 gradient-boosted fraud classifier. |
| **SHAP** | 0.45.1 | Explainability for the V1 ML models (feature attributions). |
| **NumPy** | 1.26.4 | Math everywhere — and the **entire Red Team is pure NumPy / torch-free** (GA, MAP-Elites, PPO, GraphGAN). |
| **pandas** | 2.2.2 | Tabular handling of transaction batches / datasets / benchmarks. |
| **joblib** | 1.4.2 | Model persistence (save/load trained V1 estimators). |
| **reportlab** | 4.2.5 | Generates forensic **PDF evidence reports** for cases. |
| **httpx / aiofiles / anyio** | 0.27 / 23.2.1 / 4.3.0 | Async HTTP (UB/Ollama calls), async file IO, async primitives. |
| **Faker** | 24.11.0 | Synthetic transaction / account generation for the simulator and benchmarks. |
| **orjson** | 3.10.3 | Fast JSON serialization for the WS stream and APIs. |
| **python-dateutil / python-dotenv** | 2.9.0 / 1.0.1 | Date math (recovery age-decay) and env/config loading. |
| *Phase-3 (planned)* | `psycopg[binary]`, `redis` | Postgres persistence + Redis cache/queue once wired. |

**Key backend modules (and their job):**
- `graph_engine/graph_manager.py` — NetworkX graph build, first-class cash nodes, components, analytics.
- `blue_team_v2/` — deterministic detector: 18-factor `NodeMetrics` → 11 detectors → evidence → cluster verdict (LOG 0.38 / REVIEW 0.62 / HIGH_RISK 0.83).
- `blue_team/` (V1) — ML/statistical engine (IsolationForest + XGBoost + GraphSAGE/GAE + rule classifier).
- `blue_team_v2/router.py` — selects V1/V2 via `ACTIVE_BLUE_TEAM`; shadow mode runs both for comparison.
- `anomaly_detection/` — IsolationForest pass over the live graph.
- `recovery/` — 10-factor "can we recover the money?" scorer + funnel + ranked actions + simulator (`/api/recovery/*`).
- `case_management/` — investigator cases: timeline, evidence, notes, assignment (JSON-persisted).
- `auth/` — banking-grade investigator login, JWT/RBAC, global account search, account dossiers (stdlib-based).
- `evidence/` — forensic evidence generation (PDF via reportlab).
- `adversarial_governance/store.py` — Training Queue, immutable audit trail, dedup/merge, Blue Knowledge Base.
- `ub_service/` — backend surface for the Universal Brain.
- `simulator/` + `streaming/` — the unified sample feed and live broadcast.
- `api/redteam.py` — localhost-gated Red Team panel API (`ENABLE_REDTEAM_PANEL`).

### 3.2 Frontend — 3D investigation SPA (`frontend/`, `:3000`)

| Technology | Version | Role |
|---|---|---|
| **React** | 18.3.1 | UI framework for the whole investigator app. |
| **TypeScript** | 5.4.5 | Type-safe app code (strict graph/verdict typing). |
| **Vite** | 5.3.1 | Dev server + build; proxies `/api` and `/ws` → `:8000`. |
| **three.js** | 0.184 | The 3D rendering engine for the graph scene. |
| **react-force-graph-3d** | 1.29.1 | 3D force-directed graph component (the investigation graph). |
| **@react-three/fiber** | 8.18 | React renderer for three.js (declarative scene). |
| **@react-three/drei** | 9.122 | three.js helpers (controls, effects, primitives). |
| **@react-three/postprocessing** | 2.19 | Glow/bloom and post effects on the graph. |
| **d3-force-3d / d3-quadtree / d3-scale** | 3.0.6 / 3.0.1 / 4.0.2 | Force simulation, spatial indexing, scales for the multi-scale cluster layout. |
| **cytoscape** | 3.29 | Alternative/2D graph analytics + layout utilities. |
| **framer-motion** | 11.2 | UI animation / transitions (premium banking feel). |
| **gsap** | 3.15 | Timeline animation (orb, camera, emphasis motion). |
| **recharts** | 2.12 | Dashboards & analytics charts. |
| **lucide-react** | 0.395 | Icon set. |
| **react-router-dom** | 6.30 | App shell routing (login, graph, cases, recovery, dossiers). |
| **date-fns** | 3.6 | Date formatting/age math in the UI. |
| **html2canvas / jspdf** | 1.4.1 / 4.2.1 | Client-side report/snapshot export to PDF. |
| **leva** | 0.10 | Dev tuning controls for the scene. |
| **clsx** | 2.1 | Conditional class composition. |
| **Tailwind CSS / PostCSS / autoprefixer** | 3.4 / 8.4 / 10.4 | Styling system (enterprise-minimal palette). |
| **puppeteer-core** | 24.43 | Headless screenshot / visual verification of the graph. |

**Key frontend modules:**
- `components/GraphScene.tsx` — the 3D scene; merges WS deltas (memoized on `graphSig`), multi-scale cluster forces, restores cash-node identity color every frame + drives red fraud halo.
- `components/graphLayout.ts` — **topology-aware initial placement** (ring→circular, else layered DAG with barycenter sweeps); the engine only refines.
- `store/graphStore.ts` — node color priority: node type → fraud overlay → selection → hover.
- `ai/riskPropagation.ts` — risk-intel layer (node role/risk coloring + narration content).
- `ai/ub.ts`, `hooks/useUB.ts`, `components/ai/UBOrb.tsx` — the in-app voice orb (wake word, SpeechRecognition intents, SpeechSynthesis narration).
- `components/panels/TrainingReviewPanel.tsx`, `RedTeamPanel.tsx` — localhost-gated governance + Red Team UIs.
- `data/sampleDataset.ts` — the unified sample feed (mirrors the backend simulator).

### 3.3 UB — Universal Brain (`ub/` + `backend/ub_service/`, `:8001`)

| Technology | Role |
|---|---|
| **Ollama** (`:11434`) | Local LLM runtime — **no cloud, no data egress**. |
| **llama3.1:8b** | The reasoning/answer model (tuned to honesty; judge mode admits limits). |
| **nomic-embed-text** | Embedding model for the RAG knowledge index. |
| **FastAPI** | UB API surface (`/ub/*`): 6 modes — chat, founder, developer, presentation, demo, judge. |
| Browser **SpeechRecognition / SpeechSynthesis** | Wake-word + voice intents + narration in the orb. |

UB "learns" by **re-indexing** (`python -m ub index`) over the real codebase + docs — it
regenerates summary JSONs and re-embeds every chunk; **no fine-tuning**. Every answer is grounded
in project/architecture summaries + top-k retrieved chunks + recent conversation.

### 3.4 BELS — Blockchain Evidence Ledger (`bels/`, FastAPI, `:8200`)

Internal **Proof-of-Work hash-chain** that anchors evidence **SHA-256** hashes (files stay
off-chain). Full lifecycle: submit → custody → verify → reports → dashboard. Provider-abstracted
so it can migrate to a real bank/RBI chain later. Court-grade chain of custody.

### 3.5 Adversarial plane (`red_team/`, pure NumPy, offline)

| Component | Role |
|---|---|
| **Genetic Algorithm** (`evolutionary_engine`) | Warm-started GA; genome = ordered attack "moves"; deterministic via blake2b seeding; fitness ≈ 0.55·evasion + 0.25·stealth − 0.15·distortion − 0.05·complexity. |
| **MAP-Elites** (quality-diversity) | Descriptors = fragmentation × distortion (30-cell grid); finds **12 distinct evading families vs the GA's 5** — kills mode collapse, yields the diverse corpus a detector-level hardener needs. |
| **PPO RL agent** | Attack as a one-edit-at-a-time MDP; 2-layer MLP actor-critic, clipped surrogate + GAE; ASR 0→0.56 on the cheap arsenal. |
| **GraphGAN surrogate** | NumPy MLP distilled from real V2 scores (fidelity MAE ~0.033) as a fast reward model; re-distilled on-policy each round to avoid Goodhart — agreement climbs .56→.91. |
| **6 context signals** (the hardening ladder) | provenance (KYC) · behavioural (own baseline) · coordination (hub-less crowd / B1 counter) · relationship (counterparty history) · relationship-maturity (history depth × age → ends arms race in economics). |
| **CRUCIBLE** (`red_team/crucible`) | Union-Bank analogue: nightly genome evolution → human gate → prophecy/learning feedback. |
| **BlueTeamOracle / HardenedBlueTeam** | Wrap the *real* V2 engine so the adversary attacks production logic, not a toy. |

### 3.6 Infrastructure, deployment & ops

| Technology | Role |
|---|---|
| **Railway** | Backend hosting (`railway.toml` + `nixpacks.toml`, Python 3.11, `uvicorn :$PORT`). |
| **Vercel** | Frontend hosting (root `frontend/`, `production` branch, `VITE_API_URL` → Railway). |
| **Docker / docker-compose** | BLING Union-Bank service + CRUCIBLE (Postgres + Neo4j + Celery), standalone. |
| **Celery** | Async task queue in the BLING forensic service. |
| **Apache Kafka + Flink** (`infrastructure/`) | Heavy `main`-branch streaming build (event ingestion / stream processing). |
| **Git / GitHub** (`BYTEJAYS/TRANSACTION-GRAPH-ENGINE`) | Branch strategy: `main` = full heavy build, `production` = deploy-optimized. **Never merge `production → main`.** |
| **`control/` suite** | `start_tgie` / `stop_tgie` / `status` / `restart` `.command` launchers — bring up Ollama → UB → backend → frontend in order. Nothing auto-starts. |
| **pytest** | Backend test suite (cash, governance, layout, detection regressions). |

---

## 4. Blue Team V2 — how a verdict is produced (the detection core)

1. **Graph build** — transactions → directed graph; **connected components are the unit of analysis.**
2. **Per-node metrics** — degree, fan-in/out, velocity, value flow, betweenness/closeness (sampled at scale), dormancy, role (origin/hub/mule/relay/sink).
3. **11 detectors** — `layering`, `smurfing`, `mule_accounts`, `fan_in`, `fan_out`, `velocity`, `cashout`, `circular_flow`, `bridge_accounts`, `dormant_accounts`, `synthetic_networks` — each emits explainable evidence.
4. **Scoring** — 18-factor per-node score; **detector evidence dominates**, role base risk caps ~0.34, topology is a tie-breaker. A node with no detector firing tops out ~0.42 → effectively **detector-gated**.
5. **Cluster verdict** — aggregate component risk vs thresholds **LOG 0.38 / REVIEW 0.62 / HIGH_RISK 0.83.** Deterministic, reproducible; every flag has evidence + a path.

**Absolute gate constants** (e.g. ~₹25k hop layering, mule/structuring band ~[46k,50k), ~₹150k/200k
fan/velocity, 4-hop chain, 4-degree fan, 6h dormancy, 600s burst) make V2 **auditable** — and make
evasion margins computable, which is exactly what the Red Team exploits to harden it.

---

## 5. The adversarial immune system (Red⇄Blue self-play)

The Red Team evolves attacks against the **real** V2 engine, discovers the defender's missing
capabilities, then the **context signals** supply them. The engagement *proved* that a
context-free, component-isolated detector is evadable on every axis — and that each axis is closed
by injecting **context (memory)**. Composed (V2 + all five signals) the full adversary — including
the conduit-split mule mesh + history seasoning — is driven to **0% ASR at 0% benign FP** on
construction-honest corpora. The arms race ends in **economics** (relationship-maturity).

---

## 6. Human-in-the-loop governance (the only learning path)

- **Principle:** Red Team is the attacker and **never directly trains** Blue. Blue learns **only**
  from investigator-approved cases. Nothing enters the Knowledge Base automatically.
- **Workflow:** Red attacks → Blue investigates → **Detected** ⇒ Red must evolve a harder variant
  (case NOT used to train Blue); **Missed** (real on-graph evasion) ⇒ enters the **Training Queue**.
- **Governance layer** (`adversarial_governance/store.py`, JSON-persisted): Training Queue,
  immutable **audit trail** (who/when/outcome), **dedup** (same-signature patterns merge), Blue
  Knowledge Base. Only **"Learn from this Case"** adds knowledge; reject/ignore/archive discard.
- The live platform was **already human-gated** — `blue_team_v2` is stateless and never mutated at
  runtime; the only auto-hardening is an **offline CLI research loop**, not wired into the app.

---

## 7. Investigator-facing capabilities

- **3D investigation graph** — topology-aware, money flows downward, rotatable/zoomable/draggable.
- **Cash endpoints** — emerald `CASH_SOURCE` (cash in) / gold `CASH_EXIT` (cash out), identity color
  permanent, fraud shown as a pulsing red halo (non-destructive overlay).
- **Recovery engine** — "can we still recover the money?" with age-decay, funnel, ranked actions, simulator.
- **Case management** — timeline, evidence, notes, assignment, JSON persistence.
- **Auth & navigation** — JWT/RBAC login, global account search, account dossiers.
- **BELS evidence ledger** — tamper-evident chain of custody.
- **UB voice orb** — call-driven narration + Q&A, fully local.

---

## 8. Payment rails & ingestion

- Ingress: `POST /transaction/manual` (list) → processed sequentially → graph deltas streamed over WS.
- `PaymentRail` values: **UPI, IMPS, RTGS, NEFT, CASH, CASH_IN, CASH_OUT.**
- **Two cash conventions (intentional):** first-class (`CASH_IN`/`CASH_OUT` → real `CASH_SOURCE`/
  `CASH_EXIT` graph nodes) vs legacy satellite (`CASH` → off-graph `add_cash_event`). The first-class
  path means cash endpoints fully participate in components, cycles, community detection, recovery & analytics.

---

## 9. Honest limitations (never hidden — this is a feature)

- **Production readiness ≈ 55/100.** TGIE is an advanced prototype / research platform, not a deployed bank system.
- **Native V2 false-positive rate on realistic benign traffic ≈ 56.7%** — the context signals fix it,
  but the KYC / behavioural / relationship registries are currently **synthetic**, so every "0% FP / 0% ASR"
  is **construction-honest**, not production-measured.
- **Strict on-graph attack success = 0%** — most adversarial wins are **partition-dependent** (the B1
  component-isolation blind spot). Reported separately from permissive ASR on purpose.
- **V1 caveats:** the GraphSAGE/GAE GNN is effectively **untrained** (random weights → noise embeddings);
  IsolationForest has a **label-leak** (reads ground-truth `fraud_pattern`, "B5"); XGBoost overfits its own synthetic generator.
- **Documented V2 blind spots:** B1 (components scored in isolation — no cross-component/temporal correlation,
  the dominant weakness) and B2 (stateless per call — slow time-distributed attacks unseen).
- Recent cash / layout / governance / adversarial work is **not necessarily committed to git**.
- Numbers must be **recalibrated on real account history** before being quoted as deployable.

---

## 10. Run it locally

```bash
# Backend  (from backend/)
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info

# Frontend (from frontend/)
npm install
npm run dev                      # http://localhost:3000  (proxies /api, /ws → :8000)

# Red Team panel (localhost only)
ENABLE_REDTEAM_PANEL=1 .venv/bin/uvicorn main:app --port 8000

# Full stack (Ollama → UB → backend → frontend, in order)
control/start_tgie.command       # control/stop_tgie.command to bring it down
```

> The 3D graph requires the backend on `:8000`; without it, submitted transactions produce nothing.

**Live deployment** — Backend: Railway (`transaction-graph-engine-production.up.railway.app`);
Frontend: Vercel (`production` branch, root `frontend/`). BLING + CRUCIBLE run standalone (Union
Bank), not on the public deploy.

---

## 11. Key invariants (do not regress)

- `mergedData` memoized on `graphSig` — prevents heartbeat reheat / vibrating blob.
- Never call `d3ReheatSimulation()` before first `graphData` — blank-canvas crash.
- Decentralized cluster forces — no global center/origin gravity (no solar-system hierarchy).
- `red_team/engine` isolation contract — no `blue_team` import-time coupling.
- V1 untouched by V2 — V2 is additive / opt-in.
- Localhost-gated Red Team & Training panels — never exposed on the public deploy.

---

*Generated 2026-06-30. Authoritative tree: `~/Desktop/TGIE`. When code and this doc disagree, the
code wins. Companion docs: `TGIE_MASTER_ARCHITECTURE.md`, `TGIE_PROJECT_KNOWLEDGE.md`,
`TGIE_DETECTION_AND_ADVERSARIAL_DEEPDIVE.md`.*
