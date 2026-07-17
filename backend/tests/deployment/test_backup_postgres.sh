#!/bin/sh
set -eu

backend_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
source_script="$backend_root/scripts/backup_postgres.sh"
test_root=$(mktemp -d "${TMPDIR:-/tmp}/backup-postgres-tests.XXXXXX")
trap 'rm -rf -- "$test_root"' EXIT HUP INT TERM

timestamp=20260717T120000Z
final_name="pa_investing-${timestamp}.dump"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

assert_equals() {
  expected=$1
  actual=$2
  description=$3
  [ "$actual" = "$expected" ] || fail "$description (expected $expected, got $actual)"
}

assert_no_temporary_dump() {
  backup_dir=$1
  temporary=$(find "$backup_dir" -type f -name '.pa_investing-*' -print)
  [ -z "$temporary" ] || fail "temporary dump was not cleaned up: $temporary"
}

mode_of() {
  path=$1
  if stat -c '%a' "$path" >/dev/null 2>&1; then
    stat -c '%a' "$path"
  else
    stat -f '%Lp' "$path"
  fi
}

new_case() {
  case_name=$1
  case_root="$test_root/$case_name"
  case_backend="$case_root/backend"
  case_bin="$case_root/bin"
  case_log="$case_root/docker.log"

  mkdir -p "$case_backend/scripts" "$case_bin"
  cp "$source_script" "$case_backend/scripts/backup_postgres.sh"
  chmod +x "$case_backend/scripts/backup_postgres.sh"
  : > "$case_log"

  cat > "$case_bin/date" <<'EOF'
#!/bin/sh
printf '%s\n' "${FAKE_TIMESTAMP:?}"
EOF

  cat > "$case_bin/docker" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "${FAKE_DOCKER_LOG:?}"

case " $* " in
  *' pg_dump '*)
    printf '%s' "${FAKE_DUMP_CONTENT:-complete archive}"
    exit "${FAKE_DUMP_STATUS:-0}"
    ;;
  *' pg_restore --list '*)
    archive=$(cat)
    [ "$archive" = "${FAKE_DUMP_CONTENT:-complete archive}" ] || exit 97
    [ ! -e "${FAKE_FINAL_PATH:?}" ] || exit 98
    exit "${FAKE_VALIDATE_STATUS:-0}"
    ;;
  *)
    exit 96
    ;;
esac
EOF

  chmod +x "$case_bin/date" "$case_bin/docker"
}

run_backup() {
  env \
    PATH="$case_bin:$PATH" \
    FAKE_TIMESTAMP="$timestamp" \
    FAKE_DOCKER_LOG="$case_log" \
    FAKE_FINAL_PATH="$case_backend/backups/$final_name" \
    FAKE_DUMP_CONTENT="${fake_dump_content:-complete archive}" \
    FAKE_DUMP_STATUS="${fake_dump_status:-0}" \
    FAKE_VALIDATE_STATUS="${fake_validate_status:-0}" \
    "$case_backend/scripts/backup_postgres.sh"
}

test_failed_dump_is_cleaned_up() {
  new_case failed_dump
  fake_dump_content='partial archive'
  fake_dump_status=23
  fake_validate_status=0

  if run_backup > "$case_root/stdout" 2> "$case_root/stderr"; then
    fail 'backup unexpectedly succeeded after pg_dump failed'
  fi

  [ ! -e "$case_backend/backups/$final_name" ] || fail 'failed dump was published'
  assert_no_temporary_dump "$case_backend/backups"
}

test_failed_validation_is_cleaned_up() {
  new_case failed_validation
  fake_dump_content='invalid archive'
  fake_dump_status=0
  fake_validate_status=24

  if run_backup > "$case_root/stdout" 2> "$case_root/stderr"; then
    fail 'backup unexpectedly succeeded after validation failed'
  fi

  [ ! -e "$case_backend/backups/$final_name" ] || fail 'unvalidated dump was published'
  assert_no_temporary_dump "$case_backend/backups"
}

test_success_publishes_only_after_validation() {
  new_case successful_publication
  fake_dump_content='validated archive'
  fake_dump_status=0
  fake_validate_status=0

  if ! run_backup > "$case_root/stdout" 2> "$case_root/stderr"; then
    fail 'validated backup did not publish successfully'
  fi

  final_dump="$case_backend/backups/$final_name"
  [ -f "$final_dump" ] || fail 'validated dump was not published'
  assert_equals 'validated archive' "$(cat "$final_dump")" 'published dump content changed'
  assert_no_temporary_dump "$case_backend/backups"
  assert_equals 2 "$(wc -l < "$case_log" | tr -d ' ')" 'expected dump and validation commands'
}

test_retention_runs_only_after_publication() {
  new_case retention_after_publication
  mkdir -p "$case_backend/backups"
  old_dump="$case_backend/backups/pa_investing-20200101T000000Z.dump"
  printf 'known-good old backup' > "$old_dump"
  touch -t 202001010000 "$old_dump"
  fake_dump_content='invalid archive'
  fake_dump_status=0
  fake_validate_status=25

  if run_backup > "$case_root/failed.stdout" 2> "$case_root/failed.stderr"; then
    fail 'backup unexpectedly succeeded after validation failed'
  fi
  [ -f "$old_dump" ] || fail 'retention ran before validated publication'

  fake_dump_content='validated archive'
  fake_validate_status=0
  if ! run_backup > "$case_root/success.stdout" 2> "$case_root/success.stderr"; then
    fail 'validated backup did not succeed before retention check'
  fi
  [ ! -e "$old_dump" ] || fail 'retention did not run after publication'
  [ -f "$case_backend/backups/$final_name" ] || fail 'validated dump was not published'
}

test_existing_final_dump_is_never_overwritten() {
  new_case collision
  mkdir -p "$case_backend/backups"
  final_dump="$case_backend/backups/$final_name"
  printf 'trusted existing archive' > "$final_dump"
  fake_dump_content='retry archive'
  fake_dump_status=0
  fake_validate_status=0

  if run_backup > "$case_root/stdout" 2> "$case_root/stderr"; then
    fail 'same-second backup collision unexpectedly succeeded'
  fi

  assert_equals 'trusted existing archive' "$(cat "$final_dump")" 'existing dump was overwritten'
  assert_no_temporary_dump "$case_backend/backups"
}

test_backup_directory_and_dump_are_private() {
  new_case private_permissions
  mkdir -p "$case_backend/backups"
  chmod 755 "$case_backend/backups"
  fake_dump_content='private archive'
  fake_dump_status=0
  fake_validate_status=0

  if ! (umask 022; run_backup > "$case_root/stdout" 2> "$case_root/stderr"); then
    fail 'validated backup did not succeed before permission checks'
  fi

  assert_equals 700 "$(mode_of "$case_backend/backups")" 'backup directory mode is not private'
  assert_equals 600 "$(mode_of "$case_backend/backups/$final_name")" 'published dump mode is not private'
}

tests='test_failed_dump_is_cleaned_up
test_failed_validation_is_cleaned_up
test_success_publishes_only_after_validation
test_retention_runs_only_after_publication
test_existing_final_dump_is_never_overwritten
test_backup_directory_and_dump_are_private'

if [ "$#" -eq 1 ]; then
  "$1"
else
  failures=0
  for test_name in $tests; do
    if ("$test_name"); then
      printf 'PASS: %s\n' "$test_name"
    else
      failures=$((failures + 1))
    fi
  done
  [ "$failures" -eq 0 ] || fail "$failures backup regression test(s) failed"
fi

printf 'PASS: backup_postgres.sh atomic publication and permissions\n'
