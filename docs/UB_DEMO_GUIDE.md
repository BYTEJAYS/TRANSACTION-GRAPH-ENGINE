# UB Demo Guide

How to use UB to present TGIE to investors, recruiters, judges, professors, or reviewers.

## The one-button demo (Phase 9)

```bash
python -m ub demo
# or:  curl -X POST localhost:8000/ub/demo
# or:  open the dashboard → click the DEMO mode (auto-runs the tour)
```

UB auto-presents TGIE across nine scripted sections, each grounded in the real codebase:

1. What is TGIE?
2. Why was it built? (the problem)
3. Architecture overview (services, ports, data flow)
4. UB — the local AI cognitive layer
5. Blue Team — fraud detection
6. Red Team — adversarial hardening
7. Security architecture (with honest limitations)
8. Graph intelligence engine + 3D visualization
9. Future roadmap

## Recommended live-demo flow (5-7 min)

1. **Open the dashboard** (`frontend/ub_dashboard/index.html`). Point out: live model
   (`llama3.1:8b`), indexed file/chunk counts, all running **locally**.
2. **"What is TGIE?"** (presentation mode) — the elevator pitch, with source citations.
3. **Show the real product** — open the TGIE frontend (`localhost:3000`), submit a fraud
   cycle, watch the Blue Team flag it (FRAUD ~0.97).
4. **"Explain the Blue Team"** then **"Explain the Red Team"** (developer mode) — UB cites
   actual files; show that it's reading the codebase, not improvising.
5. **Switch to Judge mode**, ask a hard one: *"What's your false-positive rate?"* — UB
   answers honestly (56.7% on realistic traffic, fixed to ~0% by the provenance signal).
   Candor backed by a plan is the strongest possible answer.
6. **"Give me a project presentation"** (presentation mode) — the closing pitch.

## Modes cheat-sheet

| Mode | Use when | Tone |
|---|---|---|
| `presentation` | pitching to non-engineers / panels | concise, polished, impact-first |
| `founder` | telling the story / vision | visionary, first-person, grounded |
| `developer` | a technical reviewer reads the code | precise, file-level, mechanism-focused |
| `judge` | hard Q&A | direct answer first, honest about limits |
| `demo` | hands-off auto-tour | guided, sectioned |
| `chat` | anything else | adaptive |

## Tips

- The dashboard's quick-question chips cover the most common asks.
- Judge Mode is pre-loaded with a question bank (`ub/data/judge_questions.json`) but answers
  any unlisted question dynamically.
- Everything is local — a great talking point: "no API keys, no cloud, the AI runs on this
  laptop and reads our actual source code."
- If asked "is this real?", run a developer-mode question and show the cited file paths.
