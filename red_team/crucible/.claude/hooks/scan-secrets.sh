#!/usr/bin/env bash
# PreToolUse hook — scans file content for secrets before Claude writes it.
# Catches API keys, tokens, passwords hardcoded in source files.
# Exit code 2 = block the write. Claude gets the reason and removes the secret.
#
# Wire up in settings.json:
# "PreToolUse": [{ "matcher": "Write|Edit|MultiEdit", "hooks": [{ "type": "command", "command": "~/.claude/hooks/scan-secrets.sh" }] }]
#
# STDOUT = JSON parsed by Claude. STDERR = debug only. Never plain-echo to stdout.

if ! command -v jq &>/dev/null; then
  echo "scan-secrets: jq not installed, secret scan skipped" >&2
  exit 0
fi

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // empty' 2>/dev/null)

[ -z "$CONTENT" ] && exit 0

# Skip test and fixture files where dummy credentials are normal
if [[ "$FILE_PATH" =~ \.(test|spec)\.[a-z]+$ ]] || \
   [[ "$FILE_PATH" =~ /test_[^/]+\.py$ ]] || \
   [[ "$FILE_PATH" =~ /__tests__/ ]]; then
  exit 0
fi

block() {
  printf '{"decision":"block","reason":"Secret detected in %s: %s. Use environment variables instead. Never hardcode secrets."}' "$FILE_PATH" "$1"
  exit 2
}

# ── Secret patterns ──────────────────────────────────────────────────────────
# These regexes match common secret formats. Tuned to reduce false positives.

# Generic high-entropy assignment patterns
if echo "$CONTENT" | grep -qiE '(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[=:]\s*["\x27][A-Za-z0-9+/]{20,}'; then
  block "API key or token assignment"
fi

# AWS credentials
if echo "$CONTENT" | grep -qE 'AKIA[0-9A-Z]{16}'; then
  block "AWS Access Key ID"
fi
if echo "$CONTENT" | grep -qE '[A-Za-z0-9/+=]{40}' && echo "$CONTENT" | grep -qi 'aws_secret'; then
  block "AWS Secret Access Key"
fi

# Anthropic / OpenAI keys
if echo "$CONTENT" | grep -qE 'sk-ant-[A-Za-z0-9_-]{20,}'; then
  block "Anthropic API key"
fi
if echo "$CONTENT" | grep -qE 'sk-[A-Za-z0-9]{48}'; then
  block "OpenAI API key"
fi

# GitHub tokens
if echo "$CONTENT" | grep -qE 'gh[pousr]_[A-Za-z0-9]{36,}'; then
  block "GitHub token"
fi

# Stripe keys
if echo "$CONTENT" | grep -qE 'sk_live_[A-Za-z0-9]{24,}'; then
  block "Stripe live secret key"
fi

# JWT tokens (header.payload.signature pattern)
if echo "$CONTENT" | grep -qE 'eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'; then
  block "JWT token (appears to be a real token, not a placeholder)"
fi

# Slack tokens
if echo "$CONTENT" | grep -qE 'xox[bpoa]-[A-Za-z0-9\-]{10,}'; then
  block "Slack API token"
fi

# Generic password assignment
if echo "$CONTENT" | grep -qiE 'password\s*[=:]\s*["\x27][^"\x27]{8,}["\x27]' && \
   ! echo "$CONTENT" | grep -qiE 'password\s*[=:]\s*["\x27](your|placeholder|example|changeme|xxx|test|dummy)'; then
  block "Hardcoded password"
fi

# Private key blocks (use -- to prevent grep treating dashes as flags)
if echo "$CONTENT" | grep -qF -- '-----BEGIN PRIVATE KEY-----' || \
   echo "$CONTENT" | grep -qF -- '-----BEGIN RSA PRIVATE KEY-----' || \
   echo "$CONTENT" | grep -qF -- '-----BEGIN EC PRIVATE KEY-----' || \
   echo "$CONTENT" | grep -qF -- '-----BEGIN OPENSSH PRIVATE KEY-----'; then
  block "Private key block"
fi

exit 0
