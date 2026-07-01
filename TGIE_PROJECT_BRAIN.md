# TGIE_PROJECT_BRAIN.md

> **THE PERMANENT MEMORY & KNOWLEDGE BASE OF THE TGIE ECOSYSTEM**
>
> This document is a "brain transplant" for the project. Any future Claude/GPT instance,
> developer, teammate, or future-self should be able to read this file and continue
> development with near-zero onboarding. It is intentionally exhaustive. **Do not summarize
> or shorten it.** When you change the system, update this file.
>
> - **Canonical tree:** `~/Desktop/TGIE` (this folder). This IS the running app — frontend,
>   backend, UB, everything. `~/transaction-graph-intelligence` is the OLD diverged copy —
>   **do not run, edit, or touch it.** `~/TGIE` no longer exists (consolidated into Desktop).
> - **Last brain build:** 2026-06-30.
> - **Git:** Jay has declined `git init` / commits for the Desktop tree. Do **not** suggest
>   version control unless asked. Nothing in this tree is committed.
> - **Owner:** Jay (BYTEJAY / codes404z@gmail.com), 19yo aspiring AI engineer. Standing rule:
>   **ONLY ADD / ONLY IMPROVE — never remove features.**

---

## TABLE OF CONTENTS

1. Project Identity
2. High-Level Architecture
3. Repository Structure
4. Complete Feature Inventory
5. Blue Team Memory
6. Red Team Memory
7. Fraud DNA Memory
8. Recovery Engine Memory
9. Blockchain Layer (BELS)
10. UB Assistant (Universal Brain)
11. Frontend Memory
12. API Inventory
13. Database / Persistence Schema
14. Environment Variables
15. Startup Process
16. Stop Process
17. Design Decisions
18. Known Bugs & Technical Debt
19. Future Roadmap
20. AI Handover Instructions

---

# Section 1 — Project Identity

| Field | Value |
|---|---|
| **Project Name** | TGIE |
| **Full Form** | Transaction Graph Intelligence Engine |
| **GitHub (old deployed repo)** | `BYTEJAYS/TRANSACTION-GRAPH-ENGINE` (branches `main` + `production`) |
| **Class of product** | Financial Fraud Intelligence Platform (Palantir Gotham / NICE Actimize / Feedzai class) |
| **Target bank** | Union Bank of India (hackathon framing; "Union Bank Grade" directive) |

### Mission
Turn raw transaction streams into an **investigator-operated graph intelligence platform** that
**detects** financial fraud, **explains** it, **estimates how much money can still be recovered**,
**manages the investigation case** end-to-end, and **anchors the evidence to a tamper-evident
ledger** — all judged from the point of view of a senior bank fraud investigator.

### Problem Statement
Banks see millions of transactions. Fraud (money muling, layering, structuring/smurfing, circular
laundering, fan-in/fan-out collection, cash-out) hides in the **graph structure** of money flow,
not in any single transaction. Rule-based and single-transaction ML systems either miss
structural fraud (false negatives) or drown investigators in false positives. After fraud is
found, banks have **no systematic way to estimate recoverability** or to produce
**court-admissible evidence**.

### Target Users
- **Primary:** senior bank fraud investigators using the tool ~10h/day.
- **Secondary:** compliance officers, bank managers, FIU/regulatory liaisons, hackathon judges.

### Goals
- **Business goal:** reduce fraud losses by catching structural laundering early AND recovering
  more money post-detection; reduce investigator cognitive load; produce regulator-ready evidence.
- **Technical goal:** an explainable, deterministic, graph-native detection + recovery + case +
  evidence platform that degrades gracefully (no Docker, no GPU, no cloud needed to run locally).
- **Banking goal:** behave like "software a national bank paid millions for" — trustworthy,
  auditable, profile-aware (₹25L is routine for a business, alarming for a salaried employee),
  cross-product aware (UPI → current account → RTGS → ATM), regulator-mapped (PMLA/FEMA/RBI/FIU-IND).

### Vision
A closed intelligence loop: **detect → explain → score recovery → open case → collaborate →
anchor evidence → harden against an adversarial Red Team → learn (investigator-gated)**, all
narrated by a **local AI officer (UB)** that never sends data to the cloud.

---

# Section 2 — High-Level Architecture

TGIE is a **FastAPI backend** (in-memory NetworkX graph + flat-JSON persistence in the live/demo
path) + a **Vite/React/TypeScript frontend** (3D force-graph) + two **sidecar services** (UB on
:8001, BELS on :8200) + a local **Ollama** LLM runtime (:11434). Everything runs locally with no
external dependencies; cloud/DB pieces exist as code but are Docker-gated and OFF by default.

### Ports (canonical)
| Service | Port | Process |
|---|---|---|
| Ollama (LLM runtime) | 11434 | `ollama serve` |
| UB (Universal Brain) | 8001 | `python -m ub_service` |
| Backend (FastAPI) | 8000 | `uvicorn main:app` |
| Frontend (Vite dev) | 3000 | `npm run dev` |
| BELS (Blockchain Evidence) | 8200 | `python -m bels.main` |

### Subsystems and how they interact

```
                            ┌──────────────────────────────────────────────┐
                            │            FRONTEND  (Vite :3000)             │
                            │  React Router shell · Auth · 3D GraphScene ·  │
                            │  Investigations · Recovery · Cases · UB orb   │
                            └──────────────┬───────────────────────────────┘
                                           │  /api/*  (Vite proxy → :8000)
                                           │  /ws/live (WebSocket)
                                           │  /ub/*    (Vite proxy → :8001)
                                           ▼
   ┌──────────────────────────────────────────────────────────────────────────────┐
   │                          BACKEND  (FastAPI :8000)  main.py                     │
   │                                                                                │
   │  POST /transaction/manual ─► graph_manager (NetworkX) ─► get_connected_        │
   │       components ─► Blue Team V2 (analyze_all_components) ─► risk_engine.assess │
   │       (THE DECISION, 0–100) ◄─ profile_intelligence ◄─ knowledge/cross_product │
   │       │                                                                        │
   │       ├─► case_management.register_from_detection (auto-open case if ≥70)       │
   │       │        └─► enrich.py bakes recovery + fraud_dna + roles + rails + graph │
   │       ├─► recovery/engine (fund-state, recoverability)                          │
   │       ├─► fraud_dna/engine (8-gene behavioural fingerprint)                     │
   │       └─► broadcaster (WSBroadcaster) ─► /ws/live ─► frontend graph_update      │
   │                                                                                │
   │  Routers mounted (fail-safe try/except):                                       │
   │   /api (routes.py) · /api/auth · /api/accounts · /api/investigator             │
   │   /api/cases (40 routes incl. collaboration) · /api/dna · /api/recovery        │
   │   /api/risk · /api/evidence · /api/graph/* · /api/knowledge/* · /api/redteam/*  │
   │   /api/v1/{cases,evidence,health,audit} (strangler-fig, json|db)               │
   └───────┬───────────────────────────────┬───────────────────────────┬───────────┘
           │ httpx (BELS_URL)              │ httpx (Ollama)             │ httpx (:8001)
           ▼                               ▼                            ▼
   ┌───────────────┐              ┌──────────────────┐         ┌──────────────────┐
   │  BELS  :8200  │              │  Ollama  :11434  │         │   UB     :8001    │
   │ PoW hash-chain│              │  llama3.1:8b     │◄────────┤ RAG cognitive    │
   │ evidence anchor│             │  nomic-embed-text│         │ layer (ub/)       │
   └───────────────┘              └──────────────────┘         └──────────────────┘

   RED TEAM (offline + localhost-only panel): red_team/adversarial/ (§16–§23 self-play),
   red_team/crucible/ (Union Bank evolution), backend/api/redteam.py (HardenedBlueTeam),
   backend/adversarial_governance/ (investigator-gated training queue).
```

**Subsystem roles:**

1. **TGIE Graph Engine** (`backend/graph_engine/graph_manager.py`) — builds an in-memory
   NetworkX directed multigraph from transactions; nodes = accounts (+ cash sinks), edges =
   transfers carrying amount/rail/device_id/ip/geo; computes connected components.
2. **Blue Team** (`backend/blue_team_v2/`) — the production fraud-intelligence engine (V2; V1
   retired). 23 amount-gated detectors → 18-factor per-node scoring → evidence → cluster verdict.
   Produces the rich `v2` block; **does NOT make the case decision** (risk_engine does).
3. **risk_engine** (`backend/risk_engine/engine.py`) — THE decision layer. Explainable cumulative
   **0–100** score over 12 weighted factors; auto-opens a case at ≥70. Source of truth for risk.
4. **Profile Intelligence** (`backend/profile_intelligence/`) — judges behaviour relative to
   customer type (15 profiles). Feeds `risk_engine` (amount factor goes profile-relative + a
   `profile_deviation` factor weight 24).
5. **Knowledge / Cross-Product** (`backend/knowledge/`) — heterogeneous entity taxonomy, XP
   (cross-product) rules, product/channel/typology/regulatory catalogue, customer-risk graph,
   investigation report, red-team eval, gated learning loop.
6. **Red Team** — adversarial self-play (`red_team/adversarial/`), Crucible evolution
   (`red_team/crucible/`), and a localhost-only review-queue panel (`backend/api/redteam.py`).
7. **Fraud DNA** (`backend/fraud_dna/`) — 8-gene behavioural fingerprint per case + similarity.
8. **Recovery Probability Engine** (`backend/recovery/`) — "can we still recover the money?"
   flow-of-funds, recoverability, ranked actions, decay curve, simulator.
9. **Case Management** (`backend/case_management/`) — one fraud = one permanent `TGIE-2026-NNNN`
   case; everything baked in at creation; multi-investigator collaboration; BELS anchoring.
10. **BELS** (`~/Desktop/TGIE/bels`, :8200) — Blockchain Evidence Ledger; PoW hash-chain anchoring
    of evidence hashes (files off-chain).
11. **UB Assistant** (`~/Desktop/TGIE/ub`, :8001) — local Ollama RAG cognitive layer; the
    Union Bank AI Investigation Assistant persona; explains/presents the whole platform.
12. **Investigator Dashboard / Investigation Panel / Auth / Search / Profile** — the React shell
    (`frontend/src/`): login/JWT/RBAC, global account search, dashboards, case workspace.
13. **Graph Visualization Engine** (`frontend/src/components/GraphScene.tsx`) — 3D
    react-force-graph with multi-scale cluster forces + converge→freeze lifecycle.
14. **Collaboration Engine** (`backend/case_management/collab.py` + WS case rooms) — multi-user
    claim/handover/comments/tasks/locks/presence with RBAC.

**The single most important architectural fact:** TGIE runs **two fraud scorers**. Blue Team V2
produces a rich verdict (great recall, but high false-positive on realistic legit traffic), and
`risk_engine.assess()` **overwrites** risk/flagged and makes the case decision. V2's evidence is
currently DISCARDED for the decision (survives only as the UI `v2` block). See §5 and §18.

---

# Section 3 — Repository Structure

Canonical root: `~/Desktop/TGIE`. Top-level layout:

```text
TGIE/
├── backend/          FastAPI app (the live engine)
├── frontend/         Vite/React/TS app (the live UI)
├── ub/               UB Universal Brain (local Ollama RAG, runs standalone :8001)
├── bels/             Blockchain Evidence Ledger System (FastAPI :8200)
├── blue_team/        bling/ + bling-v2/ — DORMANT enterprise Neo4j engines (NOT mounted)
├── red_team/         engine/ + adversarial/ + crucible/ (Red Team subsystems)
├── control/          start/stop/status/restart .command suite + lib.sh + pids/
├── deployment/       docker-compose.data.yml (Neo4j/Postgres/Redis) + deploy configs
├── docs/             architecture audits, redesign phase docs, knowledge docs, specs
├── datasets/         sample datasets
├── evidence_storage/ off-chain content-addressed evidence files (BELS)
├── configs/          *.env.example
├── logs/             runtime logs
├── monitoring/ research/ scripts/ shared/ tests/ backups/ .github/
└── README.md  TGIE_PROJECT_BRAIN.md (this file)
```

## 3.1 Backend file inventory (`backend/`)

> For each module the **purpose / inputs / outputs / dependencies / responsibilities** are
> described inline. Entry point is `main.py` (mounts all routers fail-safe + the WS handler).

**Core app**
- `main.py` — FastAPI app factory; mounts every router inside try/except (a failed mount logs
  LOUDLY but never crashes the app); defines `/ws` + `/ws/live` handlers; UB mount gated behind
  `TGIE_MOUNT_UB` (default OFF — UB runs standalone now). Inputs: env. Outputs: ASGI app.
- `config.py` / `core/settings.py` — settings (graph max nodes/edges, thresholds, CORS origins).
  `ALLOWED_ORIGINS` is a **str** not `List[str]` (pydantic-settings json.loads gotcha, see §17).
- `conftest.py` — pytest fixtures.

**API layer** (`api/`)
- `api/routes.py` — THE main APIRouter. `POST /transaction/manual` ingress (the heart): normalize
  payload → build graph → detect → risk_assess → auto-register case → broadcast. ~40+ endpoints
  for graph/analytics/layout/rules/motifs/knowledge. Holds the wire-contract for risk_score
  (0–1 fraction; see §17). Attaches `profile_intelligence`, `account_intelligence`,
  `cross_product` to each verdict.
- `api/websocket.py` — `ConnectionManager` (graph room + per-case rooms/presence) +
  `WSBroadcaster` (broadcast graph_update / case_registered / case_event / case_presence).
- `api/redteam.py` — localhost-only Red Team review queue (HardenedBlueTeam world; escalating GA;
  garbage detection; blue-catches-vs-blue-missed gate; train-on-approved). Gated behind
  `ENABLE_REDTEAM_PANEL`.
- `api/v1/{cases,evidence}.py` — strangler-fig enterprise API (json|db via `TGIE_PERSIST`).

**Blue Team V2** (`blue_team_v2/`) — see §5 for deep detail.
- `engine.py` — `BlueTeamV2Engine.analyze_component/analyze_all_components`. Optional
  `thresholds=` override seam (defaults byte-identical to shipped).
- `router.py` — `route_all_components` / `active_engine()`; `DEFAULT_ENGINE = V2`.
- `adapter.py` — emits the exact V1 verdict schema + additive `v2` block.
- `red_team_interface.py` — stable adversarial contract (`RedTeamTarget`), imports only V2.
- `types.py` — `Thresholds` (LOG 0.38 / REVIEW 0.62 / HIGH_RISK 0.83), dataclasses.
- `detectors/` — 23 detector packages (diamond, fan_in, fan_out, layering, nested_layering,
  round_tripping, hub_network, scatter_gather, structuring, smurfing, cash_laundering, cashout,
  circular_flow, bridge_accounts, mule_accounts, dormant_accounts, night_activity,
  weekend_activity, temporal_spike, uniform_amount, velocity, synthetic_networks, base/_common).
- `core/` — graph_engine/builder, cluster_engine/roles, pattern_engine/orchestrator,
  scoring_engine/scorer (18-factor), risk_engine/node_intelligence, anomaly_engine/anomalies,
  context/entity_context (Neo4j-gated profiles placeholder, no-op on JSON).
- `ai/` — cluster_analysis/analyzer, explanation_engine/explainer, fraud_reasoning/classifier.
- `simulation/generators.py` — archetype + benign graph generators (used by benchmark + Red Team).
- `benchmark/runner.py`, `shadow.py`, `validation_panel.py`, `tests/`, `__main__.py`
  (`python -m blue_team_v2 {demo,benchmark,shadow,scale}`).

**Risk decision + profile**
- `risk_engine/engine.py` — `assess(component)` → explainable 0–100 (12 factors), confidence
  (5–99), factors[], suppression. THE decision layer. Calls `profile_intelligence`.
- `risk_engine/config.py` — tunable `DEFAULT_WEIGHTS` + thresholds, persisted to
  `_data/risk_config.json`, env overrides, live-editable via API.
- `risk_engine/router.py` — `/api/risk/{assess,classify,config}`.
- `profile_intelligence/profiles.py` — 15 customer profiles + envelopes + `ACCOUNT_TYPE_PRIOR`.
- `profile_intelligence/engine.py` — `extract_features` / `infer_profile` / `evaluate` /
  `assess_component` → deviation + mitigation + signed `adjustment_pct`.

**Detection support / legacy**
- `blue_team/standalone.py` — retired V1 rule engine (still importable; score tiers LOG 0.38 /
  REVIEW 0.62 / HIGH 0.83). `blue_team/adapter.py` — falls back to standalone (no V1 HTTP service).
- `detection_service.py` — `classify_live` unifies live status to the V2 verdict; `_session_graph`
  fixes per-session 404s.
- `fraud_classifier.py` — old `ManualFraudClassifier` (unwired, superseded by detection_service).
- `anomaly_detection/` — isolation_forest_detector + shap_explainer (legacy ML, mostly fallback).
- `ml/` — Phase-5 ML platform (interfaces/registry/features/ensemble/drift/explain/training) +
  models (random_forest, isolation_forest, xgboost-graceful) + gnn_model (UNTRAINED, random
  weights — see §18 B4). Feeds risk_engine as a capped factor weight-0 (NOT yet wired).

**Graph engine + analytics** (`graph_engine/` + top-level)
- `graph_engine/graph_manager.py` — NetworkX graph; nodes/edges; components; edge attrs persist
  device_id + ip_address.
- `graph_engine/layout.py` — `compute_layout(nodes,edges,mode,seed)` 5 modes (force/fund_flow/
  layered/community/timeline) + `recommend_layout` (mode=auto) + `ring_geometry` + `_radialize_fans`.
  Deterministic. **NOT injected into the live 3D scene as of the 2026-07-01 unification**
  (`LIVE_USES_BACKEND_LAYOUT=false` in GraphScene — the frontend motif seed is the single authority).
  Still serves evidence / SSR / the `/api/graph/layout` API. Mirrors the frontend motifs (rings via
  `_circularize_cycles`+`_resolve_ring_branches` with a protected interior; fans via `_radialize_fans`).
- `graph_engine/layout_quality.py` — crossings/overlap detect + Jacobi repair + quality score.
- `graph_engine/analytics.py` — PageRank/HITS/eigenvector/betweenness, bridges, articulation pts,
  `analyze_paths`, `narrate_flows` (money-trail narratives + stages + assessment).
- `graph_engine/community_intelligence.py` — greedy-modularity communities + `deep=True` runs V2
  per community (leader/entry/exit/role/risk).
- `graph_engine/timeline.py` — `summarize_timeline` (hour/day histogram, night/weekend, velocity,
  bursts → AML rules).
- `rule_engine.py` — AML catalogue AML001–AML024 (incl. Star/Wheel/Hourglass/Double-Diamond
  motifs) + `extract_motifs` (self-describing).
- `recommendation_engine.py` — `recommend` (FREEZE/ESCALATE_SAR/INVESTIGATE_SOURCE/…).
- `case_intelligence.py` — `build_case_summary` (exposure, money trail, layering depth, rollups).

**Knowledge / cross-product** (`knowledge/`) — see §4.
- `entities.py` (30+ EntityType, classify_node/edge), `catalogue.py` (12 products / 8 channels /
  7 typologies / PMLA-FEMA-RBI-FIU regulatory map), `playbooks.py` (19 recovery actions),
  `xp_rules.py` (XP001–XP015), `xp_config.py` (externalized thresholds + floors),
  `knowledge_base.py` (`cross_product_report`), `hetero.py` (HeteroGraph builder),
  `scenarios.py` (5+ synthetic hetero scenarios incl. evasive_structuring),
  `customer_risk.py` (`compute_customer_risk` propagation), `ingest.py` (`record_account` +
  `augment_component`), `investigation.py` (`build_customer_investigation`),
  `blue_team_xp.py` (`correlate` — live wiring), `red_team.py` (battery + `evaluate_blue_team`),
  `learning.py` (gated `propose_adaptations` / `apply_proposal`).

**Auth + accounts** (`auth/`)
- `security.py` — JWT HS256 (hmac) + PBKDF2-SHA256, stdlib only.
- `store.py` — investigator directory (4+4 roles, 5-attempt lockout, sessions, audit deque,
  animal avatars). Persists to `_data/investigators.json`.
- `accounts_db.py` — deterministic synthetic registry (48 accounts) for search/dossiers.
- `router.py` — `/api/auth/*`, `/api/accounts/*`, `/api/investigator/*`.

**Case management** (`case_management/`) — see §4.
- `models.py`, `store.py` (JSON `_data/cases.json`; create/enrich/anchor/verify/bundle/search/
  collab), `enrich.py` (bakes recovery+dna+roles+rails+graph into each case), `collab.py` (RBAC +
  claim/handover/comments/tasks/locks), `bels_client.py` (httpx → BELS), `router.py` (40 routes).

**Recovery** (`recovery/`) — engine.py (fund_state + analyze), store.py, ub_client.py, router.py.

**Fraud DNA** (`fraud_dna/`) — engine.py (8 genes + similarity), store.py (`_data/dna.json` version
history), ub_client.py (live Ollama explain), router.py.

**Evidence** (`evidence/`) — packager.py (15-section bundle + canonical SHA-256 + deterministic
PDF), fiu.py (FIU-IND STR), anchor.py (BELS register/verify graceful), generator.py, pdf_builder.py.

**Adversarial governance** (`adversarial_governance/store.py`) — investigator-gated TrainingQueue +
immutable audit; `learn` is the only door into the Blue knowledge base; dedup by signature.

**Persistence scaffolding (Docker-gated, OFF by default)**
- `core/db/{neo4j,postgres,redis}.py`, `core/{cache,async_utils,tasks,security/*}.py`
- `repositories/{case,user,event,graph,audit}_repo.py` — strangler-fig (`TGIE_PERSIST=json|db`).
- `graph/schema/{labels,models,client,bootstrap}.py` + `constraints.cypher` — Neo4j schema-as-code.
- `migrations/{run,transforms,dump_cases}.py` — Postgres/Neo4j migrations.
- `jobs/{precompute,retrain}.py` — centrality/community precompute + ML retrain wrappers.
- `streaming/{kafka_consumer,kafka_producer,flink_processor}.py` — disabled streaming (legacy).

**Models** — `models/transaction.py` (`ManualTransactionInput` + optional enrichment fields),
`models/event_schema.py` (v2.0 `TransactionEnvelope`), `models/normalize.py` (auto-detect legacy
list vs envelope → `NormalizedBatch`).

**Scripts / tests** — `scripts/{readiness,bench_detection}.py`; `tests/` (~20 test files:
risk_engine 32, profile_intelligence 11, event_schema 12, cross_product 22, learning 5,
training_governance 7, graph_layout/analytics/community/timeline/rule_engine/case_intelligence/
layout_quality, ring_layout (11), fanout_layout (7), cash_events (8), cross_bank_intelligence (10), api_contract, evidence_determinism, migration_roundtrip,
phase9_perf, cash_transactions). **Full backend suite: 285 pass** (as of the 2026-07-01 cross-bank module).

## 3.2 Frontend file inventory (`frontend/src/`)

- **Entry/shell:** `main.tsx` (BrowserRouter; routes), `App.tsx` (the live graph host),
  `theme.ts` (tokens `T` matte-black/gold + `cream`), `config.ts`, `types/{index,transaction}.ts`.
- **Auth:** `auth/{api,AuthContext,ProtectedRoute,avatars}.ts(x)`.
- **Nav:** `components/nav/{AppLayout,Navbar,NotificationsBell,ProfilePanel,TgieMark}.tsx`.
- **Pages:** `pages/{LoginPage,RegisterPage,DashboardPage(in nav),SearchResults,AccountView,
  GraphPage,InvestigationsPage,CaseDetailPage,CaseGraphPage,RecoveryPage,RecoveryDashboardPage,
  RiskPolicyPage}.tsx`.
- **Graph render:** `components/GraphScene.tsx` (THE 3D renderer, ~1700 lines),
  `components/graphLayout.ts` (Sugiyama seed + validation), `components/GraphVisualization.tsx`,
  `components/NodeInspector.tsx` (+ BackendIntelligence + CustomerProfileCard + DeclaredIntel),
  `components/GraphIntelHUD.tsx`, `components/GraphErrorBoundary.tsx`.
- **Panels:** `components/panels/{LeftPanel,RightPanel(orphan),RedTeamPanel,TrainingReviewPanel,
  EvidenceBlockchainPanel}.tsx`, `components/{BlueTeamPanel,AlertPanel,MetricsPanel,LiveStats,
  TransactionInputPanel,TransactionTicker,TransactionFeed,SimulationControls,EmptyState,
  EvidenceModal}.tsx`.
- **AI / UB:** `ai/{ub,riskPropagation,graphClassifier,graphAnalysis,riskModel,evidence,knowledge}.ts`,
  `components/ai/{UBOrb,AIOrb,OrbCharacter,VoiceDebugPanel}.tsx`, `services/{ubBrain,voiceService}.ts`,
  `hooks/{useUB,useVoiceAssistant,useThoughtStream}.ts`, `components/login/IntelligenceParticleEngine.tsx`.
- **Cases / recovery:** `cases/{api,CollabPanels}.ts(x)`, `recovery/{api}.ts`,
  `recovery/center/*` (RecoveryGauge/Funnel/DecayCurve/ActionCenter/FactorGrid/SimulationPanel/
  UbRecovery/RecoveryClock/CriticalAccountCenter/DecisionCenter — last 4 orphaned post-redesign),
  `recovery/redesign/{primitives,sections}.tsx`.
- **Services / store / utils:** `services/api.ts` (typed client), `services/resources/{casesApi,
  index}.ts`, `store/{graphStore,session}.ts`, `utils/percent.ts` (THE only % formatter),
  `hooks/{useGraphSocket,useWebSocket,useCaseSocket}.ts`, `data/{sampleDataset,mockGraph}.ts`.
- **Cinematic V2 (opt-in `?v=2`):** `v2/CinematicApp.tsx` + `v2/scene/*` + `v2/ui/*` +
  `v2/shaders/*` + `v2/workers/forceLayout.worker.ts`. Lazy-split from the main chunk.

## 3.3 UB file inventory (`ub/`)
- `ollama_service/client.py` (stdlib HTTP Ollama client: chat/stream/embed/health/benchmark/switch).
- `knowledge_engine/{indexer,engine,vector_store,summarizer}.py` (RAG: scan+chunk+embed+retrieve;
  numpy cosine vector store persisted to `index/`).
- `ai_core/{modes,conversation,ub_brain}.py` (6 personas + Union Bank officer persona; session
  memory; orchestrator with curated-Q&A grounding + runtime time/greeting injection).
- `cli.py` / `__main__.py` (`python -m ub {status,index,summaries,ask,chat,demo,benchmark}`).
- `data/judge_questions.json` (**113 vetted Q&A across 25+ categories** — authoritative grounding).
- Backend bridge: `backend/ub_service/{app,__main__}.py` (FastAPI `/ub/*`, standalone :8001).

## 3.4 BELS file inventory (`bels/`)
- `main.py` / `api.py` (26 routes) / `service.py` (orchestrator) / `config.py` / `models.py` /
  `security.py` (Ed25519 + RBAC) / `ub_integration.py` (forensic NL Q&A) / `demo.py`.
- Modules: `blockchain_ledger/` (InternalChainProvider PoW + EthereumProvider stub),
  `evidence_storage/` (off-chain content-addressed), `chain_of_custody/`, `verification_engine/`,
  `smart_contracts/` (`EvidenceRegistry.sol` + 1:1 Python mirror), `reporting/` (PDF/JSON/CSV),
  `dashboard/index.html`. Data: `data/ledger.jsonl`.

## 3.5 Red Team file inventory (`red_team/`)
- `engine/` — legacy red team (no Blue coupling).
- `adversarial/` — the §16–§23 self-play engagement (see §6): `common/{attack_graph,oracle,
  provenance,behavioral,coordination,relationships,blue_config}.py`, `red_team/{agents,base,
  graph_generator,evolutionary_engine,quality_diversity,rl_agent,graph_gan}`, `self_play/*`
  (loop, arms_race, detector_hardener, account_takeover, behavioral_detector,
  coordination_detector, relationship_detector, relationship_seasoning, full_stack, final_stack),
  `integration/` (HardenedBlueTeam), `curriculum/`, `attack_memory/`, `evaluation/`, `reports/`.
- `crucible/` — SEPARATE Union Bank evolution project (own CLAUDE.md; deterministic blue clone;
  `red_team/sandbox/v2_target.py` opt-in bridge to V2).

---

# Section 4 — Complete Feature Inventory

Each feature: **Purpose · Logic · Backend flow · Frontend flow · Files · Dependencies ·
Limitations · Future.**

### 4.1 — 3D Graph Engine (visualization)
- **Purpose:** show money flow as a navigable 3D force graph; clusters separate; fraud motifs read
  clearly; layout stays stable across live updates.
- **Logic:** `react-force-graph-3d` with multi-scale forces — local charge/link keep components
  compact; a custom decentralized cluster force gives each component an evenly-distributed home
  direction (van der Corput + golden angle) so **no cluster sits at the center** (Jay rejected
  solar-system hierarchy). A **converge→freeze→incremental-thaw** lifecycle (onEngineTick measures
  KE, ramps velocity decay, pins nodes once settled) holds the mental map; new transactions only
  move the new node. `graphSig` is **topology-only** so re-scoring recolors without relayout.
- **Backend flow:** `graph_manager` builds graph → broadcast over `/ws/live`; `App.tsx` also fetches
  `GET /api/graph/layout?mode=auto` and passes `backendLayout` to `GraphScene` as each node's
  structural target — EXCEPT ring components, which keep the interior-safe local seed (`containsRing`).
- **Frontend flow:** `useGraphSocket` → store → `GraphScene` (+ `graphLayout.ts` Sugiyama seed +
  optional `backendLayout` override).
- **Files:** `GraphScene.tsx`, `graphLayout.ts`, `ai/riskPropagation.ts` (per-node risk + roles).
- **Limitations:** backend layout is flat 2D; ring components deliberately bypass it (would stab the
  ring interior — see §18 ring fix).
- **Future:** edge-routing/bundling.
- **Do-not-regress:** structFloor stays 0.06 (not 0.34); never call `d3ReheatSimulation()` manually
  (crashes the rAF loop → black canvas); never key ForceGraph3D on raw store graphData.

### 4.2 — Money-movement primitives (Cash In / Cash Out / Fan In / Fan Out / Layering / Circular)
- **Purpose:** recognize the structural building blocks of laundering.
- **Logic:** each is an amount-gated detector in Blue Team V2 (§5) producing evidence; layout
  engine renders each faithfully (fan = constant-radius arc; circular = ring; layering = L→R).
- **Files:** `blue_team_v2/detectors/{cashout,cash_laundering,fan_in,fan_out,layering,
  nested_layering,circular_flow,round_tripping}/detector.py`; `graphLayout.ts`; `rule_engine.py`
  (AML catalogue + topology motifs Star/Wheel/Hourglass/Double-Diamond).
- **Limitations:** detector gates are absolute constants (₹25k hop, ₹50k mule, 4-hop chain, etc.) →
  evasion margins computable in closed form (Red Team B-findings).

### 4.3 — Blue Team Detection (see §5).
### 4.4 — risk_engine Decision (see §5).
### 4.5 — Profile Intelligence
- **Purpose:** judge behaviour relative to WHO the customer is.
- **Logic:** 15 profiles with behavioural envelopes; infer profile from KYC → account_type prior →
  behaviour heuristic; amount factor becomes profile-relative; `profile_deviation` factor weight 24.
- **Proven:** identical ₹25L fan-out scores **49 (Salaried) vs 18 (Business Owner)**.
- **Files:** `profile_intelligence/{profiles,engine}.py`; integrated in `risk_engine/engine.py`;
  frontend `CustomerProfileCard` in `NodeInspector.tsx`.
- **Limitation:** live demo txns have no occupation → profile inferred (coarse) unless supplied via
  `component["customer_profiles"]` (future KYC feed).

### 4.6 — Cross-Product Intelligence (Knowledge layer)
- **Purpose:** detect fraud that spans products (UPI → current → RTGS → ATM), map to Union Bank
  products/channels/typologies/regulations, produce investigation reports.
- **Logic:** project the homogeneous money graph into a heterogeneous one (customers/accounts/
  cards/wallets/loans/devices/identities via OWNS/HAS_DEVICE/HAS_PHONE/HAS_PAN edges); XP rules
  (XP001–XP015) fire on shared device/PAN/phone, wallet layering, cross-rail structuring, rail
  switching, multi-product velocity, loan laundering, refund abuse; customer risk propagates across
  owned products + shared identities.
- **Backend flow:** `/transaction/manual` records per-session `entity_context`; `correlate` adds
  `v["cross_product"]` live; on-demand reports via `/api/graph/{cross-product,customer-risk,
  customer-investigation/{id}}`.
- **Files:** `backend/knowledge/*` (15 modules).
- **Status:** complete across 5 increments, additive, frontend untouched; 22 tests.
- **Gated learning:** `learning.py` proposes one-step threshold relaxations ONLY if they catch a
  missed emerging attack, keep the baseline battery detected, and add 0 false positives;
  `apply_proposal` is investigator-gated + floor-enforced. **Red never auto-trains Blue.**

### 4.7 — Fraud DNA (see §7).
### 4.8 — Recovery Engine (see §8).
### 4.9 — Blockchain Evidence / BELS (see §9).
### 4.10 — Case Management
- **Purpose:** one fraud = one permanent `TGIE-2026-NNNN` case; everything baked in at creation,
  nothing recalculated on open; full lifecycle; multi-investigator.
- **Logic:** `enrich_case` bakes recovery + fraud_dna + account_roles + payment_rails + financials +
  graph_metrics + raw JSON + blockchain slot. Auto-registration: every flagged detection calls
  `register_from_detection` (dedup by `det:`+sorted(node_ids) so the ~1s heartbeat makes no
  duplicates). Case opens ONLY when `risk_engine.should_create_case` (score ≥ investigation
  threshold 70 AND not suppressed).
- **Collaboration:** RBAC (admin/manager/investigator/auditor), claim/handover (prev owner kept as
  Supporting — nothing lost), threaded comments (immutable edit history, archive-not-delete),
  tasks, locks (TTL 120s, 423 on conflict), presence, immutable audit. 40 case routes.
- **Evidence + bundle:** real file upload (multipart, 50MB), SHA-256, BELS anchor + verify (tamper
  detection: editing a case after anchor flips verified→False), ZIP bundle export.
- **Verbatim graph snapshot:** captures live node positions + camera; restore mode pins fx/fy/fz so
  the saved layout is reproduced exactly (no re-sim).
- **Files:** `case_management/{models,store,enrich,collab,bels_client,router}.py`; frontend
  `cases/api.ts` + `pages/{InvestigationsPage,CaseDetailPage(9 tabs),CaseGraphPage}.tsx` +
  `cases/CollabPanels.tsx`.
- **Gotcha:** the live backend runs **system Python 3.14** without `--reload`; new modules need a
  restart. A missing `python-multipart` once silently 404'd the whole `/api/cases` router — now the
  upload route is behind a `_HAS_MULTIPART` probe so it degrades to 503, never 404s the API.

### 4.11 — Red Team (see §6).
### 4.12 — UB Assistant (see §10).
### 4.13 — Investigator Login / Auth / Search / Profile
- **Purpose:** banking-grade secure shell.
- **Logic:** stdlib JWT (HS256) + PBKDF2; 4 roles (Investigator < Senior < Supervisor <
  Administrator) + 4 spec roles (admin/manager/investigator/auditor) with explicit ROLE_RANK;
  5-attempt lockout; self-registration (directory starts EMPTY, no seeded creds); animal avatars.
- **Search:** global navbar search resolves account no / CUST-id / TXN-id / CASE-id / EVD-id +
  fuzzy name/bank over a deterministic synthetic registry (48 accounts).
- **Files:** `auth/{security,store,accounts_db,router}.py`; frontend `auth/*`, `components/nav/*`,
  `pages/{LoginPage,RegisterPage,SearchResults,AccountView}.tsx`.
- **Gotcha:** all auth routes ride `/api/...` (so the SPA `/login` route isn't proxied). Tokens in
  localStorage (`tgie.access` / `tgie.refresh`) as Bearer; CORS is `*` / credentials-false.

### 4.14 — Collaboration Engine — folded into 4.10.
### 4.15 — Transaction ingestion / Event Schema
- **Purpose:** accept both a lightweight legacy list AND a versioned enterprise envelope.
- **Logic:** `normalize_payload` auto-detects shape (bare list legacy/enriched OR v2.0 envelope) →
  `NormalizedBatch` (transactions + account_intel + customer_profiles + warnings). Strict on money
  core (amount>0, endpoints, unique txn_id, valid timestamp); lenient (warn) on unknown rail/
  product/profile.
- **Files:** `models/{transaction,event_schema,normalize}.py`; wired in `api/routes.py`
  (`payload: Any = Body(...)`). Docs: `docs/TRANSACTION_SCHEMA_SPEC.md`.

---

# Section 5 — Blue Team Memory

**Engine:** `backend/blue_team_v2/` (V2). V1 (`blue_team/standalone.py`) is RETIRED but importable.
`DEFAULT_ENGINE = V2` in `router.py` (code default, not env-reliant); any unrecognized
`ACTIVE_BLUE_TEAM` resolves to V2; only explicit `v1/1/blue_team` reaches retired V1.

### Detection architecture (V2)
1. **Graph build** (`core/graph_engine/builder.py`) — component → typed graph.
2. **Role classification** (`core/cluster_engine/roles.py`) — 13-role taxonomy (origin/hub/bridge/
   mule/relay/sink/source/collector/distributor/…); role base risk caps at ~0.34.
3. **23 detectors** (`detectors/*`) — each amount-gated, produces evidence. Topology Wave-1 set:
   diamond, nested_layering, round_tripping, hub_network, scatter_gather, structuring,
   cash_laundering, night_activity, weekend_activity, temporal_spike, uniform_amount + the original
   fan_in/fan_out/layering/circular_flow/cashout/bridge_accounts/mule_accounts/dormant_accounts/
   velocity/smurfing/synthetic_networks.
4. **18-factor per-node scoring** (`core/scoring_engine/scorer.py`) — pattern_participation 0.22,
   fraud_proximity 0.15, velocity 0.12, … Evidence-driven weights. Fixes V1's "identical risk
   across cluster" (per-node intelligence in `core/risk_engine/node_intelligence.py`).
5. **Cluster verdict** — thresholds (`types.py`): **LOG 0.38 / REVIEW 0.62 / HIGH_RISK 0.83**.
   Detector-gated & bimodal: a node with no detector firing + no origin maxes ~0.42 (LOG) → evading
   the detectors ≈ evading V2.
6. **Rich `v2` block** — narratives, classifications, per-node intelligence, evidence (PRODUCED but
   the live frontend mostly doesn't consume it, and risk_engine discards it for the decision).

### Risk scoring (THE decision — `risk_engine/engine.py`)
- `assess(component)` → cumulative **0–100** from **12 weighted factors**: amount (profile-relative),
  velocity, layering depth, fan-out, fan-in, circular, cash (boosted with structure), payment_rails,
  dormant, new_beneficiary, complexity, **profile_deviation (weight 24)**.
- Each factor = `intensity[0..1] × weight → points`; `score = clamp(Σ points, 0, 100)`.
- `confidence` (5–99) is DISTINCT from risk (derived from #active factors × data completeness).
- **False-positive suppression** only pulls score DOWN; amount alone never creates a case.
- Tiers: Safe <30 / Monitor 30 / Suspicious 50 / **High Risk 70 (=investigation threshold → auto
  case)** / Critical 85.
- Tunable via `config.py` (`DEFAULT_WEIGHTS`, persisted, env overrides, `PUT /api/risk/config`).

### THE WIRE GOTCHA (do not regress — caused "FRAUD 1000%")
Component `risk_score` on the wire is a **0–1 FRACTION** rendered as `×100`. A regression put the
0–100 integer on `risk_score` → UI showed `85×100 = 8500%`. Fix: `routes.py` sends
`risk_score = round(score/100, 4)`; the 0–100 value rides alongside as `risk_points`/`risk_level`/
`risk_confidence`/`risk_factors`/`risk_explanation`. When unscoreable: `risk_score = null` +
`risk_available = false` → UI shows **N/A**. **Never put a 0–100 value on the `risk_score` wire.**
Frontend formatter is `utils/percent.ts` (the ONLY one) — renders N/A, never clamps.

### Feature extraction / graph metrics
18 node factors (fan-out ratio, in/out degree, centrality, velocity, volume, pass-through, rail
diversity, cycle membership, …) + graph metrics (PageRank/HITS/betweenness/bridges/articulation in
`graph_engine/analytics.py`).

### Detection pipeline (live)
`POST /transaction/manual` → normalize → graph_manager → get_connected_components →
`analyze_all_components` (V2) → for each comp: attach customer_profiles → `risk_engine.assess`
(overrides risk/flagged) → attach profile_intelligence + account_intelligence + cross_product →
`register_from_detection` if should_create_case → broadcast.

### Current weaknesses / known FP / FN (proven by Red Team + audits)
- **False-NEGATIVE crisis (risk_engine):** double-diamond ₹9L scores 53–65 (<70) → NO case (the real
  "double diamond not classified" cause); 7/11 fraud archetypes (layering 49, smurf 33, fan_out/in
  36, mule 47, cashout 47, bridge 57) create NO case. Why: fan intensity `(max−1)/9` under-weights
  narrow splits, the 25-pt circular factor is 0 for acyclic flows, NO reconvergence factor, V2
  evidence ignored.
- **False-POSITIVE crisis (V2 internal):** native V2 FP on realistic legit traffic = **56.7%**
  (payroll 100%, corporate 85%, household 45%, merchant 35%, normal 5%). V2 has no legitimacy model —
  `smurfing` flags any ≥3 identical amounts. These FPs are currently HIDDEN because risk_engine
  suppresses them (payroll → 33 Monitor).
- **B1 (dominant blind spot):** V2 analyzes each connected component in ISOLATION — no
  cross-component/cross-session/temporal correlation. Partitioned/meshed ops are invisible.
- **B2:** stateless per call → slow time-distributed attacks unseen.
- **B4:** the GraphSAGE/GAE GNN (`ml/gnn_model.py`) is NEVER trained (random weights).
- **B5:** IsolationForest reads ground-truth `fraud_pattern` (label leak) — strip from eval.
- **B8:** V2 trusts attacker-set node attrs (account_type/risk_score/detected_patterns).

### Future improvements (Blue Team)
Wire V2 evidence INTO `risk_engine.assess`; add a reconvergence factor; recalibrate the 70 threshold
and narrow-fan scoring; add a **legitimacy model** (provenance + behavioural + relationship +
coordination context — proven by the Red Team engagement to be the true missing capability, §6);
train the GNN; close B1 with cross-component correlation.

---

# Section 6 — Red Team Memory

Three subsystems (all in `red_team/`):
1. **`adversarial/`** — the research-grade §16–§23 Red⇄Blue self-play engagement (wired to V2 via
   `common/oracle.py` → `RedTeamTarget`).
2. **`crucible/`** — a SEPARATE Union Bank evolution project (own CLAUDE.md; deterministic blue
   clone; opt-in V2 bridge `sandbox/v2_target.py`). Left mostly untouched on purpose.
3. **`engine/`** — legacy, no Blue coupling.

### Mutation / Evolution engine
- Warm-started **GA** (`evolutionary_engine/engine.py`): seeds per-agent + curated combos; fitness =
  0.55 evade + 0.25 stealth − 0.15 distortion − 0.05 complexity; deterministic via blake2b
  `stable_seed` (reproducible ASR); expectation eval over `eval_samples` realizations.
- **MAP-Elites quality-diversity** (`quality_diversity/map_elites.py`) — kills mode collapse;
  descriptors = fragmentation × distortion (30-cell grid); found 12 distinct evading families vs
  scalar GA's 5.
- **PPO** (`rl_agent/`) — pure-NumPy actor-critic over a sequential one-edit-at-a-time MDP; hits the
  same ASR band (.44–.67) as GA by a different search.
- **GraphGAN surrogate** (`graph_gan/`) — pure-NumPy verdict surrogate (MAE 0.033, flag-acc 99.7%);
  static surrogate → Goodhart; the real re-distillation GAN loop closes the gap.

### Attack library (agents.py — 11 agents)
feature_mimicry (B8), amount_dither (smurfing), temporal_spread, relay_insertion, decoy_edges,
sink_funnel, **cross_component_split (B1 — in every winning family)**, volume_dilution,
profile_mimicry, account_takeover, conduit_split (mule mesh).

### The engagement arc (§16–§22) — the headline result
Every attack found the defender's next missing **CONTEXT** capability; every counter supplied it.
Five orthogonal context signals each forced by a probe and built in `common/`:
- **provenance** (`provenance.py`) — KYC identity; benign FP 43.8% → 0% AND fraud still 9/9, ASR → 0
  (first DEPLOYABLE hardener). Defeated by **account_takeover**.
- **behavioural** (`behavioral.py`) — each account vs its OWN baseline; closes household/retail
  takeover. Defeated by corporate/SME takeover + **conduit_split mesh**.
- **coordination** (`coordination.py`) — operation-level (linked component set): hub-less +
  consumer-heavy + fragmented = the mesh signal (closes B1 mesh).
- **relationship** (`relationships.py`) — shared-history circles; closes corporate seizure + mesh
  per-component. Defeated by **relationship-seasoning**.
- **relationship-maturity** — charges each pair's flow against THAT pair's purchased history →
  attacker must pre-move legit value ∝ laundering a year ahead → **arms race ends in ECONOMICS**.
- **Capstone (`final_stack.py`):** the composed stack drives the full adversary to **0.00 ASR at 0%
  FP** on construction-honest corpora. **Root insight: V2 scores a CONTEXT-FREE SNAPSHOT; the
  highest-value Blue investment is MEMORY/context, not better structural detectors.**

### Learning / approval process (governance)
- The interactive panel (`backend/api/redteam.py` + `frontend/.../RedTeamPanel.tsx`) is a
  **human-gated review queue**: each candidate is garbage / blue-catches / blue-missed.
  **Rule (Jay):** NEVER train Blue on data it already catches — only on Blue-missed evasions; a
  pattern Blue recognizes means RED must improve.
- `backend/adversarial_governance/store.py` — investigator-gated TrainingQueue; `learn` is the only
  door into the Blue knowledge base; deduped by signature; immutable audit.
- **blue_team_v2 is stateless at runtime — never mutated/persisted.** The only auto-hardening is the
  OFFLINE self_play CLI, NOT wired into the running backend.
- HardenedBlueTeam (`adversarial/integration/`) wraps the real engine + the context signals, emits
  the V1 schema; opt-in/manual, not wired into the API by default.

### Current status / Future
- §16–§23 complete + deployable integration + local UI panel + escalating attacks + PPO + GraphGAN.
- **NOT committed.** Open threads: harden coordination linkage model; calibrate maturity on real
  dists; strip B5 label leak from eval; V1 secondary target; real RL retraining (overlaps the
  knowledge-layer gated learning loop).

---

# Section 7 — Fraud DNA Memory

- **Purpose:** behavioural fingerprinting — a per-case "DNA" enabling similarity, families, trends.
- **DNA generation:** `fraud_dna/engine.py::build_genes(case)` → **8 genes** (Velocity, Amount,
  Structure, Behavior, Temporal, Flow, Risk, Outcome), each 0–100 + label + features. DNA id
  `FDNA-<TYPE>-<NNN>` (deterministic from case_id+category; TYPE ∈ MULE/RING/LAYER/ATO/RAPID/NET/
  CHAIN).
- **Feature extraction:** pulls the primary account from `auth.accounts_db.registry` for richer gene
  features; reads cases via `case_store.all()`.
- **Similarity scoring:** weighted-cosine over the 8 genes; `risk_impact`; `explain()`.
- **Fraud families:** the TYPE codes; trends/high-risk/emerging surfaced via `/api/dna/trends`,
  `/high-risk`, `/similar/{case_id}`.
- **UB explanation:** `fraud_dna/ub_client.py` (httpx → Ollama `llama3.1:8b`); `GET
  /api/dna/explain/{case_id}` returns `{explanation, source:"ub"|"heuristic", model}`; graceful
  heuristic fallback when Ollama down.
- **Persistence:** `_data/dna.json` with version history (DNA evolution).
- **Current implementation:** backend fully built + mounted `/api/dna`. **NOTE: the Fraud DNA
  FRONTEND feature was REMOVED 2026-06-27** (panel + pages + nav). Backend `fraud_dna` still feeds
  the `dna` recovery factor and bakes into cases (CaseDetailPage Fraud DNA tab).
- **Files:** `fraud_dna/{engine,store,ub_client,router}.py`. (Old frontend `src/dna/*` + DnaRadar +
  FraudDnaPanel + DnaExplorerPage existed; mostly orphaned now.)
- **Future:** richer gene set from real KYC; live DNA-evolution timeline; re-expose frontend if Jay
  asks.

---

# Section 8 — Recovery Engine Memory

`backend/recovery/` — TGIE's "can we still recover the money?" module. Turns detection into
**recovery intelligence**.

### Recovery logic (RIE 2.0, conservation-correct)
- Single primitive `fund_state(case)` builds a flow-of-funds: per-account
  `net_balance = max(0, traceable_incoming − outgoing)`; a CASH/ATM/withdrawal inflow does NOT
  credit the recipient (money left the network).
- Headline quantities: `originated` (Σ source/victim outflow — NOT Σ all txns, which triple-counted
  layering hops), `in_network` (Σ net balances = real recoverable), `cashed_out`, `exited`.
- `fraud_amount = originated`; **`estimated_loss = originated − likely_recoverable`** (NET, not
  gross); recoverable = actual sitting balances (no magic coefficients).
- Validation: `insufficient_evidence` + `evidence_message` (refuses to invent when no flow).
- Outputs: `reasons[]`, `obstacles[]`, `traceability[]` (per-account in/out/balance/status), 
  `recovery_paths[]` (ranked routes to sitting money), `flow{}`, funnel
  (fraud→traceable→recoverable→likely), ranked `actions` (expected_recovery_increase),
  `critical_accounts`, `kill_node`, `decay_curve`, `window`.

### 10-factor recoverability scorer (`engine.py`)
Weights sum 1.0 (higher = better recovery): age .16, depth .11, dispersion .09,
**withdrawal .22 (heaviest)**, freeze .09, containment .07, dna .06, timeline .04, beneficiary .08,
disruption .08. → recovery_probability 0–100 + band + confidence.

### Age decay (deliberate design)
Heavy-tailed **rational** curve `100/(1+(h/48)^0.52)` (NOT exponential — exp collapsed the
weeks-long tail to 0). Anchors: 5min ≈ 96, 2h ≈ 83, 2d ≈ 50, 30d ≈ 19. Window = time until
`decay × still_in` hits floor 30 (seed cases 3–11 days old → some windows legitimately closed).

### Freeze recommendations / actions
`accounts_to_freeze`, `critical_accounts`, profile-aware containment (`_profile_recovery_action`:
corporate → freeze settlement + trace shell chain; retail → freeze receiving mule; sme → vendor
chain). Simulator: `simulate(freeze | no_action | delay)`.

### Dependencies
Reuses `auth`, integrates `fraud_dna` similarity (dna factor), `ub_client.py` (Ollama explain +
heuristic fallback). All tunables centralized in a `CONFIG` dict. Mounted `/api/recovery/*`.

### Known issues / honesty
- Engine never invents: there is NO "frozen funds" figure → surface "Held in-network" =
  `funnel.recoverable`; there is NO clock-time forensic event timeline → use the decay curve.
- **Files:** `recovery/{engine,store,ub_client,router}.py`; frontend `recovery/api.ts` +
  `recovery/redesign/{primitives,sections}.tsx` + `pages/{RecoveryPage,RecoveryDashboardPage}.tsx`.
  Recovery surfaces use **CREAM/ivory accent** (not gold) per the premium UI redesign.
- **Routing:** `/recovery` = portfolio view (dashboard totals + ranked clickable case table);
  `/recovery/:caseId` = detail (hero → funds snapshot → flow → accounts → strategy → timeline →
  collapsed "Deeper analysis": Why + Simulate + Ask UB). Orphaned post-redesign:
  RecoveryGauge/RecoveryClock/DecisionCenter/CriticalAccountCenter.
- **Future:** real KYC-driven freeze status; richer forensic timeline once an event store exists.

---

# Section 9 — Blockchain Layer (BELS)

`~/Desktop/TGIE/bels`, FastAPI on **:8200** (dashboard at `/`). Run: `python3 -m bels.main` (from
`~/Desktop/TGIE`) or `bels/run.sh`.

### Core design
**Files are NEVER stored on-chain** — only SHA-256 hash + ids + metadata digest + Ed25519 signature
+ custody events. Raw files live off-chain in `~/Desktop/TGIE/evidence_storage/` (content-addressed,
IPFS/S3-swappable).

### Evidence creation / hashing / upload
Complaint → upload file (off-chain, content-addressed) → compute SHA-256 → register on chain. In
the case path, `case_management/store.anchor_blockchain()` hashes 6 components (graph / transactions
/ fraud_dna / recovery / accounts / evidence) → canonical manifest SHA-256 → BELS `/evidence/register`
+ `/verify-hash` + `/certificate`, with **internal SHA-256 fallback when BELS is down**.

### Verification process (tamper-evident)
`verify_integrity()` pinpoints the broken block. Editing a case after anchoring flips
verified→False / tampered→True (confirmed). On-disk ledger corruption is caught.

### Storage structure
`bels/data/ledger.jsonl` — a REAL hash-linked, Merkle-root, proof-of-work ledger; zero external
deps. Evidence files in `evidence_storage/`.

### Blockchain abstraction (the migration seam)
`BlockchainProvider` interface. Default = `InternalChainProvider` (PoW). `EthereumProvider` is a stub
adapter. Migrating to a bank/RBI EVM chain = deploy `smart_contracts/EvidenceRegistry.sol` + set
`BELS_PROVIDER=ethereum` + RPC/contract/key env vars — **no app code changes**.

### RBAC / modules / status
Roles: admin / investigator / auditor / compliance / viewer. Modules: blockchain_ledger,
evidence_storage, chain_of_custody, verification_engine, smart_contracts (Solidity + 1:1 Python
mirror), reporting (PDF via reportlab + JSON/CSV), ub_integration (forensic NL Q&A), service.py
(orchestrator), api.py (26 routes), demo.py. **Verified end-to-end; NOT committed.**

### TGIE integration
`from bels.api import router; app.include_router(router, prefix="/bels")` OR the standalone service
(no `/bels` prefix) reached by `case_management/bels_client.py` via `BELS_URL`
(default `http://127.0.0.1:8200`).

### Future bank-blockchain plan
Swap provider to a bank/RBI consortium EVM chain via the `BlockchainProvider` seam; the Solidity
`EvidenceRegistry` is ready; only env + contract deploy needed.

---

# Section 10 — UB Assistant (Universal Brain)

`~/Desktop/TGIE/ub` — a **100% local** Ollama RAG cognitive layer. Runs standalone on **:8001**
(`python -m ub_service`). Explains/presents the entire platform from the actual indexed code +
vetted Q&A.

### Architecture
Frontend/CLI → FastAPI `/ub/*` (`backend/ub_service/app.py`) → `UBBrain` (`ai_core/ub_brain.py`) →
Knowledge Engine (RAG, `knowledge_engine/`) → numpy `VectorStore` → Ollama → `llama3.1:8b`. Pure
stdlib + numpy, no heavy deps, no fine-tuning.

### Ollama integration / model
- Hardware (this Mac): Apple **M5**, 10 CPU, 8 GPU, **16 GB** unified. 70B won't fit.
- **Primary brain = `llama3.1:8b`** (~20 tok/s); fast fallback `llama3.2:3b` (~47 tok/s);
  embeddings `nomic-embed-text` (768-dim). Ollama at `~/.local/bin/ollama`, port 11434.
- `ollama_service/client.py` = stdlib HTTP client (chat/stream/embed/health/benchmark/switch).

### Knowledge index (RAG)
`knowledge_engine/{indexer,engine,vector_store,summarizer}.py` — scans/chunks the workspace (skips
deps), embeds (truncates chunks to 6000 chars, skips embed failures), numpy cosine retrieval
persisted to `index/` (vectors.npy + chunks.jsonl + meta.json). Index ~842 files / ~4,336 chunks.

### Curated-Q&A grounding (the main accuracy lever)
`ub_brain.py` loads `data/judge_questions.json` at init and injects token-overlap-matched vetted Q&A
as an authoritative grounding block on every retrieval turn ("VERIFIED PROJECT ANSWERS — prefer
these over raw code if they conflict"). **113 vetted Q&A across 25+ categories**, honest about limits
(56.7% FP, 55/100 readiness, untrained GNN, B5 leak). Changing Q&A needs only a UB **service
restart**; changing knowledge DOCS/code needs a full `python -m ub index` (~250s).

### Persona / modes / wake word / conversation
- **Union Bank AI Investigation Assistant** persona (calm, concise, respectful senior officer).
  `BASE_CONTRACT` defines identity/tone/etiquette/grounding/honesty/banking-domain knowledge.
  Anti-hallucination uses the exact line *"That capability is not currently implemented in this
  prototype."*
- 6 personas in `modes.py`: chat / founder / developer / presentation / demo / judge + a
  CONVERSATION reception persona for small-talk (`is_smalltalk` classifier, k=0 retrieval).
- **Dynamic greetings:** `_runtime_context()` + `_greeting_word(hour)` inject CURRENT LOCAL TIME +
  correct greeting into EVERY prompt (the model has no clock). NEVER put a real example name in the
  prompt (it once parroted "Mr. Abhinav" to un-introduced visitors) — only use a name once actually
  stated this conversation.
- **Voice orb:** the in-frontend orb calls the brain for free-form questions (`services/ubBrain.ts`
  → POST `/ub/chat`); spoken text is sanitized (strips citations/bullets) so TTS sounds natural;
  built-in command intents handled locally/instantly. Voice = browser `SpeechSynthesis` (ElevenLabs
  removed); auto-mic wake-word with first-gesture grant.

### Available commands / endpoints
`backend/ub_service/app.py`: POST `/ub/{chat,chat/stream,founder,developer,presentation,judge,demo,
reindex,model}`; GET `/ub/{health,model,context,modes,sources}`. `auto_refresh` from env
`UB_AUTO_REFRESH` (default OFF so a demo question never blocks on reindex). Frontend reaches it via
the Vite `/ub` proxy → :8001.

### Presentation / demo mode
`DEMO_OUTLINE` = 8 sections (incl. investigation, cross-product, recovery). `python -m ub demo`.

### Files / docs
`ub/{ollama_service,knowledge_engine,ai_core}/*`, `ub/cli.py`, `ub/data/judge_questions.json`;
docs `docs/UB_*.md`, `frontend/ub_dashboard/index.html` (matte-black console at
`/ub_dashboard/index.html`).

### Run gotchas
Use the venv interpreter `~/transaction-graph-intelligence/backend/.venv/bin/python` (has numpy/
fastapi; local Python 3.14 can't build scipy). Start Ollama as a **persistent foreground bg-task**
(`exec ollama serve`) — `nohup &` gets reaped when the launching shell exits.

### Future
Deeper retrieval; case-scoped Q&A; richer evidence citations in voice answers.

---

# Section 11 — Frontend Memory

Vite + React + TypeScript SPA (NOT Next.js). React Router shell. `tsconfig` `strict:false`. Edit the
**live tree** `~/Desktop/TGIE/frontend` only. `npm run dev` → :3000.

### Routing (`main.tsx`)
`/login` (+ `/register`) are the ONLY public routes; everything else is wrapped in
`<ProtectedRoute><AppLayout/></ProtectedRoute>`. Routes: `/dashboard`, `/search`, `/accounts/:n`,
`/graph` (default; `/`, `*` redirect here), `/investigations`, `/investigations/:caseId`,
`/investigations/:caseId/graph`, `/dna` (orphaned), `/recovery`, `/recovery/:caseId`,
`/admin/risk-policy`.

For each page: **Purpose · Components · State · API · Dependencies**

- **LoginPage** — secure entry; IntelligenceParticleEngine canvas background (gold nodes, money
  pulses, reacts to `tgie:excite`/`tgie:activate`); cream card + GREEN sign-in button. API:
  `/api/auth/login`. State: AuthContext (localStorage tokens, 30min idle-logout, silent refresh).
- **RegisterPage** — self-registration (name, investigator_id, employee_id, department, role,
  branch, email, password). API: `/api/auth/register` (auto-logs-in). Directory starts EMPTY.
- **DashboardPage** (in nav) — case-stats KPIs + Recent Cases (demo data removed; honest empty
  states). API: `/api/cases/stats`, `/api/cases`.
- **SearchResults / AccountView** — global search + account dossier (risk dial, flags, recent
  activity, network SVG, linked accounts/cases/evidence, "Launch Graph", "Open Case"). API:
  `/api/accounts/search`, `/api/accounts/{n}`, `/api/cases/by-account/{n}`.
- **GraphPage → App.tsx → GraphScene** — the live 3D graph. State: `graphStore` (Zustand) fed by
  `useGraphSocket` (WS `/ws/live`, 5-fail mock fallback). `App.tsx` holds risk intel (`ai/
  riskPropagation.ts`), tooltip, NodeInspector, UB orb (call-driven, auto-hides), unified sample
  feed (`data/sampleDataset.ts`), Pin-to-case control, localhost-only Red Team + Training panels.
  Wrapped in `translateZ(0)` + GraphErrorBoundary so a WebGL failure degrades gracefully.
- **InvestigationsPage** — KPI tiles + filter tabs + case table + global search bar (debounced →
  `/api/cases/search`); live-refreshes (focus + visibility + 12s poll). 
- **CaseDetailPage** (`/investigations/:caseId`) — **9 tabs**: Transactions, Accounts (roles table),
  Recovery (baked), Fraud DNA (baked + FraudDnaPanel), Evidence (multipart upload + download +
  verify), Blockchain (anchor/verify/receipt), Timeline, Notes, Reports (PDF/DOCX/JSON + Case Bundle
  ZIP). Plus RiskSummary card, collaboration panels, "Open verbatim graph".
- **CaseGraphPage** (`/investigations/:caseId/graph`) — GraphScene in restore mode (pinned positions
  + captured camera).
- **RecoveryDashboardPage / RecoveryPage** — see §8 (cream accent, premium/minimal).
- **RiskPolicyPage** (`/admin/risk-policy`) — edit thresholds/weights/velocity/suppression
  (manager/admin only). API: `/api/risk/config`.

### Cross-cutting frontend rules
- **Premium UI bar (standing):** every screen must read like "software a national bank paid millions
  for" — minimal, quiet, enterprise. REJECTED: cyberpunk/neon/glow/gradients/particle backgrounds/
  giant numbers/widget-soup/fake metrics. Matte-black/graphite canvas; warm accent ONLY for brand +
  primary action (gold globally, **cream on recovery**); color ONLY for meaning (green=recoverable/
  high, amber=medium, red=critical, blue=info); status never color-only; one focal number per view;
  8px grid; soft shadows; 1px borders; thin lucide icons; subtle motion only.
- **Percentage discipline:** `utils/percent.ts` is the ONLY formatter — `pctFraction`/`pctValue`/
  `riskPct`/`riskValue`; renders N/A (never clamps).
- **Vite proxy:** `/api`→:8000, `/ub`→:8001; `/graph` route is SPA-served (`/graph/clear` is the only
  backend graph route the client POSTs). `App.tsx` root uses `100%/100%` (not vw/vh) so the graph
  embeds under the 64px navbar.

---

# Section 12 — API Inventory

> All backend routes (live). Request/response detail given where non-obvious. Most `/api/graph/*`
> routes are **session-scoped via `X-Session-Id`** and computed off the event loop. Auth-protected
> routes need `Authorization: Bearer <access>`.

### Ingestion + graph (routes.py)
- `POST /transaction/manual` — body: legacy list `[{from_account,to_account,amount,payment_rail,
  timestamp, …optional enrichment}]` OR v2.0 `TransactionEnvelope`. Returns `{schema_version,
  profiles_supplied, warnings}`. Side effects: builds graph, detects, scores, may auto-open a case,
  broadcasts. THE core ingress.
- `POST /graph/clear` — reset session graph + entity_context + account_intel.
- `GET /api/graph/state` · `/stats` · `/communities` · `/cycles` · `/node/{id}` · `/node/{id}/edges`
  · `/node/{id}/intelligence` · `/traverse/bfs/{id}` · `/traverse/dfs/{id}` · `/path/{src}/{tgt}` ·
  `/trace/{id}`.
- `GET /api/graph/layout?mode=` (mode=auto default) · `/analytics?top=` · `/paths/{src}/{tgt}` ·
  `/motifs?graph_id=` · `/case-summary?graph_id=` · `/community-intelligence?top=` ·
  `/timeline?bucket_minutes=` · `/flow-narrative?max_routes=`.
- `GET /api/graph/cross-product` · `/customer-risk` · `/customer-investigation/{account_id}`.
- `GET /api/rules` · `GET /api/knowledge` · `/scenarios` · `/scenarios/{name}` · `/red-team-eval` ·
  `/learning` · `/learning/propose` · `POST /api/knowledge/learning/apply {threshold,value}`.
- `POST /api/simulation/control` · `GET /api/stats` · `GET /health`.

### Auth / accounts / investigator (auth/router.py)
- `POST /api/auth/{login,logout,refresh,register}` · `GET /api/auth/{me,roles}`.
- `GET /api/accounts/search?q=` · `GET /api/accounts/{number}`.
- `GET /api/investigator/{profile,activity,avatars}` · `POST /api/investigator/avatar {avatar}`.

### Risk (risk_engine/router.py)
- `POST /api/risk/assess` (component → 0–100 assessment) · `GET /api/risk/classify` ·
  `GET/PUT /api/risk/config` · `POST /api/risk/config/reset`.

### Cases + collaboration (case_management/router.py — 40 routes)
- `GET /api/cases?scope=open|closed|critical|assigned|available|mine` · `/stats` · `/notifications`
  · `/search?q=` · `/by-account/{n}` · `/me/capabilities` · `/my/dashboard` · `/ops/metrics` ·
  `/ops/workload`.
- `POST /api/cases/create` · `GET/PUT /api/cases/{id}` · `GET /{id}/timeline` · `/{id}/activity`.
- `POST /{id}/{notes,evidence,assign,close,claim,handover,request-approval}` ·
  `POST /{id}/evidence/upload` (multipart 50MB) · `GET /{id}/evidence/{eid}/download` · `/{id}/bundle`
  (ZIP).
- `POST /{id}/blockchain/anchor` · `GET /{id}/blockchain/{verify,receipt}`.
- `POST /{id}/graph-snapshot` (verbatim positions+camera).
- Collaboration: `GET/POST /{id}/participants` · `DELETE /{id}/participants/{inv}` ·
  `GET/POST /{id}/comments` · `PUT /{id}/comments/{cid}` · `POST /{id}/comments/{cid}/archive` ·
  `GET/POST /{id}/tasks` · `PUT /{id}/tasks/{tid}` · `POST/DELETE /{id}/lock`.

### Fraud DNA (fraud_dna/router.py)
- `POST /api/dna/{generate,compare}` · `GET /api/dna/{trends,high-risk}` · `/similar/{case_id}` ·
  `/case/{case_id}` · `/explain/{case_id}` · `/{dna_id}`.

### Recovery (recovery/router.py)
- `POST /api/recovery/{analyze,explain}` · `GET /api/recovery/{dashboard,actions,simulation}` ·
  `/case/{case_id}`.

### Evidence (legacy + v1)
- `POST /api/evidence/generate` · `GET /api/evidence/{list,download/{filename}}`.
- `/api/v1/evidence`: `POST /build/{case_id}` · `GET /download/{pkg_id}.{json,pdf}` ·
  `/verify/{pkg_id}` · `/fiu/{case_id}`.

### Red Team (api/redteam.py — localhost/`ENABLE_REDTEAM_PANEL` only)
- `GET /attacks?seed=` · `POST /{review,reset,auto_reject,train}` ·
  `GET /training/{queue,audit,similar}` · `POST /training/{decide,reset}`.

### WebSockets
- `WS /ws/live` — graph_update / case_registered / case_event / case_presence broadcasts.
- `WS /ws` — control channel (`case:subscribe`/`unsubscribe`/`presence`).

### v1 strangler-fig
- `/api/v1/{cases,evidence,health,audit}` (json|db via `TGIE_PERSIST`); frontend uses v1-first →
  legacy fallback.

### BELS (:8200, separate service — 26 routes)
- evidence upload/register, verify-hash, certificate, custody events, reports (PDF/JSON/CSV), UB Q&A,
  ledger integrity verify. Prefix `/bels` when mounted into the backend; no prefix standalone.

---

# Section 13 — Database / Persistence Schema

TGIE's **live/demo path uses NO database** — it is in-memory NetworkX + flat JSON. A full
Neo4j+Postgres+Redis design exists as code but is **Docker-gated and OFF by default**
(`TGIE_PERSIST=json` default; `=db` flips to the repos).

### Live persistence (JSON, the running system)
| Store | File | Contents | Keys |
|---|---|---|---|
| Investigators | `backend/auth/_data/investigators.json` | hashed creds, roles, avatars, sessions | investigator_id, employee_id (unique) |
| Cases | `backend/case_management/_data/cases.json` | full case records (enriched) | `TGIE-2026-NNNN` (sequential, survives restart) |
| Case evidence files | `backend/case_management/_data/evidence/<case>/<eid>__<name>` | uploaded files | SHA-256 |
| Fraud DNA | `backend/fraud_dna/_data/dna.json` | DNA + version history | `FDNA-<TYPE>-<NNN>` |
| Risk config | `backend/risk_engine/_data/risk_config.json` | weights + thresholds | — |
| Training queue | `backend/adversarial_governance/_data/training_queue.json` | gated learning queue + audit | candidate id; signature `fraud_type|sorted(techniques)` |
| BELS ledger | `bels/data/ledger.jsonl` | PoW hash-linked blocks (Merkle root) | block_index, block_hash |
| Evidence (off-chain) | `~/Desktop/TGIE/evidence_storage/` | raw files, content-addressed | SHA-256 |
| UB index | `ub/index/{vectors.npy,chunks.jsonl,meta.json}` | RAG embeddings | — |

In-memory graph: NetworkX directed multigraph in `graph_engine/graph_manager.py`. Nodes = accounts
(+ cash sinks) with `account_type` (normal/merchant/mule/high_value/cash), `risk_score`,
`detected_patterns`. Edges = transfers with `amount`, `payment_rail`, `device_id`, `ip_address`,
`geo`. Per-session graph isolated via `X-Session-Id`; per-session `entity_context` = `{types, owns,
links}` for cross-product.

### Docker-gated enterprise schema (code written, NEVER run live → unverified)
- **Neo4j (graph truth):** `graph/schema/{labels,models,client}.py` + `constraints.cypher` +
  `bootstrap.py`. Reified `Transaction` + derived `TRANSFERRED_TO`. Wave-1 labels A/B/C/E.
- **Postgres (cases/audit/users):** `migrations/{run,transforms}.py`; `repositories/{case,user,
  event,audit}_repo.py`. Round-trips the exact 9 cases / 5 users (verified against fallback).
- **Redis (cache/queue):** `core/{cache,tasks}.py` (Redis-or-LRU `@cached`; inline-or-Celery enqueue).
- **Object store (evidence):** BELS-anchored.
- To go live: install Docker → `python3 -m graph.schema.bootstrap` + `python3 -m migrations.run
  --all` → flip `TGIE_PERSIST=db`.

### Caching
`core/cache.py` (`@cached`, Redis or in-process LRU; verified 1233× cold→warm speedup no-Docker).
NetworkX graph is the hot cache / live-demo projection of the (future) Neo4j truth.

---

# Section 14 — Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `TGIE_PERSIST` | `json` | `json` (flat-file, live default) or `db` (Postgres/Neo4j repos) |
| `TGIE_PYTHON` | venv path below | interpreter for control scripts |
| `TGIE_MOUNT_UB` | OFF | mount UB inside backend (now UB runs standalone :8001) |
| `TGIE_AUTH_SECRET` | stable local fallback | JWT signing secret (HS256) |
| `TGIE_AUTH_STORE` | `auth/_data/investigators.json` | investigator directory path |
| `TGIE_RISK_INVESTIGATION_THRESHOLD` | 70 | score at which a case auto-opens |
| `TGIE_RISK_CRITICAL` | 85 | critical tier |
| `TGIE_AUTOREG_RISK` | 0.5 | legacy auto-register gate (superseded by should_create_case) |
| `TGIE_EVIDENCE_DIR` | `case_management/_data/evidence` | case evidence file dir |
| `TGIE_TRAINING_STORE` | `adversarial_governance/_data/training_queue.json` | gated learning store |
| `ACTIVE_BLUE_TEAM` | (code default V2) | `v1`/`1`/`blue_team` → retired V1; anything else → V2 |
| `ADV_TARGET_ENGINE` | `v2` | adversarial oracle target |
| `ENABLE_REDTEAM_PANEL` | OFF | expose `/api/redteam/*` (localhost only; never on deploy) |
| `CRUCIBLE_BLUE_TEAM` | (MockBlueTeam) | `v2` → V2BlueTeam bridge; `BLUE_TEAM_URL` → legacy HTTP |
| `CRUCIBLE_V2_BACKEND` | auto-locate | path override for crucible→V2 bridge |
| `BELS_URL` | `http://127.0.0.1:8200` | case_management → BELS service |
| `BELS_PROVIDER` | `internal` | `internal` PoW or `ethereum` (+ RPC/contract/key vars) |
| `TGIE_OLLAMA_URL` | `http://localhost:11434` | Ollama endpoint (fraud_dna/recovery/UB) |
| `TGIE_UB_MODEL` | `llama3.1:8b` | LLM model id |
| `UB_PORT` | 8001 | UB standalone port |
| `UB_AUTO_REFRESH` | OFF (`0`) | re-index staleness check (kept OFF so demos don't block) |
| `PYTHONHASHSEED` | — | set for Red Team reproducibility (hash-seed nondeterminism) |
| **Deployment (Railway)** | | |
| `DEBUG` | false | |
| `GRAPH_MAX_NODES` / `GRAPH_MAX_EDGES` | 150 / 600 | RAM drivers (prod-reduced from 500/2000) |
| `ANOMALY_SCORE_THRESHOLD` | 0.65 | |
| `BLUE_TEAM_API_KEY` | `tgie-secret-2025` | static (a known prod blocker) |
| `ALLOWED_ORIGINS` | `*` | **must be a str, not List[str]** (pydantic-settings json.loads gotcha) |
| **Frontend (Vercel)** | | |
| `VITE_API_URL` | Railway URL | backend base for the deployed SPA |

---

# Section 15 — Startup Process

**Preferred (manual control suite):** double-click `~/Desktop/TGIE/control/start_tgie.command`
(ordered: Ollama → wait healthy → UB → Backend → Frontend → open browser). `TGIE_NO_OPEN=1` skips
the browser. Writes PID files to `control/pids/`.

**Manual / dev steps:**
1. **Ollama** — `exec ollama serve` (persistent foreground bg-task; `:11434`). Models:
   `ollama pull llama3.1:8b nomic-embed-text`.
2. **UB** — from `~/Desktop/TGIE`: `<venv-py> -m ub_service` (`UB_PORT=8001`). Index must exist
   (`python -m ub index` once, ~250s).
3. **Backend** — from `~/Desktop/TGIE/backend`: `PYTHONPATH=. <python> -m uvicorn main:app
   --port 8000 --log-level info` (runs WITHOUT `--reload`; new modules need a restart). Interpreter:
   the live backend uses **system Python 3.14**; the venv `~/transaction-graph-intelligence/backend/
   .venv/bin/python` is used for UB/scripts (3.14 can't build scipy). Ensure `python-multipart` is
   installed in whichever interpreter runs the backend.
4. **BELS** (optional, for evidence anchoring) — from `~/Desktop/TGIE`: `python3 -m bels.main`
   (`:8200`) or `bels/run.sh`.
5. **Frontend** — from `~/Desktop/TGIE/frontend`: `npm run dev` (`:3000`; falls back to :3001 if
   taken). Vite proxies `/api`→:8000, `/ub`→:8001.
6. **Browser** — open `http://localhost:3000`.

**Investigator workflow (typical):**
Register/login (`/register` → tokens in localStorage `tgie.access`/`tgie.refresh`) → `/graph` →
Generate Sample (or submit transactions) → Blue Team V2 + risk_engine score → fraud auto-opens a
`TGIE-2026-NNNN` case → open Investigations → review Recovery / Fraud DNA / Accounts (roles) →
upload evidence → anchor to blockchain → export bundle/report → ask UB (voice or dashboard).

**To screenshot the authed app headlessly:** POST `/api/auth/register` (needs investigator_id,
password, name, employee_id, department, role, branch, email) → inject the returned `access` token
into localStorage `tgie.access` → goto the route.

---

# Section 16 — Stop Process

**Preferred:** `~/Desktop/TGIE/control/stop_tgie.command` — graceful SIGTERM (pidfile pid + port
listener + children via `pkill -P`) then SIGKILL; scoped orphan sweep; verifies ports free; removes
pidfiles. `restart_tgie.command` = stop then start. `status_tgie.command` shows per-component
running/stopped + port + PID + memory + ollama models + UB index size.

**Manual:** find the process owning each port and SIGTERM it. **Gotcha:** `lsof -ti:8000` ALSO
matches Vite's proxy connection — killing by it drops the frontend too. **Kill the uvicorn task
directly**, not by port. Order to stop: Frontend → Backend → BELS → UB → Ollama. Workers/schedulers/
WebSockets: none run as separate daemons in the live path (Celery/Kafka are Docker-gated and OFF;
the WS broadcaster is in-process and dies with uvicorn).

**Auto-start:** disabled. The only auto-start ever found was Ollama (`com.ollama.ollama` via
SMAppService) — disabled with `launchctl disable gui/$(id -u)/com.ollama.ollama` + `bootout`.
Opening Ollama.app may re-register it → re-run disable or toggle off in System Settings → Login Items.

---

# Section 17 — Design Decisions

- **Two-scorer split (risk_engine decides, V2 advises):** keeps the case decision explainable,
  bounded (0–100), and engine-swap-independent. Consumers read only the shared verdict keys.
  *Trade-off (known debt):* V2's rich evidence is discarded for the decision (§18).
- **risk_score wire = 0–1 fraction:** preserves the long-standing frontend contract; prevents the
  "FRAUD 1000%" bug. The 0–100 value + explainability ride alongside (`risk_points`, etc.).
- **Profile-relative amount:** ₹25L means different things to a salaried employee vs a business
  owner; absolute thresholds create false positives. Profile Intelligence is integrated INTO
  risk_engine, not a parallel scorer.
- **react-force-graph-3d (default) over Cytoscape:** the 3D scene shows multi-component separation
  and is the look Jay wants. A Cytoscape "workstation" was built then DELETED. The backend layout
  engine IS consumed (App.tsx fetches `?mode=auto` → structural targets) but ring components keep the
  local interior-safe seed so a flat backend layout can't route an edge through a laundering circle.
- **Decentralized cluster forces (no center):** Jay rejected solar-system hierarchy where the
  heaviest hub parks at origin. Each component gets an evenly-distributed home direction.
- **Converge→freeze lifecycle + topology-only reheat:** the Railway backend re-broadcasts every ~1s;
  without this the graph never cools ("vibration tail"). structFloor lowered 0.34→0.06.
- **Ollama / local LLM (UB):** 100% local, no cloud, no data egress — required for a bank; no
  fine-tuning (persona + RAG + curated-Q&A grounding instead).
- **Curated-Q&A grounding outranks raw code retrieval:** stops UB hallucinating under
  cross-questioning (raw retrieval once gave a wrong "Red auto-trains Blue" answer).
- **Blockchain evidence (BELS) with provider abstraction:** proves existence/integrity/custody;
  internal PoW now, bank/RBI EVM chain later via the seam; files NEVER on-chain.
- **Red Team requires investigator approval; Red never auto-trains Blue:** the learning gate is a
  core principle. blue_team_v2 is stateless at runtime; only investigator-approved Blue-missed
  evasions enter the knowledge base.
- **Recovery as net-loss, conservation-correct:** never invent figures; `estimated_loss = originated
  − recoverable`; rational age-decay (not exponential).
- **One fraud = one permanent case, everything baked in at creation:** nothing recalculated on open;
  verbatim graph snapshot; dedup by account set.
- **JSON-first, Docker-gated DB:** runs anywhere with graceful degradation; strangler-fig migration.
- **Premium/minimal UI bar:** the product must earn institutional trust; no cyberpunk/neon/fake
  metrics.
- **Deployment reductions (main → production branch):** removed Kafka/GNN/retrain-loop; reduced graph
  size/buffers; `ALLOWED_ORIGINS` as str (pydantic gotcha); CORS credentials false with `*`; vite
  manualChunks removed (three.js TDZ crash). Never merge production → main.

---

# Section 18 — Known Bugs & Technical Debt

**Critical (open):**
1. **risk_engine false-negatives:** double-diamond ₹9L and 7/11 fraud archetypes score <70 → NO
   case. Fix = wire V2 evidence into `assess` + add a reconvergence factor + recalibrate the
   threshold + fix narrow-fan scoring. (THE most important detection bug.)
2. **V2 false-positives:** 56.7% FP on realistic legit traffic (payroll 100%, corporate 85%). No
   legitimacy model. Currently hidden because risk_engine suppresses them. Fix needs context signals
   (provenance/behavioural/relationship/coordination — proven by Red Team).
3. **B1 component isolation:** no cross-component/cross-session correlation → meshed/partitioned
   laundering is invisible. Highest-value architectural fix.

**High:**
4. **Untrained GNN (B4):** `ml/gnn_model.py` has random weights (`_is_trained` never set) — its
   outputs are noise. ML ensemble is NOT wired into risk_engine (designed as capped factor weight-0).
5. **B5 label leak:** IsolationForest reads ground-truth `fraud_pattern` — inflates V1; strip from
   eval harness.
6. **B8 attacker-controlled attrs:** V2 trusts node `account_type`/`risk_score`/`detected_patterns`.

**Medium / latent:**
7. `/api/evidence/generate` still reads the GLOBAL graph_mgr for cash events (per-session bug;
   noted, out of scope).
8. `case_management` runs on **system Python 3.14** without `--reload` → restarts required; a missing
   `python-multipart` once silently 404'd the whole `/api/cases` router (now guarded to 503).
9. Don't edit `cases.json` while the backend runs — the in-memory store re-saves over it.
10. Client-side risk calculators (`ai/riskPropagation.ts`, `graphClassifier.ts`, `riskModel.ts`,
    `graphAnalysis.ts`) still run in React (Phase-2 "no risk calc in React" not fully met). Backend
    has equivalents (`v2.node_intelligence`, evidence) but blind removal breaks live graph coloring.
11. Graph rhombus/distortion: GraphScene WebGL drawing-buffer aspect ≠ CSS-box aspect (worst after
    rotation). Fix = ResizeObserver + clamp devicePixelRatio (documented in
    `docs/graph_validation.md`).
12. `/api/graph/layout?mode=auto`: `App.tsx` still fetches it and passes `backendLayout` to
    `GraphScene`, BUT as of the 2026-07-01 unification GraphScene IGNORES it for the live scene
    (`LIVE_USES_BACKEND_LAYOUT=false`) — the frontend motif seed is the single source of truth.
    The endpoint remains the authority for evidence/SSR/the API. NOT dead code; do not flag it.
    (History: it was briefly the live override, which caused the ring-interior stab; now demoted.)

### Ring edge-routing fix (2026-06-30) — branches must never cut through a laundering ring
**Symptom:** a circular ring (e.g. `ROUND_A→…→ROUND_F→ROUND_A`) with an exit branch
(`ROUND_C→CIR_LAYER_001→CIR_LAYER_002→CIR_CASHOUT`) was drawn with the branch slicing straight
through the ring interior. **Root cause (proven, not the frontend seed — that was already correct):
`backend/graph_engine/layout.py::_circularize_cycles` relocated only the cycle nodes onto a ring
but left the branch nodes on the global L→R fund-flow axis, so the connecting edge stabbed the
interior (minDist 63 < R 92). The live app renders these backend coords (see item 12).** Fix, all
additive/deterministic:
- `layout.py`: `_circularize_cycles` now ORIENTS each ring so its external-connection ("gateway")
  nodes face their neighbours' direction; new `_resolve_ring_branches` fans every spur/cash-out
  radially OUTWARD from its anchor ring node (multi-source BFS for anchor+hop), mirroring the
  frontend embedded-ring algorithm; new exported `ring_geometry()`.
- `layout_quality.py`: ring interiors are a PROTECTED no-crossing zone — `detect_ring_interior_
  crossings()` + `repair_ring_crossings()` (push offending non-member endpoint outward; radial
  through the member endpoint when one end is on the ring), wired into `compute_layout`'s
  validate→repair; `assess_quality(rings=…)` reports `ring_interior_crossings` (optional arg →
  backward compatible).
- `graphLayout.ts`: `ComponentLayout.containsRing` flag (set on pure-cycle + embedded-ring paths).
- `GraphScene.tsx`: for `containsRing` components, skip the backend override and keep the local
  interior-safe seed (belt-and-suspenders so a bad server layout can never re-introduce the stab).
- Tests: `backend/tests/test_ring_layout.py` (11) — pure ring, ring+exit (the reported dataset),
  multi-exit, entry, two connected rings, ring+diamond, ring+cash-out, large hybrid, determinism,
  detector sanity. **Backend 260 pass; tsc clean.** NOT committed.

### Fan-out edge-routing fix (2026-07-01) — wide fan-outs with tails must read as a radial fan
**Symptom:** a wide fan-out where some children carry their own branch (e.g. `SOURCE_MAIN → 6
smurfs`, with `SMURF_003→FANOUT_EXIT_001`, `SMURF_004→FANOUT_EXIT_002`) rendered chaotically — the
branch-bearing children got flung to the extremes ("one smurf shoots sideways"), source→child
distances ranged 107–241 (spread 0.82), and the fan stopped reading as a fan. **Root cause (proven
on BOTH engines):** the pure 2-layer fan path (`placeFan` arc / backend column) only fires for a
*pure* fan; the moment a child has a tail the graph is 3+ layers and falls into generic Sugiyama,
which barycenter-pushes branch-bearing children to the edges. Fix = a dedicated **radial fan-out
motif** for a *wide rooted arborescence* (one source hub, every other node indeg 1, hub
out-degree ≥ 4, with downstream tails):
- `graphLayout.ts`: `placeRadialFan` — hub at centre, direct children on a full circle at even
  angular spacing (each gets its own outward corridor), each child's subtree fanned radially
  OUTWARD by BFS hop; detected before the Sugiyama fallback; sets `ComponentLayout.containsFan`.
- `GraphScene.tsx`: `protectedMotif = containsRing || containsFan` — fans (like rings) keep the
  local interior-safe seed instead of the backend `?mode=auto` override (which would re-flatten
  them into a column). Refine pass treats `containsFan` as radial (unlock Y).
- `layout.py`: `_radialize_fans` post-pass (parallels `_circularize_cycles`/`_resolve_ring_branches`)
  — re-lays a wide rooted fan-WITH-tails radially; **pure fans deliberately stay legible columns**
  (existing `test_fund_flow_fans_out_into_a_column` contract). Clears the "starburst" quality flag.
- Tests: `backend/tests/test_fanout_layout.py` (7) + a permanent **20-topology frontend backtest
  harness** `frontend/scripts/layout_backtest.mjs` (`node scripts/layout_backtest.mjs`, exit-code
  gate) covering pure/with-cashout/multi-cashout fans, fan-in, diamond/double-diamond, all ring
  variants, chains, two-clusters, mesh, hybrid, cash-in→cash-out, multi-hub, bridge — with metrics
  (overlap/edgeCV/crossings/fan-angle-variance/equal-radius/ring-interior/cash-out-externality/
  determinism). **Result: backend 267 pass; frontend backtest 20/20; tsc clean.** Reported dataset:
  6 children now at exactly equal radius (spread 0.00), evenly spaced, cash-out tails outward, 0
  crossings. NOT committed.

### Cash-event ontology fix (2026-07-01) — cash-in/out are events, not bank accounts
**Symptom:** a transaction `DIAMOND2_MERGE →(CASH_OUT)→ DIAMOND_CASHOUT` rendered `DIAMOND_CASHOUT`
as a normal (red, when fraud) bank account. **Root cause:** `graph_manager._update_node` classified
node type by **name prefix only** (`startswith("CASH")`), so a cash endpoint whose name isn't
`CASH*` was NORMAL. **Much of the ontology already existed** (the frontend already colors
`account_type==='cash'` emerald=cash-in / gold=cash-out with fraud as a halo-not-fill — identity
outranks fraud by design; recovery already had cash-out flow logic; `CASH_IN`/`CASH_OUT` rails are
already "first-class" connected nodes). The fix was making cash identity **rail-driven**:
- `graph_manager._update_node`: a `CASH_OUT` edge's TARGET and a `CASH_IN` edge's SOURCE are cash
  events regardless of name; sets `AccountType.CASH` + `cash_kind`; identity is **sticky** (a later
  normal edge never downgrades it). `_node_attrs`/`get_graph_state` now emit `is_cash_event`,
  `cash_kind`, `is_account`, `terminal`. `AccountNode` gained `cash_kind`.
- `recovery/engine.py`: `CASH_OUT` added to `cash_rails` → a cash-out correctly counts as exited
  funds (lowers recoverable, raises loss; the destination is not a freezable balance).
- `layout.py`: `_build_digraph` carries `account_type`/`cash_kind`; `_stage_label` returns
  `cash_in`/`cash_out` rail-driven. (Cash-out is already terminal = out_degree 0 = boundary.)
- `case_management/store.py::register_from_detection`: cash IDs derived from edges (CASH_OUT target
  / CASH_IN source) → separate `cash_events[]`, `account_count` excludes them, a cash event is never
  the primary suspect, snapshot role `cash_in`/`cash_out`. `summary` adds `cash_event_count`.
- Frontend: `types/index.ts` GraphNode gains `is_cash_event`/`cash_kind`/`is_account`/`terminal`;
  `NodeInspector` routes first-class cash nodes (`is_cash_event`/`account_type==='cash'`) to the
  `CashNodeInspector` ("Cash Withdrawal/Deposit Event", channel, "Funds exited banking system",
  source account — NOT a customer/account profile). Coloring needed NO change (already cash-aware).
- Both schemas supported: `normalize.py::_resolve_rail` maps nested `payment.rail` AND flat
  `payment_rail` → identical `CASH_OUT`. **Scoping note:** node IDs stay the literal `to_account`
  (the existing first-class design); semantic correctness comes from classification + attrs +
  styling + labeling, not synthetic IDs (avoided rippling edges/dedup/search/snapshots).
- Tests: `backend/tests/test_cash_events.py` (8 — account transfer, cash-in/out by arbitrary name,
  the reported `DIAMOND_CASHOUT`, double-diamond+cashout, multi-cashout, sticky identity, recovery
  exited-funds, case account-count excl. cash). **Backend 275 pass; tsc clean; backtest 20/20.** Not
  committed.

### Cross-Bank Intelligence module (2026-07-01) — plug-in enrichment, graph untouched
**What:** a MuleHunter-style layer answering "has this entity behaved suspiciously at OTHER
banks?" New package `backend/cross_bank_intelligence/` (9 files mirroring the spec: `schemas`,
`risk_registry`, `fingerprints`, `entity_resolution`, `external_signals`, `velocity_engine`,
`profile_correlation`, `mule_scoring`, `intelligence_engine` + `__init__`). Pure ENRICHMENT:
reads a read-only component snapshot + the per-session `entity_context`, returns intelligence ONLY
— **never creates/removes nodes or edges, never touches positions/layout/colours/physics.** The
graph engine does not know it exists.
- **Entity resolution:** Union-Find links accounts sharing a fingerprint (device/phone/PAN/UPI/
  email/KYC-name/merchant) into one real-world entity across banks.
- **Risk registry** (`risk_registry.py`): the cross-bank memory — seeded known-suspicious
  fingerprints (Kafka-fed in prod) + `register_sighting` accumulation seam. Default singleton;
  tests pass their own instance (no global-state leak).
- **Patterns:** same_device_multi_bank, same_phone_multiple_accounts, multi_bank_layering,
  multi_bank_fanout/fanin, cross_bank_circular, dormant_activation, same_merchant_across_banks,
  same_device_different_names, known_suspicious_entity. Output = the spec dict (cross_bank_risk,
  linked_banks/accounts, shared_devices/phones, known_suspicious_entities, patterns[], banks_involved,
  per-account intel).
- **Banks:** `KNOWN_BANKS` (UNION_BANK/SBI/HDFC/…); account bank from input `from_bank`/`to_bank`
  (new optional `ManualTransactionInput` fields) → `record_account(bank=)` → `entity_context["banks"]`;
  default UNION_BANK.
- **Risk integration (capped):** `risk_engine` `DEFAULT_WEIGHTS["cross_bank"]=10`; `assess()` consults
  the module as ONE factor (intensity = cross_bank_risk/100 × weight 10) — contributes but **never
  dominates** (alone can't reach the 70 case threshold; proven: structurally-trivial + known mule →
  no case). Subject to the existing FP suppression. Returns a `cross_bank` block.
- **Verdict/case/frontend:** `routes.py` attaches `comp["entity_context"]` before assess and
  `v["cross_bank"]` after; `case_management` stores a compact `case["cross_bank"]` summary
  (`_cross_bank_summary`). Frontend: `types/index.ts` CrossBankReport/CrossBankAccountIntel on
  `GraphComponentResult`; `NodeInspector` `CrossBankCard` (Banks Seen / Linked Accounts / Shared
  Devices / Cross-Bank Risk / "Known to other banks"); `CaseDetailPage` `CrossBankIndicators` block.
- **Kafka/Celery:** simulate only — registry is the Kafka seam (`register_sighting`);
  `analyze_component_async` is the Celery/threadpool offload seam (runs inline today, cheap O(nodes),
  graph never blocked). Async by design, defensive (any failure → empty report).
- Tests: `backend/tests/test_cross_bank_intelligence.py` (10 — benign-quiet, multi-bank layering,
  same-device-multi-bank, same-phone-multi-account, known-entity, same-device-diff-names, entity
  resolution, **factor capped / no case alone**, **graph snapshot untouched**, registry accumulation).
  **Backend 285 pass; tsc clean; layout backtest 20/20.** NOT committed.

### Pipeline audit + single-source-of-truth unification (2026-07-01)
**Request:** "graphs keep rendering wrong — find the architectural flaw, not another patch."
**Audit (empirical, full pipeline traced):** the DATA pipeline is correct — normalization
(`normalize.py` maps nested `payment.rail` AND flat `payment_rail`), edge direction (from→to, arrows
correct), node typing (rail-driven cash events, fixed prior turn), and motif layouts (both engines
score 0 crossings / 0 overlap on every test topology). So the recurring bugs were NOT gross math or
bad data. **ROOT CAUSE = architectural: the live 3D scene ran TWO motif-aware layout engines —
frontend `graphLayout.ts` (the seed) AND backend `layout.py` (`GET /api/graph/layout?mode=auto`) —
reconciled by a per-component `protectedMotif` override, then refined by physics. No single
authority owned the final geometry.** Rings/fans were "protected" (frontend seed won); everything
else rendered with the flat 2D backend override forced into the 3D scene. Every prior layout bug was
one engine or the handoff disagreeing (the ring-interior stab was literally the backend override).
**Fix — one source of truth:** `GraphScene.tsx` const `LIVE_USES_BACKEND_LAYOUT = false` → the
deterministic motif-aware seed is now the ONLY structural authority for every component; physics only
polishes + freezes. The backend layout engine is untouched and still serves evidence/SSR/the API —
it is just no longer injected into the live scene. One-line revert (flip the const) to A/B it. The
frontend seed is proven on all 20 topologies (incl. the ex-override motifs: diamond, double-diamond,
fan-in, multi-hub, chain, bridge), so unifying removed the fragility with zero motif regression.
**Validation gate strengthened (Phases 12/14):** `scripts/layout_backtest.mjs` now also asserts
stage/direction — in a hierarchical flow motif the source sits upstream and the terminal at the flow
extreme ("where money started / ended" is readable at a glance). **20/20 pass, tsc clean, backend
275 pass.** Architecture is now: transaction semantics → topology → motif → seed → physics-polish →
render (single authority), not two engines + override. NOT committed.

**Layout architecture (consolidated):** every component is laid out by a single MOTIF-AWARE seed
(`graphLayout.ts`, the sole authority for the live scene), then physics only refines + freezes it.
Motif precedence: pure cycle → embedded ring (cycle+spurs) → wide radial fan-out (arborescence+tails)
→ pure fan arc → chain meander → Sugiyama layered (diamonds/trees/hybrids); protected motifs
(`containsRing`/`containsFan`) additionally never accept any external override. Backend `layout.py`
mirrors the same motifs for `?mode=auto`/evidence/SSR but is NOT injected into the live 3D scene
(`LIVE_USES_BACKEND_LAYOUT=false`). Both deterministic.

**Technical debt / workarounds:**
- Nothing committed to git (Jay's choice). No frontend tests. No observability. Static
  `BLUE_TEAM_API_KEY`. No authN on the public WS/ingress (deployment blocker).
- Composite production readiness: **55/100** (advanced prototype / pre-production).

---

# Section 19 — Future Roadmap

**Critical**
- Wire Blue Team V2 evidence INTO `risk_engine.assess`; add reconvergence factor; recalibrate the 70
  threshold + narrow-fan scoring (fix the false-negative crisis).
- Build a legitimacy model (provenance + behavioural + relationship + coordination context) to fix
  the 56.7% FP — the Red Team engagement proved this is the true missing capability.
- Close B1: cross-component / cross-session correlation.

**High**
- Wire the ML ensemble into risk_engine; train the GNN; strip the B5 label leak.
- Identity-ring detectors (Wave 2: shared device/PAN/IP via `entity_context`) — needs Neo4j.
- Finish the `/api/v1` routers (graph/alerts/transactions/search/risk/dna/recovery still
  legacy-only; frontend uses v1-first → legacy fallback).
- AuthN on public WS/ingress; rotate `BLUE_TEAM_API_KEY`; observability.

**Medium**
- Bring up Docker (Neo4j+Postgres+Redis) → bootstrap schema + migrations → flip `TGIE_PERSIST=db`;
  BELS custody on-chain round-trip; Celery/Redis workers; Neo4j GDS precompute.
- Move client-side risk calculators to the backend (`/api/graph/intel`); delete the React
  calculators.
- Re-expose Fraud DNA frontend if desired; richer recovery forensic timeline (needs event store).

**Low**
- Edge-routing/bundling in the graph; graph rhombus fix; multi-replica perf.
- Frontend tests; CI; commit + push (when Jay asks).

**Stretch goals**
- Real RL retraining of Blue (investigator-gated); foundation-model attacker; real-data + linkage-
  error recalibration of every context signal; CBS integration; migrate BELS to a bank/RBI EVM chain.

---

# Section 20 — AI Handover Instructions

> Another Claude/GPT instance reading this: start here.

### How to understand the project (read order)
1. This file (§1–§2 first).
2. Confirm the running tree: `lsof -iTCP:3000` / `ps aux | grep -E 'vite|uvicorn'`. **ALL work is in
   `~/Desktop/TGIE`.** Never touch `~/transaction-graph-intelligence`.
3. `backend/main.py` (what's mounted) → `backend/api/routes.py` (`POST /transaction/manual` is the
   spine) → `backend/risk_engine/engine.py` (the decision) → `backend/blue_team_v2/engine.py` (the
   detector) → `frontend/src/App.tsx` + `GraphScene.tsx` (the live UI).
4. The `docs/` folder: `redesign/REDESIGN_SUMMARY.md`, `TGIE_PROJECT_KNOWLEDGE.md`,
   `PERCENTAGE_AUDIT.md`, `CUSTOMER_PROFILE_INTELLIGENCE_AUDIT.md`, `TRANSACTION_SCHEMA_SPEC.md`,
   `blue_team_v2/docs/AUDIT_2026-06-29.md`, `red_team/adversarial/reports/*`.

### Where to begin work
- Detection accuracy → §18 items 1–3 (the highest-value, hardest, most-impactful work).
- A new feature → follow the established module pattern: backend package
  (`engine.py` pure funcs + `store.py` JSON + `router.py` + `__init__.py`) mounted fail-safe in
  `main.py`; frontend `api.ts` + page/component using `theme.ts` tokens; tests in `backend/tests/`.

### What NOT to change (do-not-regress list)
- The `risk_score` wire contract (0–1 fraction). Never put 0–100 on it. Use `utils/percent.ts`.
- `GraphScene.tsx`: never call `d3ReheatSimulation()` manually (black-canvas crash); keep structFloor
  0.06; keep `graphSig` topology-only; keep the converge→freeze lifecycle.
- Do NOT reintroduce: hardcoded sector grid / origin-gravity center force; per-pattern scenario
  buttons; an always-on top-right UB orb; a top header bar; demo/fake metrics; gold accent on the
  recovery pages (those are cream).
- Do NOT remove features (Jay's standing rule: only add / only improve).
- Do NOT suggest git/commits (Jay declined). Do NOT flag `/api/graph/layout` as dead code.
- blue_team_v2 is the isolation boundary for Red Team — adversarial code imports only blue_team_v2,
  never the reverse. Red never auto-trains Blue.

### Architectural principles
Explainable + deterministic + bounded; graceful degradation (no Docker/GPU/cloud required);
additive/backward-compatible changes; one decision authority (risk_engine); local-only AI (UB);
context (memory) over more structural detectors; honesty over fabricated figures.

### Coding conventions
- Backend: Python, FastAPI APIRouters, stdlib-preferred (auth is stdlib-only), pure functions over
  case/component dicts, JSON `_data/` persistence, fail-safe mounts, off-event-loop heavy compute
  (`asyncio.to_thread`). Tests with pytest; run `python -m scripts.readiness`.
- Frontend: TypeScript (`strict:false`, guard reads with `?? 0`), React Router, Zustand store, theme
  tokens (`T` / cream `A`), `npx tsc --noEmit` must be clean, `npm run build` must pass.
- Match surrounding code's idiom, comment density, and naming. Reference files as `path:line`.

### Design philosophy
- **Frontend:** "Less UI, More Intelligence" — minimal/premium/enterprise banking; quiet; matte-black
  canvas; warm accent only for brand + primary action; color only for meaning; one focal number per
  view; subtle motion only; every element answers "what does the investigator do next?".
- **Backend:** single source of truth (risk_engine); explainable factor scoring; suppress, never
  invent; profile-aware; cross-product aware; regulator-mapped.
- **Investigator workflow:** one fraud = one permanent case; everything baked in; recovery-first
  framing ("can we still get the money back?"); evidence anchored and court-ready; collaboration with
  immutable audit; nothing lost on handover.

### Verification habits
Run the app and SEE it (puppeteer-core + system Chrome `--use-angle=swiftshader` for headless WebGL;
auth via injected localStorage tokens). Run the backend test suite (285 pass). Keep tsc clean.
Restart the backend after adding modules (no `--reload`). Confirm Ollama is up for any UB/DNA/recovery
LLM path.

### Final note
This file is the project's brain backup. If you learn something non-obvious — a new gotcha, a design
decision, a fix — **update this file** so the next instance inherits it. The project must survive loss
of context windows and migration to another model. That is the whole point of this document.
