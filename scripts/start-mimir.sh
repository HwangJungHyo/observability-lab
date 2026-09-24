#!/usr/bin/env bash
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
snapshot="${1:?Usage: bash scripts/start-mimir.sh .local/images-TIMESTAMP-PID}"
bash scripts/prepare-mimir-stack.sh "$snapshot"
bash scripts/mimir-compose.sh up -d --no-deps object-store
bash scripts/mimir-compose.sh run --rm --no-deps mimir-check storage
bash scripts/mimir-compose.sh up -d --no-deps mimir
bash scripts/mimir-compose.sh run --rm --no-deps mimir-check mimir
bash scripts/mimir-compose.sh ps object-store mimir
docker inspect observability-lab-object-store-1 observability-lab-mimir-1 \
  --format '{{.Name}} Image={{.Image}} Memory={{.HostConfig.Memory}} NanoCPUs={{.HostConfig.NanoCpus}}'
printf '\nPASS: S3 CRUD/auth and Mimir ready/query. remote_write is not enabled yet.\n'
