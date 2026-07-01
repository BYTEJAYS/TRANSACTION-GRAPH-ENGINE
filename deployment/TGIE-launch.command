#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# TGIE one-click launcher (macOS).
# Double-click in Finder, or run from a terminal:
#   ./TGIE-launch.command
#
# Brings up the full stack in dependency order:
#   • PostgreSQL (5432)
#   • Redis (6379)
#   • TGIE backend / FastAPI (8000)
#   • Blue Team API / FastAPI (8001)
#   • Frontend / Vite dev server (3000)
# Then opens the browser. Ctrl+C (or closing the Terminal window) kills
# everything that was started by this script. Already-running services are
# left alone.
# ─────────────────────────────────────────────────────────────────────────────
set -u

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$ROOT/frontend"
BACKEND="$ROOT/backend"
BLUETEAM="$HOME/bling-blue-team"
MINIFORGE="$HOME/miniforge3"
PGDATA="$HOME/pgdata"
REDIS_DATA="$HOME/redis-data"
LOG_DIR="$HOME/.tgie-logs"
PID_FILE="$LOG_DIR/pids"
mkdir -p "$LOG_DIR"
: > "$PID_FILE"

export PATH="$MINIFORGE/bin:$PATH"

# ── Colors ────────────────────────────────────────────────────────────────────
B='\033[1m';   D='\033[2m';   N='\033[0m'
CY='\033[1;36m'; GR='\033[1;32m'; YE='\033[1;33m'; RE='\033[1;31m'; GY='\033[0;37m'

log()  { printf "%b[TGIE]%b  %s\n"   "$CY" "$N" "$*"; }
ok()   { printf "%b[OK]%b    %s\n"   "$GR" "$N" "$*"; }
warn() { printf "%b[WARN]%b  %s\n"   "$YE" "$N" "$*"; }
err()  { printf "%b[ERR]%b   %s\n"   "$RE" "$N" "$*"; }
hr()   { printf "%b%s%b\n" "$GY" "──────────────────────────────────────────────────────────────────────" "$N"; }

# ── Cleanup ───────────────────────────────────────────────────────────────────
# Whatever this script starts goes into PID_FILE. On exit, kill them all.
# Long-running shared services (Postgres / Redis) are NOT killed here so they
# remain available for other tools / IDE extensions.
OWNED_PIDS=()
record_pid() { OWNED_PIDS+=("$1"); echo "$1" >> "$PID_FILE"; }

cleanup() {
  printf "\n"
  log "Shutting down (Ctrl+C received)…"
  for pid in "${OWNED_PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null
      ok "stopped pid $pid"
    fi
  done
  : > "$PID_FILE"
  log "All TGIE processes stopped. Postgres and Redis left running."
  printf "%bClose this window when ready.%b\n" "$D" "$N"
  # If launched from Finder, keep the window open so the user can read.
  if [ -t 0 ]; then
    read -r -p "Press Enter to exit." _ || true
  fi
}
trap cleanup EXIT INT TERM

# ── Helpers ───────────────────────────────────────────────────────────────────
port_listening() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

wait_port() {                              # wait_port <port> <label> [timeout_secs]
  local port="$1" label="$2" timeout="${3:-20}" t=0
  while ! port_listening "$port"; do
    sleep 0.5; t=$((t+1))
    if [ "$t" -ge "$((timeout * 2))" ]; then
      err "$label did not bind to :$port within ${timeout}s — check $LOG_DIR"
      return 1
    fi
  done
  return 0
}

# ── Banner ────────────────────────────────────────────────────────────────────
clear
printf "%b" "$CY"
cat <<'BANNER'
 ┌────────────────────────────────────────────────────────────────────┐
 │   T G I E    ·    Transaction Graph Intelligence Engine            │
 │   one-click launcher — full stack + UB voice copilot               │
 └────────────────────────────────────────────────────────────────────┘
BANNER
printf "%b" "$N"
hr

# ── Step 1: Postgres ─────────────────────────────────────────────────────────
if port_listening 5432; then
  ok "Postgres already running on :5432"
else
  log "Starting Postgres…"
  pg_ctl -D "$PGDATA" -l "$PGDATA/postgres.log" start >/dev/null
  if wait_port 5432 "Postgres" 15; then ok "Postgres up"; else exit 1; fi
fi

# ── Step 2: Redis ────────────────────────────────────────────────────────────
if port_listening 6379; then
  ok "Redis already running on :6379"
else
  log "Starting Redis…"
  redis-server --port 6379 --daemonize yes --dir "$REDIS_DATA" >/dev/null
  if wait_port 6379 "Redis" 10; then ok "Redis up"; else exit 1; fi
fi

# ── Step 3: TGIE backend (FastAPI :8000) ─────────────────────────────────────
if port_listening 8000; then
  warn "Port 8000 already in use — assuming TGIE backend is up"
else
  log "Starting TGIE backend…"
  if [ ! -d "$BACKEND/.venv" ]; then
    err "Backend venv missing at $BACKEND/.venv — run 'python3 -m venv .venv && pip install -r requirements.txt' first."
    exit 1
  fi
  [ -f "$BACKEND/.env" ] || cp "$BACKEND/.env.example" "$BACKEND/.env"
  ( cd "$BACKEND" \
    && source .venv/bin/activate \
    && exec uvicorn main:app --host 0.0.0.0 --port 8000 \
         >"$LOG_DIR/tgie-backend.log" 2>&1 \
  ) &
  record_pid $!
  if wait_port 8000 "TGIE backend" 30; then ok "TGIE backend up on :8000"; else exit 1; fi
fi

# ── Step 4: Blue Team API (FastAPI :8001) ────────────────────────────────────
if port_listening 8001; then
  warn "Port 8001 already in use — assuming Blue Team is up"
else
  log "Starting Blue Team API…"
  if [ ! -d "$MINIFORGE/envs/blueenv" ]; then
    err "Conda env 'blueenv' missing — run 'conda create -n blueenv python=3.11 && pip install -r requirements.txt' first."
    exit 1
  fi
  ( cd "$BLUETEAM" \
    && exec "$MINIFORGE/envs/blueenv/bin/uvicorn" app.main:app --port 8001 \
         >"$LOG_DIR/blueteam.log" 2>&1 \
  ) &
  record_pid $!
  if wait_port 8001 "Blue Team" 30; then ok "Blue Team up on :8001"; else exit 1; fi
fi

# ── Step 5: Frontend (Vite :3000) ────────────────────────────────────────────
if port_listening 3000; then
  warn "Port 3000 already in use — assuming frontend is up"
else
  log "Starting frontend…"
  if [ ! -d "$FRONTEND/node_modules" ]; then
    log "Installing frontend deps (first run)…"
    ( cd "$FRONTEND" && npm install ) || { err "npm install failed"; exit 1; }
  fi
  ( cd "$FRONTEND" \
    && exec npm run dev \
         >"$LOG_DIR/frontend.log" 2>&1 \
  ) &
  record_pid $!
  if wait_port 3000 "Frontend" 30; then ok "Frontend up on :3000"; else exit 1; fi
fi

# ── Summary + browser ────────────────────────────────────────────────────────
hr
printf "%b ALL SYSTEMS LIVE %b\n" "$GR" "$N"
hr
printf "  %bDashboard %b      http://localhost:3000\n"            "$B" "$N"
printf "  %bTGIE API  %b      http://localhost:8000\n"            "$B" "$N"
printf "  %bBlue Team %b      http://localhost:8001/health\n"     "$B" "$N"
printf "  %bPostgres  %b      localhost:5432  (bling_user / bling_blue)\n" "$B" "$N"
printf "  %bRedis     %b      localhost:6379\n"                    "$B" "$N"
hr
printf "  %bLogs%b      tail -f %s/{frontend,tgie-backend,blueteam}.log\n" "$D" "$N" "$LOG_DIR"
printf "  %bStop%b      Ctrl+C  (or close this window)\n"          "$D" "$N"
hr

sleep 1
log "Opening dashboard in your default browser…"
open "http://localhost:3000" 2>/dev/null || true

# ── Stream the most relevant log so the window isn't dead ────────────────────
printf "\n%b── tailing frontend.log (Ctrl+C to stop the stack) ──%b\n" "$D" "$N"
tail -n 0 -F "$LOG_DIR/frontend.log" "$LOG_DIR/tgie-backend.log" "$LOG_DIR/blueteam.log"
