# TGIE Manual Control Guide

> TGIE is a **manually-controlled application suite**. Nothing starts at boot or login.
> You start and stop the whole stack with one double-click each, from `TGIE/control/`.

## The four scripts (`TGIE/control/`)

| Double-click | Does |
|---|---|
| `start_tgie.command` | Starts everything in order, waits for health, opens the browser, prints status |
| `stop_tgie.command` | Stops everything (reverse order), sweeps orphans, verifies shutdown |
| `status_tgie.command` | Shows each component: running/stopped, port, PID, memory |
| `restart_tgie.command` | Stop, then start |

All are `chmod +x` and open in Terminal when double-clicked from Finder.

## The stack (independent components, independent ports)

| Component | Port | Process | PID file |
|---|---|---|---|
| Ollama | 11434 | `ollama serve` | `control/pids/ollama.pid` |
| UB (Universal Brain) | 8001 | `python -m ub_service` | `control/pids/ub.pid` |
| TGIE Backend | 8000 | `uvicorn main:app` | `control/pids/backend.pid` |
| TGIE Frontend | 3000 | `npm run dev` (Vite) | `control/pids/frontend.pid` |

UB runs as its **own** service on :8001 so it can be started/stopped independently. The
frontend's voice orb reaches it through Vite's `/ub` proxy (→ :8001). (If you ever want UB
embedded in the backend process instead, start the backend with `TGIE_MOUNT_UB=1` — but the
suite keeps them separate by design.)

## How startup works

`start_tgie.command` runs strictly in order, gating each step on a health check:

1. **Ollama** → wait for `:11434/api/version`; warn if `llama3.1:8b` / `nomic-embed-text` aren't pulled.
2. **UB** → `:8001/ub/health` (needs Ollama + a built knowledge index).
3. **Backend** → `:8000/health`.
4. **Frontend** → `:3000`.
5. Writes a PID file per service, prints a colored status table, and opens
   `http://localhost:3000` (set `TGIE_NO_OPEN=1` to skip).

Final output on success:
```
TGIE STARTED SUCCESSFULLY
  ● Ollama    running  ·  http://localhost:11434
  ● UB        running  ·  http://localhost:8001/ub/health
  ● Backend   running  ·  http://localhost:8000
  ● Frontend  running  ·  http://localhost:3000
```
Already-running components are detected (by listening port) and adopted, so re-running start
is safe and idempotent.

## How shutdown works

`stop_tgie.command`:
1. Reads each PID file and stops services **gracefully** (`SIGTERM` to the process **and its
   children** — e.g. Vite under npm), waits, then **force-kills** (`SIGKILL`) anything that lingers.
2. Order: Frontend → Backend → UB → Ollama.
3. **Orphan sweep** — pattern-matched and *scoped to this workspace* so it never touches
   unrelated processes: `…/TGIE/frontend`, `vite --port 3000`, `uvicorn main:app …:8000`,
   `ub_service`, `ollama serve`.
4. Verifies every port (11434/8001/8000/3000) is free, removes PID files, reports.

Final output:
```
TGIE STOPPED SUCCESSFULLY
  All TGIE services have been terminated.
```

## How to restart

Double-click `restart_tgie.command` (= stop then start), or run the two in sequence.

## How to check status

Double-click `status_tgie.command`:
```
COMPONENT  STATE     PORT   PID    MEMORY
Ollama     ● running 11434  9109   780 MB
UB         ● running 8001   23110  120 MB
Backend    ● running 8000   23145  180 MB
Frontend   ● running 3000   23180  90 MB
```
It also reports the loaded Ollama models and UB's knowledge-index size (files/chunks).

## Auto-start is disabled

The audit (`docs/autostart_audit.md`) found exactly one auto-start: Ollama, registered by
`Ollama.app` as a login background item (`com.ollama.ollama`, SMAppService `runatload`). It has
been **disabled** (not uninstalled):

```bash
launchctl disable gui/$(id -u)/com.ollama.ollama
launchctl bootout  gui/$(id -u)/com.ollama.ollama
# verify:
launchctl print-disabled gui/$(id -u) | grep ollama   # → "com.ollama.ollama" => disabled
```

Nothing else (backend, frontend, UB, watchers, cron) was ever set to auto-start. So after a
reboot, **nothing TGIE runs** until you double-click `start_tgie.command`.

> **Re-enable note:** if you later open `Ollama.app` from the Dock, it may re-register its
> login item. To re-disable, run the `launchctl disable` line above, or toggle it off in
> **System Settings → General → Login Items → Allow in the Background**. To re-enable
> intentionally: `launchctl enable gui/$(id -u)/com.ollama.ollama`.

## Configuration (env overrides)

| Var | Default | Meaning |
|---|---|---|
| `TGIE_PYTHON` | the TGIE venv python | interpreter for backend + UB (local 3.14 can't build scipy) |
| `TGIE_OLLAMA` | `~/.local/bin/ollama` | ollama binary |
| `TGIE_NO_OPEN` | `0` | `1` = don't auto-open the browser on start |
| `TGIE_MOUNT_UB` | unset | `1` = embed UB in the backend instead of the standalone :8001 service |

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `npm not found` on start | Node not on the `.command` PATH — the script probes `~/.nvm/...`; install Node or set PATH. |
| UB unhealthy | Ollama down, or no index — run `python -m ub index`; check `logs/ub.log`. |
| Backend unhealthy | `scipy` build error means it's on Python 3.14 — set `TGIE_PYTHON` to a 3.11 venv (the suite defaults to the working one). See `logs/backend.log`. |
| Port already in use | Something is already listening — `status_tgie.command` shows the PID; `stop_tgie.command` clears it. |
| Stop says "incomplete" | Re-run `stop_tgie.command`; it force-kills on the second pass. |
| Services die right after start (from a terminal that exits) | Use the double-clickable `.command` (keeps a Terminal window); the services are `nohup`+`disown`ed so they persist while that window stays open. |
| Logs | `TGIE/logs/{ollama,ub,backend,frontend}.log` |
