#!/usr/bin/env bash
# PostToolUse hook — runs the project test suite after Claude edits source files.
# This is a PROJECT-LEVEL hook. Lives at .claude/hooks/run-tests-on-change.sh
#
# DISABLED BY DEFAULT. To enable:
#   1. chmod +x .claude/hooks/run-tests-on-change.sh
#   2. Uncomment the PostToolUse hook entry in .claude/settings.json
#
# Wire up in .claude/settings.json:
# "PostToolUse": [{
#   "matcher": "Edit|Write|MultiEdit",
#   "hooks": [{ "type": "command", "command": ".claude/hooks/run-tests-on-change.sh" }]
# }]
#
# Exit code: always 0 (PostToolUse cannot block — it only informs)
# STDOUT = JSON parsed by Claude. STDERR = debug only.

FILE="${TOOL_INPUT_FILE_PATH:-}"

# Only run when source or test files are edited
if [ -z "$FILE" ]; then exit 0; fi

# Skip non-source files (config, docs, assets, etc.)
case "$FILE" in
  *.py|*.ts|*.tsx|*.js|*.jsx|*.go|*.rs) ;;  # run tests
  *) exit 0 ;;
esac

# Skip files outside src/ or tests/ directories
if [[ "$FILE" != *"/src/"* ]] && \
   [[ "$FILE" != *"/tests/"* ]] && \
   [[ "$FILE" != *"/test/"* ]] && \
   [[ "$FILE" != *"test_"* ]] && \
   [[ "$FILE" != *".test."* ]] && \
   [[ "$FILE" != *".spec."* ]]; then
  exit 0
fi

run_python_tests() {
  if command -v pytest &>/dev/null; then
    OUTPUT=$(pytest --tb=no -q 2>&1)
    EXIT=$?
  elif python -m pytest --version &>/dev/null 2>&1; then
    OUTPUT=$(python -m pytest --tb=no -q 2>&1)
    EXIT=$?
  else
    exit 0
  fi
}

run_node_tests() {
  if [ -f "package.json" ]; then
    if command -v npx &>/dev/null && npx vitest --version &>/dev/null 2>&1; then
      OUTPUT=$(npx vitest run --reporter=verbose 2>&1)
      EXIT=$?
    elif grep -q '"test"' package.json 2>/dev/null; then
      OUTPUT=$(npm test --silent 2>&1)
      EXIT=$?
    else
      exit 0
    fi
  fi
}

# Detect runtime and run appropriate tests
if [ -f "pyproject.toml" ] || [ -f "setup.py" ] || [ -f "requirements.txt" ]; then
  run_python_tests
elif [ -f "package.json" ]; then
  run_node_tests
else
  exit 0
fi

# Format output for Claude
SUMMARY=$(echo "$OUTPUT" | tail -3)
if [ "${EXIT:-0}" -eq 0 ]; then
  printf '{"output":"Tests passed after edit to %s\\n%s"}' "$FILE" "$SUMMARY"
else
  printf '{"output":"Tests FAILED after edit to %s\\n%s\\nFull output above."}' "$FILE" "$SUMMARY"
fi

exit 0
