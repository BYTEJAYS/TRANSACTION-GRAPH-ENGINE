#!/usr/bin/env bash
# SessionEnd hook — logs a summary of the session to ~/claude-sessions.log
# Runs async so it never delays Claude's shutdown.
# Gives you a searchable history of what was built in each session.
#
# Wire up in settings.json:
# "SessionEnd": [{ "matcher": "", "hooks": [{ "type": "command", "command": "~/.claude/hooks/log-session.sh", "async": true }] }]
#
# STDOUT = JSON parsed by Claude. STDERR = debug only. Never plain-echo to stdout.

LOG_FILE="$HOME/claude-sessions.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')

# Get project context
if git rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
  PROJECT=$(basename "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null || echo "unknown")
  BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
  FILES_CHANGED=$(git diff --name-only HEAD 2>/dev/null | wc -l | tr -d ' ')
  CONTEXT="$PROJECT ($BRANCH) — $FILES_CHANGED files changed"
else
  CONTEXT="$(basename "$PWD")"
fi

{
  echo "[$TIMESTAMP] $CONTEXT"
} >> "$LOG_FILE" 2>/dev/null || true

exit 0
