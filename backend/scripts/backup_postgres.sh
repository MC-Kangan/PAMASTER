#!/bin/sh
set -eu

backend_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$backend_dir"

mkdir -p backups
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
output="backups/pa_investing-${timestamp}.dump"

docker compose exec -T postgres \
  pg_dump -U pa_investing -d pa_investing -Fc > "$output"

docker compose exec -T postgres \
  pg_restore --list < "$output" > /dev/null

find backups -type f -name 'pa_investing-*.dump' -mtime +30 -delete

printf 'PostgreSQL backup completed: %s\n' "$output"
