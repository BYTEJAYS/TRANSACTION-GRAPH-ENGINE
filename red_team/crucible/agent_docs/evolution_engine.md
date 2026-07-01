# Intelligent Fraud Evolution Engine

Package: `red_team/evolution/`. A controlled, **investigator-in-control** adversarial
simulator that continuously evolves synthetic fraud against **Blue Team V2** to find
blind spots. Defensive research only; synthetic data only.

## The architectural invariant (non-negotiable)
The Red Team **never auto-trains Blue Team.** Per generation, mutation is automatic,
but *learning is not*:

```
plan weakest category → build/hybridise attack → apply difficulty
   │  (per generation, automatic)
   ▼
run vs Blue Team V2
   │
Blue detects? ── YES ─→ failure analysis → directed mutation (Red learns) → next gen
   │
   └──────── NO ─→ SUCCESS → queue InvestigatorAlert (NOT injected) → investigator
                              approves? → append to hardening backlog (Blue untouched)
```

`learning_gate.py` is the safety boundary. It **imports nothing from `blue_team_v2`**
and `LearningGate.self_check()` asserts that at startup. Approval only appends to a
JSONL **hardening backlog** (a triage queue for Blue Team owners) — it never calls,
retrains, or mutates Blue Team V2.

## Modules
| File | Role |
|------|------|
| `engine.py` | `EvolutionEngine` orchestrator: `run_attack`, `run_campaign`, `dashboard_state` |
| `library.py` | Attack library — 52 named `FraudFamily` builders → categories (extensible) |
| `runner.py` | `BackgroundCampaignRunner` — daemon thread runs continuous evolution into the live queue |
| `crossover.py` | Gene-level recombination → hybrid fraud (unions special-node tricks) |
| `difficulty.py` | Easy…Impossible profiles: size, noise ratio, multi-day, hybridisation, realism |
| `legit_traffic.py` | 95%/5% legit-cover noise + human timing; tags fraud/legit nodes for FP/FN |
| `blue_target.py` | Rich V2 verdict view via `RedTeamTarget.judge_component` (one-way Red→Blue) |
| `failure_analysis.py` | "Why detected?" → maps each fired V2 detector to counter-mutations |
| `llm_client.py` | Pure-stdlib local **Ollama** client (`/api/chat`, `format:json`, health) |
| `llm_strategist.py` | **Ollama-powered strategist**: proposes validated evasion plans (ops + gene overrides) |
| `strategy_memory.py` | Red's persistent learning: records winning recipes, primes the LLM few-shot |
| `weakness.py` | `WeaknessMap` + AI planner: detection % per category, biases attacks to blind spots |
| `metrics.py` | Detection rate, FP/FN, gens-to-evade, top bypassed detector, best mutation |
| `learning_gate.py` | **Investigator approval boundary** (alerts → approved hardening backlog) |
| `api.py` | FastAPI router `/api/v1/evolution/*` (mounted in `api/main.py`) |
| `dashboard.html` | Investigator console (`GET /api/v1/evolution/ui`) |

## Blue coupling
Uses the V2 `red_team_interface` through `sandbox/v2_target._resolve_backend_path`
(same backend locator as the `CRUCIBLE_BLUE_TEAM=v2` wiring). No code imports
`red_team` into Blue. Set `CRUCIBLE_V2_BACKEND` if the TGIE `backend/` dir isn't
auto-found.

## API (response wrapper `{data,error,meta}`)
- `POST /api/v1/evolution/attacks` `{family?,category?,difficulty}` → one evolved attack
- `POST /api/v1/evolution/campaigns` `{n_attacks,difficulty}` → dashboard state
- `POST /api/v1/evolution/campaigns/auto/start` `{difficulty,interval_seconds,rotate_difficulty}` → continuous runner
- `POST /api/v1/evolution/campaigns/auto/stop` · `GET …/campaigns/auto/status`
- `GET  /api/v1/evolution/dashboard | /weakness | /metrics | /library`
- `GET  /api/v1/evolution/alerts?status=pending` → investigator queue (durable)
- `POST /api/v1/evolution/alerts/{id}/approve|reject` `{investigator_id,notes}` (gated learning)
- `GET  /api/v1/evolution/backlog` → approved hardening patterns
- `GET  /api/v1/evolution/ui` → dashboard (with auto-run toggle)

## Elitist beam search (the search upgrade)
Each generation evolves from the BEST genome found so far (elitism — never regress) and
evaluates `beam_width` (default 3) heuristic candidates plus the LLM rival, keeping the one
Blue scores lowest. Benchmark (80 matched attacks): beam 1→3 lifted evasions 29→43/80 and
dropped mean Blue risk 0.759→0.690. Knobs: `engine.beam_width`, `engine.max_llm_calls_per_attack`.

## Ollama adversarial strategist (the Red brain)
A local LLM (default `llama3.1:8b`, fast `llama3.2:3b`) upgrades mutation from the
static detector→operator map to *reasoned* evasion. On detection the engine asks the
strategist for a plan — which operators to apply AND direct gene overrides (channels,
timing, ages, amounts, topology) — primed with the most relevant past wins from
`strategy_memory`.

**Greedy acceptance (why it's strictly stronger).** The LLM does NOT override the
heuristic. Each mutation step the heuristic candidate ALWAYS competes; when the LLM is
on it adds a rival candidate, and the engine keeps whichever Blue scores LOWEST
(`_candidate_risk`), ties going to the heuristic. So the strategist can only help, never
derail a working trajectory. A/B benchmark (12 matched attacks, identical seeds/families,
medium+hard): with greedy acceptance LLM matched evasions (8/12 = 8/12) and **lowered mean
Blue risk 0.600 → 0.574** (harder to detect), and evaded `hub_and_spoke` in fewer
generations. (Without greedy acceptance the LLM was a wash — it sometimes derailed an
attack the heuristic would have evaded; greedy fixed that.)

Guarantees:
- **Red-only.** The strategist never imports/calls Blue; it only reads Blue's verdict
  text and proposes RED mutations. The investigator gate is unchanged.
- **Untrusted output is sanitized.** Every field is validated/clamped against the
  locked format (9 rails, integer amounts, valid enums, age/threshold rules) before
  apply; invalid values dropped, unknown keys ignored, nothing eval'd. If a gene
  override breaks `hard_validate`, it's reverted (operators kept).
- **ON by default when Ollama is available** (benchmark-proven stronger). Disable with
  the dashboard toggle, `POST /llm/config {enabled:false}`, or `CRUCIBLE_LLM_AUTO=0`. If
  Ollama is down or returns junk, `propose()` returns None and the heuristic drives — no
  hard dependency. Budgeted to ≤3 LLM calls per attack (greedy ⇒ more calls can't hurt).
  NB: default-on adds latency (~10–30s per *detected* attack); turn it off for fast runs.
- **Compounding learning.** Every evasion is recorded to `strategy_memory` (JSONL,
  `CRUCIBLE_STRATEGY_MEMORY`) and fed back as few-shot exemplars → Red gets better at
  beating the detectors that are firing. The `learning_curve` (rolling Blue detection
  rate) shows it trending down as Red hardens.

API: `GET /llm/status`, `POST /llm/config {enabled}`, `GET /learning_curve`. Env:
`OLLAMA_HOST`, `CRUCIBLE_LLM_MODEL`, `CRUCIBLE_LLM_AUTO`.

## Continuous evolution + durability
`runner.py` runs the engine in a daemon thread, launching one evolved attack every
`interval_seconds` into the SAME engine + `learning_gate` the API serves, so missed
attacks appear live in the investigator queue (it still never auto-trains Blue).
The queue is now **durable**: `learning_gate` persists pending/decided alerts to
`CRUCIBLE_ALERTS_STORE` (default `evolution/data/investigator_alerts.jsonl`) and
rehydrates on startup — fixing the old "in-memory singletons reset on restart"
limitation. For a Celery batch instead of the in-process thread, call
`EvolutionEngine.run_campaign` from a task pointed at the same `CRUCIBLE_ALERTS_STORE`.

## Genome changes this introduced (core, additive)
- `to_transaction_list()` gained a `cycle` branch (real closed ring) so round-robin /
  nested-ring families exercise V2's `circular_flow` detector. Only affects `cycle`
  genomes (no existing seed/DNA uses cycle). Note: CLAUDE.md Rule 5 ("never set
  topology.type=cycle") is a *bypass-DNA* guideline for the old union-bank clone — the
  evolution engine deliberately uses cycles to attack V2; the bypass DNAs still don't.
- `_compute_timestamp()` clamps the day offset to ~100y (stacked time-dilation operators
  could overflow `timedelta`). No effect on normal-range genomes.

## Tests
`red_team/tests/test_evolution.py` — library/crossover/difficulty/failure-analysis +
safety tests (no Blue coupling; approval-only backlog; planner bias) + V2 end-to-end
(skips if backend absent). Run: `pytest red_team/tests/test_evolution.py -v`.

## Run it
```bash
CRUCIBLE_BLUE_TEAM=v2 uvicorn red_team.api.main:app --port 8001
# open http://localhost:8001/api/v1/evolution/ui
```
