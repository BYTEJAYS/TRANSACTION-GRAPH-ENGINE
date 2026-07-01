#!/usr/bin/env bash
# TGIE — STOP everything cleanly (reverse order), then sweep orphans + verify.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

printf "\n${BLD}${CYN}╔══════════════════════════════════════════╗${NC}\n"
printf   "${BLD}${CYN}║   TGIE  ·  manual stop                   ║${NC}\n"
printf   "${BLD}${CYN}╚══════════════════════════════════════════╝${NC}\n"

# ── Graceful stop by PID file (reverse of start order) ────────────────────────
banner "Stopping services"
stop_service frontend "Frontend" "$FRONTEND_PORT"
stop_service backend  "Backend"  "$BACKEND_PORT"
stop_service ub        "UB"       "$UB_PORT"
stop_service ollama    "Ollama"   "$OLLAMA_PORT"

# ── Orphan sweep (scoped to THIS workspace so we never touch unrelated procs) ──
banner "Sweeping orphans"
kill_pattern "$TGIE_ROOT/frontend"                          # vite/node for this frontend
kill_pattern "vite --port $FRONTEND_PORT"
kill_pattern "uvicorn main:app --host 0.0.0.0 --port $BACKEND_PORT"
kill_pattern "ub_service"                                   # standalone UB
kill_pattern "ollama serve"                                 # ollama server
sleep 1

# ── Verify shutdown ───────────────────────────────────────────────────────────
banner "Verifying shutdown"
STILL=0
for entry in "${COMPONENTS[@]}"; do
  IFS=':' read -r label port _ <<< "$entry"
  if port_up "$port"; then
    err "$label still listening on :$port (pids: $(port_pids "$port" | tr '\n' ' '))"; STILL=1
  else
    ok "$label port :$port free"
  fi
done
# any straggler TGIE python/node?
strag="$(pgrep -fl "ub_service|uvicorn main:app|$TGIE_ROOT/frontend|ollama serve" 2>/dev/null | grep -v "$$" || true)"
[ -n "$strag" ] && { warn "stragglers:"; echo "$strag" | sed 's/^/      /'; STILL=1; }

rm -f "$PID_DIR"/*.pid 2>/dev/null || true
hr
if [ "$STILL" -eq 0 ]; then
  printf "\n${BLD}${GRN}TGIE STOPPED SUCCESSFULLY${NC}\n"
  printf "  All TGIE services have been terminated.\n\n"
else
  printf "\n${BLD}${YLW}TGIE STOP INCOMPLETE${NC} — some processes survived (see above).\n"
  printf "  Re-run this script, or inspect with status_tgie.command.\n\n"
fi
