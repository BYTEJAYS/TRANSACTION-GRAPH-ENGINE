#!/usr/bin/env bash
# PostToolUse hook — auto-formats the file Claude just edited.
# Detects project type and runs the right formatter automatically.
# Runs AFTER the edit so it cannot block — it just cleans up.
# Keep this fast (under 2 seconds). Heavy tasks belong elsewhere.
# IMPORTANT: Only stdout goes to Claude. Use stderr for debug. Never echo to stdout.

FILE="${TOOL_INPUT_FILE_PATH:-}"

# Nothing to format if no file path
[ -z "$FILE" ] && exit 0

# Skip non-existent files and binary files
[ ! -f "$FILE" ] && exit 0

EXT="${FILE##*.}"

format_python() {
  if command -v ruff &>/dev/null; then
    ruff format "$FILE" 2>/dev/null || true
  elif command -v black &>/dev/null; then
    black --quiet "$FILE" 2>/dev/null || true
  fi
}

format_js_ts() {
  if command -v prettier &>/dev/null; then
    prettier --write "$FILE" 2>/dev/null || true
  elif command -v biome &>/dev/null; then
    biome format --write "$FILE" 2>/dev/null || true
  fi
}

format_go() {
  if command -v gofmt &>/dev/null; then
    gofmt -w "$FILE" 2>/dev/null || true
  fi
}

format_rust() {
  if command -v rustfmt &>/dev/null; then
    rustfmt "$FILE" 2>/dev/null || true
  fi
}

case "$EXT" in
  py)              format_python ;;
  js|jsx|mjs|cjs)  format_js_ts ;;
  ts|tsx)          format_js_ts ;;
  json)            format_js_ts ;;
  go)              format_go ;;
  rs)              format_rust ;;
  *)               exit 0 ;;
esac

exit 0
