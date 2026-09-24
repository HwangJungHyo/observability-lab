#!/usr/bin/env bash
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
snapshot="${1:?Usage: bash scripts/prepare-mimir-stack.sh .local/images-TIMESTAMP-PID}"
[[ -f "$snapshot/compose.images.lock.yaml" && -f "$snapshot/mimir-image.env" ]] || { echo "Missing image snapshot" >&2; exit 1; }
command -v openssl >/dev/null || { echo "openssl is required (Git Bash normally includes it)" >&2; exit 1; }
mkdir -p .local/mimir
if [[ ! -f .local/mimir/compose.images.lock.yaml ]]; then
  cp "$snapshot/compose.images.lock.yaml" .local/mimir/compose.images.lock.yaml
fi
if [[ ! -f .env.mimir ]]; then
  mimir_image="$(sed -n 's/^MIMIR_IMAGE=//p' "$snapshot/mimir-image.env" | tr -d '\r')"
  [[ "$mimir_image" == "grafana/mimir@sha256:92838f113ba54230014e79bc812e57ca90bb9ebc06e665f59e4f700098c2dd04" ]] || { echo "Unexpected Mimir digest; review snapshot" >&2; exit 1; }
  umask 077
  env_tmp="$(mktemp .env.mimir.tmp.XXXXXX)"
  trap 'rm -f "$env_tmp"' EXIT
  {
    printf 'MIMIR_IMAGE=%s\n' "$mimir_image"
    printf 'MIMIR_CHECK_IMAGE=python:3.12.14-alpine@sha256:4c47124a8391cb7a9f571164147d154777cf012a4ece5f86097130d7a4478111\n'
    printf 'MIMIR_S3_ACCESS_KEY=lab%s\n' "$(openssl rand -hex 8)"
    printf 'MIMIR_S3_SECRET_KEY=%s\n' "$(openssl rand -hex 32)"
  } > "$env_tmp"
  mv "$env_tmp" .env.mimir
  trap - EXIT
fi
git check-ignore -q .env.mimir || { echo ".env.mimir must be ignored by Git" >&2; exit 1; }
bash scripts/mimir-compose.sh config --quiet
bash scripts/mimir-compose.sh --profile checks pull object-store mimir mimir-check
# -modules runs config validation before printing modules; -version alone does not.
bash scripts/mimir-compose.sh run --rm --no-deps mimir \
  -config.file=/etc/mimir/mimir.yaml -config.expand-env=true -modules
printf '\nPASS: stack prepared; no service started. Keep .env.mimir private.\n'
