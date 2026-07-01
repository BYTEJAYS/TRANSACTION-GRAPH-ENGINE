#!/usr/bin/env bash
# SessionStart hook — injects context at the start of every session.
# Stdout is added directly to Claude's context window.
# Use this to remind Claude of project state without repeating yourself.
#
# Wire up in settings.json:
# "SessionStart": [{ "matcher": "startup|resume|compact", "hooks": [{ "type": "command", "command": "~/.claude/hooks/session-context.sh" }] }]
#
# For compact matcher specifically: re-injects context after context window compression.
# STDOUT goes to Claude as context. STDERR = debug only.

set -euo pipefail

OUTPUT=""

# ── Git context (only if inside a git repo) ──────────────────────────────────
if git rev-parse --is-inside-work-tree &>/dev/null; then
  BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
  RECENT=$(git log --oneline -5 2>/dev/null || echo "no commits")
  DIRTY=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')

  OUTPUT+="=== Session Context ==="$'\n'
  OUTPUT+="Branch: $BRANCH"$'\n'
  OUTPUT+="Recent commits:"$'\n'"$RECENT"$'\n'

  if [ "$DIRTY" -gt 0 ]; then
    OUTPUT+="Uncommitted changes: $DIRTY file(s)"$'\n'
  fi
fi

# ── Project rules reminder (survives context compaction) ─────────────────────
# This is the key use case: after /compact, Claude forgets CLAUDE.md context.
# These reminders get re-injected automatically.

# ── Project rules reminder (survives context compaction) ─────────────────────
# Reads the actual CLAUDE.md so rules stay current without editing this script.
CLAUDEMD_PATH=""
[ -f ".claude/CLAUDE.md" ] && CLAUDEMD_PATH=".claude/CLAUDE.md"
[ -z "$CLAUDEMD_PATH" ] && [ -f "CLAUDE.md" ] && CLAUDEMD_PATH="CLAUDE.md"

if [ -n "$CLAUDEMD_PATH" ]; then
  OUTPUT+=$'\n'"=== Project Rules (from $CLAUDEMD_PATH) ==="$'\n'
  OUTPUT+="$(head -50 "$CLAUDEMD_PATH" 2>/dev/null || true)"$'\n'
fi

# ── Output ────────────────────────────────────────────────────────────────────
if [ -n "$OUTPUT" ]; then
  echo "$OUTPUT"
fi

exit 0
