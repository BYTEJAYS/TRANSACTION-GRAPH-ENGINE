#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# TGIE control — shared library (sourced by start/stop/status/restart .command)
# Manual control suite: nothing auto-starts; these scripts are the only launcher.
# ──────────────────────────────────────────────────────────────────────────────

# Resolve locations from THIS file (works no matter where double-clicked from).
LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTROL_DIR="$LIB_DIR"
TGIE_ROOT="$(cd "$CONTROL_DIR/.." && pwd)"
PID_DIR="$CONTROL_DIR/pids"
LOG_DIR="$TGIE_ROOT/logs"
mkdir -p "$PID_DIR" "$LOG_DIR"

# ── Ports ─────────────────────────────────────────────────────────────────────
OLLAMA_PORT=11434
UB_PORT=8001
BACKEND_PORT=8000
FRONTEND_PORT=3000

# ── Toolchain (override via env if your paths differ) ─────────────────────────
# Python: the local 3.14 can't build scipy, so default to the working venv used to
# host TGIE. Override with TGIE_PYTHON=/path/to/python.
DEFAULT_VENV_PY="/Users/bytejay/transaction-graph-intelligence/backend/.venv/bin/python"
PYTHON="${TGIE_PYTHON:-$DEFAULT_VENV_PY}"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3 || echo python3)"

# Ensure user-local + nvm bins are on PATH (double-clicked .command has a minimal PATH).
export PATH="$HOME/.local/bin:$PATH"
OLLAMA_BIN="${TGIE_OLLAMA:-$(command -v ollama || echo "$HOME/.local/bin/ollama")}"
if ! command -v npm >/dev/null 2>&1; then
  _nvm_npm="$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | sort -V | tail -1)"
  [ -n "$_nvm_npm" ] && export PATH="$_nvm_npm:$PATH"
fi

# ── Colors ────────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
  RED=$'\033[0;31m'; GRN=$'\033[0;32m'; YLW=$'\033[1;33m'; BLU=$'\033[0;34m'
  CYN=$'\033[0;36m'; BLD=$'\033[1m'; DIM=$'\033[2m'; NC=$'\033[0m'
else
  RED=; GRN=; YLW=; BLU=; CYN=; BLD=; DIM=; NC=
fi
ok()   { printf "  ${GRN}✓${NC} %s\n" "$1"; }
warn() { printf "  ${YLW}!${NC} %s\n" "$1"; }
err()  { printf "  ${RED}✗${NC} %s\n" "$1"; }
info() { printf "  ${DIM}%s${NC}\n" "$1"; }
hr()   { printf "${DIM}────────────────────────────────────────────────────────────${NC}\n"; }
banner() { printf "\n${BLD}${CYN}%s${NC}\n" "$1"; hr; }

# ── Process / port helpers ────────────────────────────────────────────────────
port_pids() { lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null; }      # PIDs LISTENING on a port
port_up()   { [ -n "$(port_pids "$1")" ]; }
http_ok()   { curl -s -o /dev/null --max-time 2 "$1" 2>/dev/null; }
pid_alive() { [ -n "$1" ] && kill -0 "$1" 2>/dev/null; }

read_pid() { [ -f "$PID_DIR/$1.pid" ] && cat "$PID_DIR/$1.pid" 2>/dev/null || true; }
write_pid() { echo "$2" > "$PID_DIR/$1.pid"; }
clear_pid() { rm -f "$PID_DIR/$1.pid"; }

# Wait until an HTTP endpoint answers (or a port listens). $1=url $2=label $3=timeout_s
wait_http() {
  local url="$1" label="$2" timeout="${3:-40}" i=0
  while [ "$i" -lt "$timeout" ]; do
    if http_ok "$url"; then ok "$label healthy"; return 0; fi
    sleep 1; i=$((i+1))
    [ $((i % 5)) -eq 0 ] && info "waiting for $label … ${i}s"
  done
  err "$label did not become healthy within ${timeout}s (see $LOG_DIR)"; return 1
}

# Launch a shell command in the background and record the REAL server PID.
# We wrap with `bash -c "exec <cmd>"` so the wrapper is REPLACED by the target
# process — $! is then the actual server pid (accurate PID files). No command
# substitution, so the launcher never blocks waiting on a pipe.
# Usage: spawn_sh <name> <logfile> "<shell command string>"
spawn_sh() {
  local name="$1" logfile="$2" cmd="$3"
  # cmd supplies its own `exec` (after any `cd`) so the wrapper bash is replaced by
  # the real server → accurate PID. (Don't prepend exec here: cmds may start with `cd`.)
  nohup bash -c "$cmd" >"$logfile" 2>&1 &
  local p=$!
  disown "$p" 2>/dev/null || true
  write_pid "$name" "$p"
}

# Stop a service gracefully then forcefully. $1=name $2=label $3=port(optional)
# Targets the recorded PID *and* whatever is actually LISTENING on the port, so a
# stale/wrapper PID file can never leave the real server running.
stop_service() {
  local name="$1" label="$2" port="${3:-}" pid; pid="$(read_pid "$name")"
  local targets; targets="$(printf '%s\n' $pid $( [ -n "$port" ] && port_pids "$port" ) \
                            | grep -E '^[0-9]+$' | sort -u)"
  if [ -z "$targets" ]; then info "$label not running"; clear_pid "$name"; return; fi
  info "stopping $label (pids: $(echo $targets | tr '\n' ' ')) …"
  local p
  for p in $targets; do pkill -TERM -P "$p" 2>/dev/null || true; kill -TERM "$p" 2>/dev/null || true; done
  local i=0 alive=1
  while [ "$i" -lt 6 ]; do
    alive=0; for p in $targets; do pid_alive "$p" && alive=1; done
    [ "$alive" -eq 0 ] && break; sleep 0.5; i=$((i+1))
  done
  for p in $targets; do
    pid_alive "$p" && { warn "$label pid $p didn't exit — force killing"; \
                        pkill -KILL -P "$p" 2>/dev/null || true; kill -KILL "$p" 2>/dev/null || true; }
  done
  ok "$label stopped"
  clear_pid "$name"
}

# Pattern-scoped orphan sweep (catches instances started outside the PID files).
kill_pattern() { pkill -f "$1" 2>/dev/null && warn "swept orphans matching: $1" || true; }

mem_mb() { # RSS in MB for a pid
  local pid="$1" rss
  rss="$(ps -o rss= -p "$pid" 2>/dev/null | tr -d ' ')"
  [ -n "$rss" ] && echo "$(( rss / 1024 )) MB" || echo "—"
}

# Resolved component → port map used by status
COMPONENTS=("Ollama:$OLLAMA_PORT:ollama" "UB:$UB_PORT:ub" "Backend:$BACKEND_PORT:backend" "Frontend:$FRONTEND_PORT:frontend")
