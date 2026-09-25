#!/usr/bin/env bash
# Run from Git Bash or Bash. No running service is recreated.
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
mkdir -p .local
lock_dir="$(mktemp -d .local/image-lock.XXXXXX)"
trap 'rm -rf "$lock_dir"' EXIT
printf 'services:\n' > "$lock_dir/compose.images.lock.yaml"
printf 'service\timage_id\trepository_digest\n' > "$lock_dir/images.tsv"

resolve_digest() {
  local image_id="$1" repository="$2" candidate found=""
  while IFS= read -r candidate; do
    candidate="${candidate%$'\r'}"
    case "$candidate" in
      "$repository"@sha256:*|"docker.io/$repository"@sha256:*)
        found="$candidate"; break ;;
    esac
  done < <(docker image inspect "$image_id" --format '{{range .RepoDigests}}{{println .}}{{end}}')
  if [[ -z "$found" ]]; then
    printf 'ERROR: no matching RepoDigest for %s (%s). Stop; do not substitute an image ID.\n' "$repository" "$image_id" >&2
    return 1
  fi
  local resolved
  resolved="$(docker image inspect "$found" --format '{{.Id}}')"
  resolved="${resolved%$'\r'}"
  [[ "$resolved" == "$image_id" ]] || { printf 'ERROR: digest/image ID mismatch\n' >&2; return 1; }
  printf '%s' "$found"
}

for service in prometheus grafana alertmanager; do
  case "$service" in
    prometheus) repository=prom/prometheus ;;
    grafana) repository=grafana/grafana ;;
    alertmanager) repository=prom/alertmanager ;;
  esac
  container="observability-lab-${service}-1"
  image_id="$(docker inspect "$container" --format '{{.Image}}')"
  image_id="${image_id%$'\r'}"
  digest="$(resolve_digest "$image_id" "$repository")"
  printf '  %s:\n    image: "%s"\n' "$service" "$digest" >> "$lock_dir/compose.images.lock.yaml"
  printf '%s\t%s\t%s\n' "$service" "$image_id" "$digest" >> "$lock_dir/images.tsv"
done

# Pull only the new Mimir image; never pull existing :latest images.
docker pull --platform linux/amd64 grafana/mimir:3.2.1
mimir_id="$(docker image inspect grafana/mimir:3.2.1 --format '{{.Id}}')"
mimir_id="${mimir_id%$'\r'}"
mimir_digest="$(resolve_digest "$mimir_id" grafana/mimir)"
docker run --rm --network none --platform linux/amd64 "$mimir_digest" -version
printf 'mimir\t%s\t%s\n' "$mimir_id" "$mimir_digest" >> "$lock_dir/images.tsv"
printf 'MIMIR_IMAGE=%s\n' "$mimir_digest" > "$lock_dir/mimir-image.env"
docker compose -f compose.yaml -f "$lock_dir/compose.images.lock.yaml" config --quiet

# Preserve prior snapshots, then publish only after every check succeeded.
snapshot=".local/images-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mv "$lock_dir" "$snapshot"
trap - EXIT
printf '\nPASS: snapshot=%s\n' "$snapshot"
printf 'The existing containers are unchanged. Mimir server is not started yet.\n'
cat "$snapshot/images.tsv"
