#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

profile="${1:-smoke}"
case "$profile" in
  smoke|steps|spike|soak) ;;
  *) printf 'Usage: bash scripts/run-k6-orders.sh [smoke|steps|spike|soak]\n' >&2; exit 2 ;;
esac
run_id="k6-${profile}-$(date -u +%Y%m%dT%H%M%SZ)-${RANDOM}"
mkdir -p .local/k6-results
printf 'RUN_ID=%s\nPROFILE=%s\n' "$run_id" "$profile"
printf 'RESULT_DIRECTORY=.local/k6-results\n'

# Only start the temporary load generator. Do not recreate application services.
# Inherit MSYS_NO_PATHCONV=1 from mimir-compose.sh for Windows Git Bash.
bash scripts/mimir-compose.sh -f compose.load-limits.yaml -f compose.k6.yaml \
  run --rm --no-deps -T \
  -e "PROFILE=$profile" -e "RUN_ID=$run_id" k6 \
  run --out "json=/results/${run_id}.points.json" /scripts/k6-orders.js \
  2>&1 | tee ".local/k6-results/${run_id}.console.log"
