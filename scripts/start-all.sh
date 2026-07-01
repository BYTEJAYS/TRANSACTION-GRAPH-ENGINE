#!/usr/bin/env bash
# start-all.sh — bring up the WHOLE trinity in one command.
#   • PRL backend     (memory & cognition, no-Docker local stack) -> :8000
#   • ASCENSION game  (action layer; + sync :8001, coach)         -> :3000
#   • LEGACY          (meaning & story; API :8088, web :3088)
# Start PRL first so both bridges see it immediately. Every piece degrades
# gracefully on its own, so order isn't critical.
set -uo pipefail

echo "▶ Starting PRL (memory layer)…"
"$HOME/prl/start-prl-local.sh" || echo "  (PRL had trouble — the rest still runs, bridges just won't sync)"

echo
echo "▶ Starting ASCENSION (action layer)…"
"$HOME/ascension/start-ascension.sh"

echo
echo "▶ Starting LEGACY (meaning layer)…"
LEGACY_LOGS="$HOME/.legacy"
mkdir -p "$LEGACY_LOGS"
if curl -s -m 2 http://127.0.0.1:8088/api/health | grep -q project-legacy; then
  echo "  Legacy API already running on :8088"
else
  (cd "$HOME/legacy/backend" && nohup python3 -m uvicorn legacy.app:app --host 127.0.0.1 --port 8088 \
    > "$LEGACY_LOGS/api.log" 2>&1 &)
  echo "  Legacy API -> :8088  (logs: ~/.legacy/api.log)"
fi
if curl -s -m 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:3088 | grep -q 200; then
  echo "  Legacy web already running on :3088"
else
  (cd "$HOME/legacy/frontend" && nohup pnpm dev > "$LEGACY_LOGS/web.log" 2>&1 &)
  echo "  Legacy web -> :3088  (logs: ~/.legacy/web.log)"
fi

echo
echo "════════════════════════════════════════════════════════════════"
echo "  TRINITY READY"
echo "  ▸ Play:    http://localhost:3000      (ASCENSION — the game)"
echo "  ▸ Story:   http://localhost:3088      (LEGACY — the biography)"
echo "  ▸ Memory:  http://localhost:8000/health   (PRL backend)"
echo "  The loop: act in ASCENSION → PRL learns you → LEGACY tells it."
echo "  • Stop everything:  ~/stop-all.sh"
echo "════════════════════════════════════════════════════════════════"
