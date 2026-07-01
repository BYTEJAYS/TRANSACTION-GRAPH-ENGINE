#!/usr/bin/env bash
# Launch the BELS standalone service from the TGIE root.
set -euo pipefail
cd "$(dirname "$0")/.."   # → ~/Desktop/TGIE
echo "⛓  Starting BELS on http://localhost:${BELS_PORT:-8200}  (provider=${BELS_PROVIDER:-internal})"
exec python3 -m bels.main
