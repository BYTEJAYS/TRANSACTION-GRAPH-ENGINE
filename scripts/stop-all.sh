#!/usr/bin/env bash
# stop-all.sh — shut down the whole trinity (PRL + ASCENSION + LEGACY).
# (Leaves Ollama alone, since it may be shared with Jerry.)
set -uo pipefail

echo "■ Stopping ASCENSION…"
"$HOME/ascension/stop-ascension.sh"

echo
echo "■ Stopping LEGACY…"
for port in 8088 3088; do
  pids=$(lsof -ti tcp:$port 2>/dev/null || true)
  if [ -n "$pids" ]; then
    kill $pids 2>/dev/null || true
    echo "  killed :$port"
  else
    echo "  :$port already free"
  fi
done

echo
echo "■ Stopping PRL…"
"$HOME/prl/stop-prl-local.sh"

echo
echo "All stopped. Bring it back with ~/start-all.sh"
