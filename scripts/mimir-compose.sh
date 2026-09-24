#!/usr/bin/env bash
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
exec docker compose --env-file .env.mimir \
  -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml -f compose.traces.yaml \
  -f .local/mimir/compose.images.lock.yaml -f compose.mimir.yaml "$@"
