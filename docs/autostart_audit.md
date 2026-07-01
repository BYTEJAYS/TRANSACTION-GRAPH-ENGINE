# TGIE Auto-Start Audit (Phase 1)

> Inspected 2026-06-24 on this Mac (Apple M5, macOS 26.4) to find everything that starts
> automatically at boot/login, ahead of converting TGIE to fully manual control.

## Method

Checked every standard macOS auto-start surface:
`launchctl list`, `~/Library/LaunchAgents`, `/Library/LaunchAgents`, `/Library/LaunchDaemons`,
`crontab -l`, Login Items (System Events), and the Ollama install type.

## Findings

| Surface | TGIE-related auto-start found? | Detail |
|---|---|---|
| `launchctl` (user) | **YES — 1** | `com.ollama.ollama` |
| `~/Library/LaunchAgents` | No | only `com.google.GoogleUpdater.*`, `com.google.keystone.*` (unrelated) |
| `/Library/LaunchAgents` | No | nothing ollama/tgie |
| `/Library/LaunchDaemons` | No | nothing ollama/tgie |
| `crontab` | No | no TGIE/ollama/uvicorn/vite entries |
| Login Items (classic) | No | only `Notion` (unrelated) |
| Ollama install | `.app` present | `/Applications/Ollama.app`; CLI at `~/.local/bin/ollama` |

### The one auto-start: `com.ollama.ollama`

```
launchctl print gui/<uid>/com.ollama.ollama
  path = (submitted by smd.97)          ← registered via SMAppService (modern background item)
  properties = ... runatload ...        ← set to launch at login
  state = not running                   ← not running as a launchd job right now
```

- **What it is:** Ollama.app registered itself as a **background / login item** (Apple's
  `SMAppService` API, the modern replacement for LaunchAgent plists — which is why it shows in
  `launchctl list` but has **no plist** in `~/Library/LaunchAgents` and does **not** appear in
  the classic "Login Items" AppleScript list; it lives under System Settings → General →
  Login Items → "Allow in the Background").
- **Effect:** `runatload` means Ollama's server would start automatically at each login.
- **Note:** the Ollama currently running (`~/.local/bin/ollama serve`, started manually this
  session) is **separate** from this launchd job.

### What is NOT auto-starting (good)

- **TGIE Backend, Frontend, UB, and any watcher/scheduler** have **no** LaunchAgent,
  LaunchDaemon, login item, or cron entry. Every time they ran, it was a manual/session-bound
  process — nothing survives a reboot on its own.
- The Google Updater/Keystone agents and Notion login item are unrelated to TGIE and are left
  untouched.

## Conclusion

The **only** thing that auto-starts for the TGIE stack is **Ollama** (via the
`com.ollama.ollama` SMAppService background item). Disabling that one item achieves the goal of
"nothing starts automatically." See Phase 2 (`docs/manual_control_guide.md`) for the disable
action and the manual control suite in `TGIE/control/`.
