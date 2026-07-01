#!/usr/bin/env bash
# PreToolUse hook — blocks genuinely dangerous commands before they run.
# Exit code 2 = block the command entirely and tell Claude why.
# Exit code 0 = allow the command to proceed.
# IMPORTANT: Only stdout goes to Claude. Use stderr for debug. Never echo to stdout.

# Parse command from stdin JSON (consistent with other hooks), fallback to env var
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$COMMAND" ] && COMMAND="${TOOL_INPUT_COMMAND:-}"

block() {
  printf '{"decision":"block","reason":"%s"}' "$1"
  exit 2
}

# Block force push — this is the #1 accidental catastrophe
if echo "$COMMAND" | grep -qE 'git push.*(--force|-f)'; then
  block "Force push blocked. Never force-push from Claude. Do this manually if you are certain."
fi

# Block pipe-to-bash — executing remote scripts is always a security risk
if echo "$COMMAND" | grep -qE '(curl|wget).*\|\s*(bash|sh)'; then
  block "Pipe-to-bash blocked. Never execute remote scripts directly. Download first, inspect, then run."
fi

# Block recursive force remove on root or home
if echo "$COMMAND" | grep -qE 'rm\s+-rf\s+(\/|~|\/home|\/root)'; then
  block "Recursive remove on system directory blocked."
fi

# Block disk format commands
if echo "$COMMAND" | grep -qE '^(mkfs|dd if=)'; then
  block "Disk format command blocked."
fi

# Block hard reset — silently destroys all uncommitted work
if echo "$COMMAND" | grep -qE 'git reset --hard'; then
  block "git reset --hard blocked — this permanently discards all uncommitted work. Run manually if certain."
fi

# Block git checkout -- which silently restores tracked files to last commit
if echo "$COMMAND" | grep -qE 'git checkout -- '; then
  block "git checkout -- blocked — this discards working tree changes. Run manually if certain."
fi

# Block git clean which permanently deletes untracked files
if echo "$COMMAND" | grep -qE 'git clean -[a-z]*f'; then
  block "git clean -f blocked — this permanently deletes untracked files. Run manually if certain."
fi

exit 0
