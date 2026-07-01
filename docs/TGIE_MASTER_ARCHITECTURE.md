# TGIE Master Architecture

> The single source-of-truth architecture for the entire TGIE (Transaction Graph
> Intelligence Engine) ecosystem, as assembled in this `TGIE/` workspace.

---

## 1. Ecosystem Map

```
                                   ┌───────────────────────────┐
                                   │        OBSERVER           │
                                   │   (analyst / browser)     │
                                   └─────────────┬─────────────┘
                                                 │ HTTPS / WSS
                                                 ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  FRONTEND  (frontend/) — Vite + React 18 + three.js                          │
│  ┌──────────────┐  ┌──────────────────┐  ┌───────────────────────────────┐  │
│  │ GraphScene   │  │ Risk Intel layer │  │ UB — Universal Brain (ub/)    │  │
│  │ (3D force    │◄─┤ ai/riskPropaga-  │  │ voice assistant · wake word · │  │
│  │  graph)      │  │ tion.ts          │  │ intents (show/hide intel…)    │  │
│  └──────────────┘  └──────────────────┘  └───────────────────────────────┘  │
└───────────────┬──────────────────────────────────────────┬──────────────────┘
        WS /ws/live │                    POST /transaction/manual │
                    ▼                                              ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  TGIE CORE BACKEND  (backend/) — FastAPI :8000                               │
│                                                                              │
│   simulator ──► graph_engine (networkx GraphManager) ──► anomaly_detection   │
│                         │                                  (IsolationForest) │
│                         ▼                                                    │
│                 Blue Team router  ──select(ACTIVE_BLUE_TEAM)──►              │
│                    ├── V1  blue_team/      (ML: IF + XGBoost + rules)         │
│                    └── V2  blue_team_v2/   (deterministic: 11 detectors)     │
│                         │                                                    │
│                 evidence/ (forensic) · streaming/ · api/ (routes, ws,        │
│                 redteam[localhost-gated])                                    │
└───────────────┬──────────────────────────────────────────────────────────┬─┘
                │ verdict schema (graph_id/verdict/risk/flagged_nodes/…)     │
                ▼                                                            │
┌──────────────────────────────────────────┐               ┌────────────────▼───────────────┐
│  BLING BLUE TEAM  (blue_team/bling :8001) │               │  ADVERSARIAL PLANE (offline)    │
│  FastAPI + Postgres + Neo4j + Celery      │               │  red_team/adversarial           │
│  detection · evidence(PDF) · ML bridges   │               │   GA · MAP-Elites · PPO ·       │
│  (Union Bank forensic service)            │               │   GraphGAN · 6 context signals  │
└──────────────────────────────────────────┘               │  red_team/engine  (scenarios)   │
                                                            │  red_team/crucible (genomes +   │
                                                            │   human gate + prophecy)        │
                                                            └─────────────────────────────────┘
```

---

## 2. Data Flow (live path)

1. **Ingress** — analyst submits a transaction (`POST /transaction/manual`) or the
   `simulator` emits the unified sample feed (`frontend/src/data/sampleDataset.ts`
   mirrors the backend feed).
2. **Graph construction** — `graph_engine/graph_manager.py` (networkx) inserts nodes/edges,
   maintains connected components, enforces `GRAPH_MAX_NODES/EDGES` caps.
3. **Scoring** — the Blue Team router dispatches to V1 (ML) or V2 (deterministic). V2:
   18-factor NodeMetrics → 11 detectors → evidence → per-node score → cluster verdict.
4. **Broadcast** — verdicts + graph deltas pushed over `WS /ws/live` (~1s heartbeat).
5. **Render** — `GraphScene.tsx` merges deltas (memoized on `graphSig`), the multi-scale
   cluster force lays out components, the risk-intel layer colors nodes by role/risk.
6. **Narration** — UB wakes on fraud, narrates, and responds to voice intents.

---

## 3. Blue Team Interactions

- **Router pattern:** `ACTIVE_BLUE_TEAM` env selects V1/V2; **shadow mode** runs both on
  the same graph for comparison.
- **Schema contract:** both adapters emit the identical verdict schema (the de-facto shared
  contract — candidate for extraction into `shared/`).
- **Hardened stack (research → prod path):** `red_team/adversarial/integration/HardenedBlueTeam`
  wraps the real V2 engine and adds 6 context signals (provenance, behavioural, coordination,
  relationship, relationship-maturity) emitting the same schema + an additive `hardening` block.

## 4. Red Team Interactions

- **Adversarial self-play** (`red_team/adversarial`) runs offline against the real V2 engine
  via `BlueTeamOracle`; produces attacks, a diverse evasion corpus, and the context-signal
  counters. Closed Red⇄Blue loops: `arms_race.py`, `full_stack.py`, `final_stack.py`.
- **Frontend panel** (`api/redteam.py`, localhost-gated): human-in-the-loop review queue —
  only human-approved, Blue-*missed* evasions train Blue.
- **CRUCIBLE** (`red_team/crucible`) is the Union Bank analogue: nightly genome evolution →
  human gate → prophecy/learning feedback.
- **Isolation contract:** `red_team/engine` enforces `assert_isolation()` — no blue_team
  import-time coupling.

## 5. UB Interactions

- UB (`frontend/src/ai/ub.ts`, `hooks/useUB.ts`, `components/ai/UBOrb.tsx`; mirrored in `ub/`)
  is a browser-side voice assistant: wake-word arming, SpeechRecognition intents
  (`show_intel`/`hide_intel`), browser SpeechSynthesis narration. Call-driven orb (not
  always-on). It consumes the risk-intel layer for narration content.

## 6. Frontend ↔ Backend Interactions

- `WS /ws/live` (graph + verdict stream), `POST /transaction/manual` (ingress), `/health`
  (Railway healthcheck). Vite dev proxy forwards `/api` and `/ws` to `:8000`.

---

## 7. Training & Feedback Loops

```
   Red Team (GA/QD/PPO/GAN)  ──generates──►  evasions
            ▲                                   │
            │                          human gate (frontend panel /
            │                          CRUCIBLE human_gate)
    re-evolve vs hardened                       │ approve Blue-MISSED only
            │                                    ▼
   Blue Team context signals  ◄──train/calibrate──  approved corpus
            │                                    │
            └────────  arms_race / full_stack / final_stack  ◄── benign corpus (FP guard)
```

- **Equilibrium:** the engagement terminates in *economics* — `relationship-maturity` forces
  the attacker to pre-move legit value proportional to laundering, a year ahead.
- **Honesty guard:** strict (on-graph) ASR reported separately from permissive ASR; benign
  FP measured on construction-honest corpora every round.

---

## 8. Deployment Architecture

```
  GitHub: BYTEJAYS/TRANSACTION-GRAPH-ENGINE
     ├── branch main        (full heavy build: Kafka, GNN, docker-compose)
     └── branch production  (deploy-optimized)
                 │
        ┌────────┴─────────┐
        ▼                  ▼
   Railway (backend)   Vercel (frontend)
   railway.toml +      Root: frontend/
   nixpacks.toml       Branch: production
   Python 3.11         VITE_API_URL → Railway
   uvicorn :$PORT

  BLING Blue Team + CRUCIBLE: standalone (Union Bank), docker-compose; not on the
  public TGIE deploy.
```

Deploy artifacts live in `deployment/` (railway.toml, nixpacks.toml, docker-compose.yml,
DEPLOY.md, launch/stop `.command` files, `infrastructure/` flink+kafka).

---

## 9. Key Invariants (do not regress)

- `mergedData` memoized on `graphSig` — prevents heartbeat reheat / vibrating blob.
- Never call `d3ReheatSimulation()` before first graphData — blank-canvas crash.
- Decentralized cluster forces — no global center/origin gravity (no solar-system hierarchy).
- `red_team/engine` isolation contract — no blue_team coupling.
- V1 untouched by V2 — V2 is additive/opt-in.
- Localhost-gated red team panel — never exposed on public deploy.
