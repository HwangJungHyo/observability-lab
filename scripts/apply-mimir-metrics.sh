#!/usr/bin/env bash
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
bash scripts/mimir-compose.sh config --quiet
mkdir -p .local/mimir
backup=".local/mimir/prometheus-before-remote-write.yaml"
if [[ ! -f "$backup" ]]; then
  temp_backup="$(mktemp .local/mimir/effective-config.XXXXXX)"
  trap 'rm -f "$temp_backup"' EXIT
  bash scripts/mimir-compose.sh exec -T order-api python -c \
    'import json,urllib.request; print(json.load(urllib.request.urlopen("http://prometheus:9090/api/v1/status/config",timeout=5))["data"]["yaml"],end="")' > "$temp_backup"
  [[ -s "$temp_backup" ]] || { echo "Empty active-config backup" >&2; exit 1; }
  mv "$temp_backup" "$backup"
  trap - EXIT
fi
# A Git checkout can replace a file inode. Verify what the container actually sees.
mounted="$(mktemp .local/mimir/mounted-config.XXXXXX)"
trap 'rm -f "$mounted"' EXIT
bash scripts/mimir-compose.sh exec -T prometheus cat /etc/prometheus/prometheus.yml > "$mounted"
if ! diff -q --strip-trailing-cr prometheus.yml "$mounted" >/dev/null; then
  echo "FAIL: mounted Prometheus config differs from host file. Do not reload; report this output." >&2
  exit 1
fi
bash scripts/mimir-compose.sh exec -T prometheus promtool check config /etc/prometheus/prometheus.yml
bash scripts/mimir-compose.sh kill -s SIGHUP prometheus
bash scripts/mimir-compose.sh exec -T order-api python - < scripts/check_mimir_metrics.py
printf '\nPASS: remote_write verified. Next, register Mimir in Grafana with a Grafana-only restart.\n'
