# UB — Union Bank AI Investigation Assistant (Demo Persona & Runbook)

UB is the on-premise cognitive layer of TGIE. As of 2026-06-30 it presents as the
**Union Bank AI Investigation Assistant** — a calm, concise, respectful senior fraud-officer,
not a generic chatbot. This note is for whoever runs a live demonstration.

## What it does now

- **Time-based greeting.** UB greets with Good Morning / Afternoon / Evening computed from the
  machine's local clock (night → Good Evening). The time is injected into every prompt at
  runtime (`ub/ai_core/ub_brain.py::_runtime_context`), so it is always correct.
- **Name & role memory.** If a visitor is introduced ("He is Abhinav, Director of Union Bank"
  / "this is one of the judges"), UB welcomes them, addresses them as Mr./Ms. <surname> or by
  role for the rest of the conversation, and raises formality for judges/auditors/directors/
  mentors. It will **never invent a name** — if none is given, it greets without one.
- **Audience adaptation.** More technical depth for engineers/technical judges; plain,
  value-focused language for executives and visitors.
- **Honesty.** If asked about something TGIE does not do, it says exactly: *"That capability is
  not currently implemented in this prototype."* It is candid about prototype status.
- **Knows the project & the banking domain.** Graph engine, Blue Team (rules, analytics, risk
  score, narratives, evidence), Red Team, Recovery, plus Union Bank products/channels (Savings,
  Current, Loan, Credit Card; UPI/IMPS/NEFT/RTGS/SWIFT; ATM/Cash/POS/QR/Wallet/Merchant;
  Branch/Internet/Mobile) and **cross-product fraud**.

## Modes (set per request to `/ub/chat` via the `mode` field)

| Mode | Use it for |
|---|---|
| `chat` (default) | General Q&A; auto-routes greetings/small talk to the reception persona. |
| `presentation` | Polished explanations to judges / executives / auditors. |
| `demo` | Auto-presenter: `POST /ub/demo` walks the 8-section guided tour end to end. |
| `judge` | Pointed Q&A; appends a confidence + sources transparency footer. |
| `developer` | Engineer-level, file-and-module specific. |
| `founder` | The rationale / why-Union-Bank-built-this. |

## Running it

1. **Ollama up** with the model: `ollama serve` (persistent) + `llama3.1:8b` pulled.
2. **Backend up**: UB auto-mounts at `/ub/*` on the core backend (`:8000`). The frontend orb
   calls `/ub/chat` (session `voice-orb`); Vite proxies `/ub` → `:8000`.
3. **Health check**: `GET /ub/health` should be green (`up` + `model_available`).

## Important operational notes

- **Persona / Q&A changes need a UB service restart** (the persona and `judge_questions.json`
  load at brain init) — but **not** a full re-index.
- **Knowledge from the codebase**: the knowledge engine indexes the actual source + docs;
  `judge_questions.json` (113 vetted answers) supplies authoritative facts that outrank raw
  retrieval. Rebuild the code index only when code/docs change: `python -m ub index` or
  `POST /ub/reindex`.
- **Auto-refresh**: set `UB_AUTO_REFRESH=1` to make UB re-index automatically when the project
  changes (cheap mtime/size check each turn). Left **off by default** so a live question never
  blocks on a re-index — prefer a manual reindex before a demo.

## Quick sanity script before a demo

```
POST /ub/chat {"message":"Good morning.","mode":"chat","session_id":"check"}
POST /ub/chat {"message":"He is <name>, Director of Union Bank.","mode":"chat","session_id":"check"}
POST /ub/chat {"message":"Explain cross-product fraud.","mode":"judge","session_id":"check"}
```
Expect: time-correct greeting; the visitor addressed by name on later turns; an accurate,
grounded cross-product answer. Delete the `check` session afterwards (`ub/data/sessions/`).
