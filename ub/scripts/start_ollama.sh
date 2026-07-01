#!/usr/bin/env bash
# Start the local Ollama server for UB (Phase 2). Idempotent.
set -e
HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
OLLAMA_BIN="$(command -v ollama || echo "$HOME/.local/bin/ollama")"

if curl -s --max-time 2 "http://${HOST}/api/version" >/dev/null 2>&1; then
  echo "Ollama already running on ${HOST}"
else
  echo "Starting Ollama server ..."
  mkdir -p "$(dirname "$0")/../../logs"
  nohup "$OLLAMA_BIN" serve > "$(dirname "$0")/../../logs/ollama.log" 2>&1 &
  for i in $(seq 1 20); do
    curl -s --max-time 1 "http://${HOST}/api/version" >/dev/null 2>&1 && { echo "up after ${i}s"; break; }
    sleep 0.5
  done
fi

# Ensure UB's models are present
ensure() { "$OLLAMA_BIN" list 2>/dev/null | grep -q "$1" || { echo "pulling $1 ..."; "$OLLAMA_BIN" pull "$1"; }; }
ensure "llama3.1:8b"
ensure "nomic-embed-text"
echo "models:"; "$OLLAMA_BIN" list
