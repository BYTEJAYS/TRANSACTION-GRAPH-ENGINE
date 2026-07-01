#!/usr/bin/env bash
# Stops the entire TGIE stack — useful when the launcher window was closed
# uncleanly and processes are still hanging around.
set -u
export PATH="$HOME/miniforge3/bin:$PATH"

CY='\033[1;36m'; GR='\033[1;32m'; YE='\033[1;33m'; RE='\033[1;31m'; N='\033[0m'
log() { printf "%b[TGIE]%b %s\n" "$CY" "$N" "$*"; }
ok()  { printf "%b[OK]%b   %s\n" "$GR" "$N" "$*"; }
warn(){ printf "%b[WARN]%b %s\n" "$YE" "$N" "$*"; }

kill_port() {
  local port="$1" label="$2" pids
  pids=$(lsof -ti:"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    kill $pids 2>/dev/null && ok "$label (:$port) stopped"
  else
    warn "$label (:$port) was not running"
  fi
}

log "Stopping application services…"
kill_port 3000 "Frontend"
kill_port 8001 "Blue Team"
kill_port 8000 "TGIE backend"

log "Stopping data services…"
redis-cli shutdown 2>/dev/null && ok "Redis stopped" || warn "Redis was not running"
pg_ctl -D "$HOME/pgdata" stop -m fast 2>/dev/null && ok "Postgres stopped" || warn "Postgres was not running"

ok "All TGIE services down."
read -r -p "Press Enter to close." _ || true
