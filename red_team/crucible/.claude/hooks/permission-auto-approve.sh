#!/usr/bin/env bash
# PermissionRequest hook — auto-approves MCP tool calls from trusted servers.
# Removes the confirmation dialog when Claude uses GitHub, Playwright, etc.
#
# How it works: reads the tool_name from stdin JSON.
# If tool starts with "mcp__" (i.e., any MCP server call), output approval JSON.
# If not an MCP call, exit 0 silently — let normal permission flow handle it.
#
# Wire up in settings.json:
# "PermissionRequest": [{ "hooks": [{ "type": "command", "command": "~/.claude/hooks/permission-auto-approve.sh" }] }]

if ! command -v jq &>/dev/null; then
  exit 0
fi

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)

# Auto-approve all MCP server tool calls
if [[ "$TOOL_NAME" == mcp__* ]]; then
  printf '{"hookSpecificOutput":{"decision":{"behavior":"allow"}}}\n'
fi

exit 0
