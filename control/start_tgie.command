#!/usr/bin/env bash
# TGIE — START everything, in order. Double-click in Finder or run from a terminal.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

printf "\n${BLD}${CYN}╔══════════════════════════════════════════╗${NC}\n"
printf   "${BLD}${CYN}║   TGIE  ·  manual start                  ║${NC}\n"
printf   "${BLD}${CYN}╚══════════════════════════════════════════╝${NC}\n"
info "root: $TGIE_ROOT"
info "python: $PYTHON"

FAIL=0

# ── 1. Ollama ─────────────────────────────────────────────────────────────────
banner "1/4  Ollama  (:$OLLAMA_PORT)"
if port_up "$OLLAMA_PORT"; then
  ok "Ollama already running"; write_pid ollama "$(port_pids "$OLLAMA_PORT" | head -1)"
else
  [ -x "$OLLAMA_BIN" ] || command -v ollama >/dev/null || { err "ollama not found (set TGIE_OLLAMA)"; FAIL=1; }
  spawn_sh ollama "$LOG_DIR/ollama.log" "exec '$OLLAMA_BIN' serve"
  info "launched ollama (pid $(read_pid ollama))"
  wait_http "http://localhost:$OLLAMA_PORT/api/version" "Ollama" 30 || FAIL=1
fi
# Make sure UB's models exist (warn only — pulling is the user's call)
if port_up "$OLLAMA_PORT"; then
  have_models="$("$OLLAMA_BIN" list 2>/dev/null)"
  echo "$have_models" | grep -q "llama3.1:8b"       || warn "model llama3.1:8b not pulled (ollama pull llama3.1:8b)"
  echo "$have_models" | grep -q "nomic-embed-text"  || warn "model nomic-embed-text not pulled (ollama pull nomic-embed-text)"
fi

# ── 2. UB service ─────────────────────────────────────────────────────────────
banner "2/4  UB · Universal Brain  (:$UB_PORT)"
if port_up "$UB_PORT"; then
  ok "UB already running"; write_pid ub "$(port_pids "$UB_PORT" | head -1)"
else
  spawn_sh ub "$LOG_DIR/ub.log" \
    "cd '$TGIE_ROOT/backend' && exec env PYTHONPATH='$TGIE_ROOT/backend' UB_PORT='$UB_PORT' '$PYTHON' -m ub_service"
  info "launched UB (pid $(read_pid ub))"
  wait_http "http://localhost:$UB_PORT/ub/health" "UB" 40 || { warn "UB not healthy — is Ollama up + index built (python -m ub index)?"; FAIL=1; }
fi

# ── 3. Backend ────────────────────────────────────────────────────────────────
banner "3/4  TGIE Backend  (:$BACKEND_PORT)"
if port_up "$BACKEND_PORT"; then
  ok "Backend already running"; write_pid backend "$(port_pids "$BACKEND_PORT" | head -1)"
else
  spawn_sh backend "$LOG_DIR/backend.log" \
    "cd '$TGIE_ROOT/backend' && exec env PYTHONPATH='$TGIE_ROOT/backend' ENABLE_REDTEAM_PANEL=1 '$PYTHON' -m uvicorn main:app --host 0.0.0.0 --port $BACKEND_PORT --log-level warning"
  info "launched backend (pid $(read_pid backend))"
  wait_http "http://localhost:$BACKEND_PORT/health" "Backend" 40 || FAIL=1
fi

# ── 4. Frontend ───────────────────────────────────────────────────────────────
banner "4/4  TGIE Frontend  (:$FRONTEND_PORT)"
if port_up "$FRONTEND_PORT"; then
  ok "Frontend already running"; write_pid frontend "$(port_pids "$FRONTEND_PORT" | head -1)"
else
  if ! command -v npm >/dev/null 2>&1; then
    err "npm not found on PATH — install Node or add it (nvm). Skipping frontend."; FAIL=1
  else
    spawn_sh frontend "$LOG_DIR/frontend.log" "cd '$TGIE_ROOT/frontend' && exec npm run dev"
    info "launched frontend (pid $(read_pid frontend))"
    wait_http "http://localhost:$FRONTEND_PORT" "Frontend" 40 || FAIL=1
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
banner "TGIE status"
fmt() { port_up "$2" && printf "  ${GRN}● %-9s${NC} %s\n" "$1" "$3" || printf "  ${RED}○ %-9s${NC} stopped\n" "$1"; }
fmt "Ollama"   "$OLLAMA_PORT"   "running  ·  http://localhost:$OLLAMA_PORT"
fmt "UB"       "$UB_PORT"       "running  ·  http://localhost:$UB_PORT/ub/health"
fmt "Backend"  "$BACKEND_PORT"  "running  ·  http://localhost:$BACKEND_PORT"
fmt "Frontend" "$FRONTEND_PORT" "running  ·  http://localhost:$FRONTEND_PORT"
hr

if [ "$FAIL" -eq 0 ]; then
  printf "\n${BLD}${GRN}TGIE STARTED SUCCESSFULLY${NC}\n"
  printf "  ${DIM}Frontend${NC}  http://localhost:$FRONTEND_PORT\n"
  printf "  ${DIM}Dashboard${NC} http://localhost:$FRONTEND_PORT/ub_dashboard/index.html\n"
  printf "  ${DIM}Backend${NC}   http://localhost:$BACKEND_PORT/docs\n"
  # Open the frontend (optional). Set TGIE_NO_OPEN=1 to skip.
  [ "${TGIE_NO_OPEN:-0}" = "1" ] || { sleep 1; open "http://localhost:$FRONTEND_PORT" 2>/dev/null || true; }
else
  printf "\n${BLD}${YLW}TGIE STARTED WITH WARNINGS${NC} — check $LOG_DIR/*.log and run status_tgie.command\n"
fi
printf "\n${DIM}(leave this window open; run stop_tgie.command to shut everything down)${NC}\n\n"
