#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colors ─────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${CYAN}[TGIE]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}   $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail() { echo -e "${RED}[ERR]${NC}  $*"; exit 1; }

# ── Backend ─────────────────────────────────────────────────────────────────
start_backend() {
  log "Starting backend (FastAPI + simulation engine)..."
  cd "$ROOT/backend"

  if [ ! -d ".venv" ]; then
    log "Creating Python virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -q --upgrade pip
    pip install -q fastapi "uvicorn[standard]" websockets pydantic pydantic-settings \
      networkx scipy scikit-learn numpy pandas shap faker orjson python-dateutil aiokafka
  else
    source .venv/bin/activate
  fi

  [ -f ".env" ] || cp .env.example .env

  log "Backend starting on http://localhost:8000"
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
  BACKEND_PID=$!
  echo $BACKEND_PID > /tmp/tgie_backend.pid
  ok "Backend PID: $BACKEND_PID"
}

# ── Frontend ─────────────────────────────────────────────────────────────────
start_frontend() {
  log "Starting frontend (React + Vite)..."
  cd "$ROOT/frontend"

  if ! command -v node &>/dev/null; then
    warn "Node.js not found. Install from https://nodejs.org/"
    warn "Frontend will not start — backend is still running."
    return
  fi

  if [ ! -d "node_modules" ]; then
    log "Installing npm packages..."
    npm install
  fi

  log "Frontend starting on http://localhost:3000"
  npm run dev &
  FRONTEND_PID=$!
  echo $FRONTEND_PID > /tmp/tgie_frontend.pid
  ok "Frontend PID: $FRONTEND_PID"
}

# ── Cleanup on exit ────────────────────────────────────────────────────────
cleanup() {
  log "Shutting down..."
  [ -f /tmp/tgie_backend.pid ]  && kill "$(cat /tmp/tgie_backend.pid)"  2>/dev/null
  [ -f /tmp/tgie_frontend.pid ] && kill "$(cat /tmp/tgie_frontend.pid)" 2>/dev/null
  rm -f /tmp/tgie_backend.pid /tmp/tgie_frontend.pid
}
trap cleanup EXIT INT TERM

# ── Main ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║    Transaction Graph Intelligence Engine (TGIE)      ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

start_backend
start_frontend

echo ""
ok "System starting up!"
echo ""
echo -e "  ${CYAN}→${NC} API Docs:  http://localhost:8000/docs"
echo -e "  ${CYAN}→${NC} Frontend: http://localhost:3000"
echo -e "  ${CYAN}→${NC} Health:   http://localhost:8000/health"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services.${NC}"
echo ""

# Wait for background processes
wait
