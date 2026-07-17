#!/bin/sh
set -eu
umask 077

backend_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$backend_dir"

mkdir -p backups
chmod 700 backups
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
output="backups/pa_investing-${timestamp}.dump"
temporary=

cleanup() {
  if [ -n "$temporary" ] && [ -e "$temporary" ]; then
    rm -f "$temporary"
  fi
}

trap cleanup 0
trap 'exit 1' HUP INT TERM

if [ -e "$output" ]; then
  printf 'PostgreSQL backup already exists: %s\n' "$output" >&2
  exit 1
fi

temporary=$(mktemp "backups/.pa_investing-${timestamp}.XXXXXX")
chmod 600 "$temporary"

docker compose exec -T postgres \
  pg_dump -U pa_investing -d pa_investing -Fc > "$temporary"

docker compose exec -T postgres \
  pg_restore --list < "$temporary" > /dev/null

mv -n "$temporary" "$output"
if [ -e "$temporary" ]; then
  printf 'PostgreSQL backup already exists: %s\n' "$output" >&2
  exit 1
fi
temporary=

find backups -type f -name 'pa_investing-*.dump' -mtime +30 -delete

printf 'PostgreSQL backup completed: %s\n' "$output"
