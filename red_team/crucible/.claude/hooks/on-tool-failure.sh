#!/usr/bin/env bash
# PostToolUseFailure hook — fires when a Bash tool call fails.
# Injects diagnostic hints into Claude's context so it can recover without looping.
#
# How it works: reads the failed command + error from stdin JSON,
# pattern-matches against known failure modes, outputs a helpful hint.
# If no pattern matches, outputs nothing (exit 0 silently).
#
# Wire up in settings.json:
# "PostToolUseFailure": [{ "matcher": "Bash", "hooks": [{ "type": "command", "command": "~/.claude/hooks/on-tool-failure.sh" }] }]

if ! command -v jq &>/dev/null; then
  exit 0
fi

INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
ERROR=$(echo "$INPUT" | jq -r '.error // empty' 2>/dev/null)

[ -z "$CMD" ] && exit 0

hint() {
  # Escape double quotes and newlines for safe JSON embedding
  SAFE=$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/$/\\n/' | tr -d '\n' | sed 's/\\n$//')
  printf '{"output":"%s"}\n' "$SAFE"
  exit 0
}

# Node.js not found
if echo "$ERROR" | grep -qiE 'command not found.*node|node.*not found|ENOENT.*node'; then
  hint "Node.js not found. Check: which node && node --version. Install via nvm: nvm install --lts"
fi

# npm/pnpm permission denied
if echo "$CMD" | grep -qE '^(npm|pnpm|yarn) (install|add)' && echo "$ERROR" | grep -qiE 'EACCES|permission denied'; then
  hint "Permission denied on install. Never use sudo npm. Fix: npm config set prefix ~/.npm then re-run."
fi

# Python/venv not found or not activated
if echo "$CMD" | grep -qE '^(python|python3|pip|pip3|pytest|uvicorn|fastapi)' && echo "$ERROR" | grep -qiE 'command not found|No module named'; then
  hint "Python command failed. Check: which python3. Activate venv: source .venv/bin/activate OR source venv/bin/activate. Create: python3 -m venv .venv"
fi

# pytest ImportError — missing dependency
if echo "$CMD" | grep -qE '^pytest' && echo "$ERROR" | grep -qiE 'ModuleNotFoundError|ImportError'; then
  hint "Pytest import error — missing dependency. Run: pip install -r requirements.txt (or: pip install -e .)"
fi

# Git push auth failure
if echo "$CMD" | grep -qE '^git (push|pull|fetch|clone)' && echo "$ERROR" | grep -qiE 'Authentication failed|403|Permission denied.*publickey|could not read Username'; then
  hint "Git auth failed. Check: gh auth status (for HTTPS) or ssh-add -l (for SSH). Re-auth: gh auth login"
fi

# Port already in use
if echo "$ERROR" | grep -qiE 'EADDRINUSE|address already in use|port.*in use'; then
  PORT=$(echo "$ERROR" | grep -oE ':[0-9]{4,5}' | head -1 | tr -d ':')
  if [ -n "$PORT" ]; then
    hint "Port $PORT in use. Kill it: lsof -ti tcp:$PORT | xargs kill -9"
  else
    hint "Port already in use. Find listening ports: lsof -i -P -n | grep LISTEN"
  fi
fi

# Docker daemon not running
if echo "$CMD" | grep -qE '^docker' && echo "$ERROR" | grep -qiE 'Cannot connect|docker daemon|Is the docker daemon running'; then
  hint "Docker daemon not running. Start it: open -a Docker (Mac) or: sudo systemctl start docker (Linux)"
fi

# jq not found
if echo "$ERROR" | grep -qiE 'command not found.*jq'; then
  hint "jq not installed. Install: brew install jq (Mac) or: sudo apt install jq (Linux)"
fi

exit 0
