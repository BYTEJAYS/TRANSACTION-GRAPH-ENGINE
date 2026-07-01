#!/usr/bin/env bash
# TGIE — RESTART: stop everything, then start everything.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

printf "\n\033[1;36m▶ TGIE restart — stopping…\033[0m\n"
bash "$DIR/stop_tgie.command"

printf "\n\033[1;36m▶ TGIE restart — starting…\033[0m\n"
# Don't auto-open twice; the start script opens the browser.
bash "$DIR/start_tgie.command"
