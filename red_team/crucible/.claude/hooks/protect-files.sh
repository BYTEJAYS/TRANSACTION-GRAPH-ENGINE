#!/usr/bin/env bash
# PreToolUse hook — blocks any Edit/Write to protected files before it happens.
# Exit code 2 = hard block. Claude gets the reason and tries a different approach.
# Configure PROTECTED list below for your project.
#
# Wire up in settings.json:
# "PreToolUse": [{ "matcher": "Edit|Write|MultiEdit", "hooks": [{ "type": "command", "command": "~/.claude/hooks/protect-files.sh" }] }]
#
# STDOUT = JSON parsed by Claude. STDERR = debug only. Never plain-echo to stdout.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

[ -z "$FILE_PATH" ] && exit 0

block() {
  printf '{"decision":"block","reason":"%s"}' "$1"
  exit 2
}

# ── Absolute never-touch files ──────────────────────────────────────────────
PROTECTED_EXACT=(
  ".env"
  ".env.local"
  ".env.production"
  ".env.staging"
  "package-lock.json"
  "yarn.lock"
  "pnpm-lock.yaml"
)

# ── Protected directory patterns ────────────────────────────────────────────
PROTECTED_PATTERNS=(
  ".git/"
  "secrets/"
  ".ssh/"
  "migrations/"       # migrations should be reviewed manually, never auto-edited
)

# Check exact filename matches
FILENAME=$(basename "$FILE_PATH")

# .env.example is a template — Claude must be able to write it
[[ "$FILENAME" == ".env.example" ]] && exit 0

for f in "${PROTECTED_EXACT[@]}"; do
  if [ "$FILENAME" = "$f" ]; then
    block "Protected file: $FILE_PATH cannot be edited by Claude. Edit manually if needed."
  fi
done

# Check pattern matches
for pattern in "${PROTECTED_PATTERNS[@]}"; do
  if [[ "/$FILE_PATH/" == *"/$pattern"* ]]; then
    block "Protected path: $FILE_PATH matches pattern '$pattern'. Edit manually if needed."
  fi
done

# Check .env variants (catches .env.test, .env.development, etc.)
if [[ "$FILENAME" == .env* ]]; then
  block "Protected: .env files cannot be edited by Claude. Add new vars to .env.example only."
fi

exit 0
