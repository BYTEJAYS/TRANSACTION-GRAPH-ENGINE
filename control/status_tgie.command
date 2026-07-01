#!/usr/bin/env bash
# TGIE — STATUS: per-component running/stopped, port, PID, memory.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

printf "\n${BLD}${CYN}TGIE status${NC}   ${DIM}%s${NC}\n" "$(date '+%Y-%m-%d %H:%M:%S')"
hr
printf "  ${BLD}%-10s %-9s %-7s %-8s %s${NC}\n" "COMPONENT" "STATE" "PORT" "PID" "MEMORY"
hr

UP=0; DOWN=0
for entry in "${COMPONENTS[@]}"; do
  IFS=':' read -r label port name <<< "$entry"
  # prefer the listening pid (authoritative); fall back to the recorded pid file
  pid="$(port_pids "$port" | head -1)"; [ -z "$pid" ] && pid="$(read_pid "$name")"
  if port_up "$port" && pid_alive "$pid"; then
    printf "  ${GRN}%-10s ● %-7s${NC} %-7s %-8s %s\n" "$label" "running" "$port" "$pid" "$(mem_mb "$pid")"
    UP=$((UP+1))
  elif port_up "$port"; then
    printf "  ${GRN}%-10s ● %-7s${NC} %-7s %-8s %s\n" "$label" "running" "$port" "?" "—"
    UP=$((UP+1))
  else
    printf "  ${RED}%-10s ○ %-7s${NC} %-7s %-8s %s\n" "$label" "stopped" "$port" "—" "—"
    DOWN=$((DOWN+1))
  fi
done
hr

# Ollama model + knowledge index health (best effort)
if port_up "$OLLAMA_PORT"; then
  models="$("$OLLAMA_BIN" list 2>/dev/null | awk 'NR>1{print $1}' | tr '\n' ' ')"
  info "ollama models: ${models:-none}"
fi
if port_up "$UB_PORT"; then
  ctx="$(curl -s --max-time 2 "http://localhost:$UB_PORT/ub/context" 2>/dev/null)"
  if [ -n "$ctx" ]; then
    files="$(echo "$ctx" | sed -n 's/.*"file_count": *\([0-9]*\).*/\1/p' | head -1)"
    chunks="$(echo "$ctx" | sed -n 's/.*"chunk_count": *\([0-9]*\).*/\1/p' | head -1)"
    info "UB knowledge index: ${files:-?} files · ${chunks:-?} chunks"
  fi
fi

printf "\n  ${BLD}%s up · %s down${NC}\n" "$UP" "$DOWN"
[ "$UP" -eq 4 ] && printf "  ${GRN}All TGIE services running.${NC}\n\n" || \
  printf "  ${DIM}Run start_tgie.command to launch what's stopped.${NC}\n\n"
