# TGIE — Architecture & Flow (easy guide)

> How TGIE works, stage by stage. TGIE turns transactions into a **live graph**, finds
> **money-laundering** patterns, **hardens** itself with an attacker, and **explains**
> everything with a local AI (UB). Everything runs on one Mac — nothing leaves it.
> Canonical home: `~/Desktop/TGIE`.

---

## The big picture

```
   You ──► FRONTEND (3000) ──► BACKEND (8000) ──► BLUE TEAM (detect)
            3D graph              graph + rules        │
              ▲                                        ▼
              └──────── live updates over WebSocket ◄──┘

   RED TEAM ──attacks──► BLUE TEAM ──misses──► you APPROVE ──► Blue learns
   UB (8001) ──reads the code──► explains any of it, locally
```

| Piece | Port | Job |
|---|---|---|
| Frontend | 3000 | draw the 3D graph, panels, voice |
| Backend | 8000 | ingest, build graph, run detection, stream updates |
| UB | 8001 | local AI that explains the project |
| Ollama | 11434 | runs the local LLM for UB |

---

## Main flow — a transaction's journey (stage by stage)

**1. You send transactions.** A dataset or manual entry is POSTed to the backend
(`/transaction/manual`). Each one looks like `{from, to, amount, payment_rail, time}`.

**↓ then**

**2. The backend reads the rail.** UPI/IMPS/NEFT/RTGS are normal transfers.
`CASH_IN`/`CASH_OUT` become real cash endpoints (see "Cash flow"). Bad rails fall back to UPI.

**↓ then**

**3. It's added to the live graph.** `graph_manager` (NetworkX) creates the accounts as
**nodes** and the transaction as a directed **edge**, and groups everything into connected
components (the separate "rings").

**↓ then**

**4. The Blue Team scores it.** For each component: measure the accounts → run 11 fraud
detectors → collect evidence → produce a risk score → decide a verdict
(**LOG 0.38 / REVIEW 0.62 / FRAUD 0.83**). It's deterministic, so every flag has a reason.

**↓ then**

**5. The backend broadcasts the result.** The updated graph + verdicts are pushed over a
**WebSocket** to your browser session.

**↓ then**

**6. The frontend lays it out and draws it.** It places nodes by their **shape** (chains as
lines, fan-outs as cones, rings as circles — see "Layout"), colors them by role/risk, and
animates the update. You see the fraud at a glance; ask **UB** to explain it.

---

## Cash flow (how cash in/out is handled)

```
deposit:   CASH_SOURCE ──► account        withdrawal:  account ──► CASH_EXIT
```
- Both endpoints are **real connected nodes** (type `cash`), so the whole chain
  `CASH_SOURCE → … → CASH_EXIT` stays connected and shows up in every analysis.
- **Color = identity, always:** CASH_SOURCE is **emerald** (cash entered), CASH_EXIT is
  **gold** (cash left). If it's part of a fraud, it keeps its color and gets a **red halo** —
  it never turns solid red. (Legacy `CASH` rail still works the old off-graph way.)

---

## Layout (why the graph looks clean, not tangled)

```
look at a component ──► is it a ring?  ──yes──► draw a CIRCLE
                                        ──no───► draw LAYERS top→down (money flows down),
                                                 spread siblings sideways, reduce crossings
                              ▼
                    place nodes smartly FIRST, then let physics gently tidy (not scramble)
```
Result: chain = straight line, fan-out = cone, fan-in = funnel, layered laundering = neat stack.

---

## UB flow (how the AI answers)

```
your question ──► UB picks a mode (chat/judge/developer/…) ──► gathers grounding:
   project summary + most-relevant code chunks + vetted answers + chat history
        ──► local model (llama3.1:8b) writes the answer + cites the files
```
- It's **RAG**, not fine-tuning: run `python -m ub index` to re-learn after code changes.
- Vetted answers (`judge_questions.json`) are trusted facts that **outrank** raw code, so UB
  doesn't drift on tough questions. Judge mode shows a **confidence + sources** footer.

---

## Red vs Blue + learning (how Blue gets stronger — safely)

```
RED TEAM invents an attack ──► BLUE TEAM tries to catch it
        │
        ├─ caught  ──► don't train; RED must invent something harder
        └─ missed  ──► goes to the TRAINING QUEUE (not learned yet!)
                          ▼
                   YOU review it: Learn / Ignore / Review / Reject
                          ▼
                   only "Learn" ──► added to Blue's knowledge (deduped + logged)
```
**Key rule:** nothing trains Blue automatically — a human approves every lesson. The deployed
detector is never silently changed.

---

## Investigation flow (acting on a fraud)

```
flagged cluster ──► Recovery: "can we still get the money back?" (score + ranked actions)
                ──► Case: open an investigation (timeline, notes, assignment)
                ──► Evidence: hash it into BELS (tamper-proof ledger; files stay off-chain)
```

---

## Inside each component (one line each)

- **Frontend** (`frontend/src/`): `App` shell → `graphStore` (shared state) ↔ `GraphScene` +
  `graphLayout` (3D), panels (Left, Red Team, Training Review, inspectors), `ai/` intel,
  `services/` (voice + UB).
- **Backend** (`backend/`): `api/routes` → `graph_engine` → `blue_team_v2/router` → WebSocket;
  plus routers for recovery, cases, auth, red team, UB.
- **Blue Team V2** (`backend/blue_team_v2/`): metrics → 11 `detectors/` → evidence →
  `scoring_engine` → `cluster_engine` verdict; `ai/` writes the human explanation.
- **Red Team** (`red_team/adversarial/`): `red_team/` (11 attack moves + GA/MAP-Elites/PPO/
  GraphGAN), `common/` (the 5 context signals), `self_play/` (offline hardening loop).
- **Governance** (`backend/adversarial_governance/`): the Training Queue + audit log + dedup +
  Blue Knowledge Base (the only door into Blue's training data).
- **UB** (`ub/`): `ub_brain` (orchestrator) → `knowledge_engine` (RAG) → vector store →
  `ollama_service` → Ollama.
- **Recovery / BELS** (`backend/recovery/`, `bels/`): recovery scoring; SHA-256 evidence ledger.

---

## Starting it & honest limits

- **Start:** `control/start_tgie.command` brings up, in order, **Ollama → UB → Backend →
  Frontend**, each gated on a health check. Nothing auto-starts at boot.
- **Honest limits:** it's an **advanced prototype (~55/100)**, not a production bank system.
  False positives are high on realistic data (~56.7%) and the hardened "0% FP" results use
  **synthetic** data; most attack wins are partition-dependent (the "B1" blind spot); there's
  no auth on the public socket yet. We measure these openly rather than hide them.

> Need the deep version (exact weights, file-level sub-diagrams, every flow)? That detail now
> lives across `TGIE_PROJECT_KNOWLEDGE.md` and `TGIE_DETECTION_AND_ADVERSARIAL_DEEPDIVE.md`.
