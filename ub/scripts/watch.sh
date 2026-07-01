#!/usr/bin/env bash
# Self-updating knowledge system (Phase 11).
# Polls the TGIE workspace; when files change, UB regenerates summaries + re-indexes.
# Uses fswatch if available (event-driven), else falls back to a 30s poll on the
# engine's own manifest-hash staleness check.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
TGIE_ROOT="$(cd "$HERE/../.." && pwd)"
PY="${UB_PYTHON:-python3}"
cd "$TGIE_ROOT"

reindex() {
  echo "[ub-watch] change detected → reindexing $(date '+%H:%M:%S')"
  "$PY" -m ub index >/dev/null 2>&1 && echo "[ub-watch] index updated" || echo "[ub-watch] reindex failed"
}

echo "[ub-watch] watching $TGIE_ROOT (Ctrl-C to stop)"
if command -v fswatch >/dev/null 2>&1; then
  fswatch -o -r \
    --exclude 'node_modules' --exclude '\.venv' --exclude '\.git' \
    --exclude '__pycache__' --exclude 'ub/knowledge_engine/index' --exclude 'logs' \
    backend frontend ub blue_team red_team docs deployment configs scripts \
  | while read -r _; do reindex; done
else
  echo "[ub-watch] fswatch not found — polling staleness every 30s (brew install fswatch for instant)"
  while true; do
    if "$PY" -c "import sys; sys.path.insert(0,'.'); from ub.knowledge_engine import KnowledgeEngine; sys.exit(0 if KnowledgeEngine().is_stale() else 1)" 2>/dev/null; then
      reindex
    fi
    sleep 30
  done
fi
