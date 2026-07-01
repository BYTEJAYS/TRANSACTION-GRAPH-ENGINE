# scripts/

Convenience launchers for local development.

| Script | What |
|---|---|
| `start-all.sh` | Bring up the local TGIE stack |
| `stop-all.sh` | Tear it down |
| `start.sh` | Repo-root start script (backend + frontend) |

> **Persistence gotcha (verified):** background processes launched with `&`/`nohup`/`setsid`
> from a one-shot shell get reaped when that shell returns. To keep `uvicorn` + `vite` up,
> run them as the blocking foreground of a long-lived terminal/session, or use the macOS
> `deployment/TGIE-launch.command` which opens dedicated windows.

## Manual start (most reliable)

```bash
# Terminal 1 — backend
cd ../backend && .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
# Terminal 2 — frontend
cd ../frontend && npm run dev    # http://localhost:3000
```

Review these scripts before running — paths may reference the original source-repo layout
and might need adjusting to the consolidated `TGIE/` paths.
