#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BACKEND_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$BACKEND_DIR"

PA_HOST=${PA_HOST:-127.0.0.1}
PA_PORT=${PA_PORT:-8000}
PA_OPEN_BROWSER=${PA_OPEN_BROWSER:-true}
PA_RELOAD=${PA_RELOAD:-false}
PA_LOG_FILE=${PA_LOG_FILE:-"${TMPDIR:-/tmp}/pa-master-${PA_PORT}.log"}
PA_URL="http://${PA_HOST}:${PA_PORT}"
PA_FRONTEND_URL="${PA_URL}/analysis/portfolio"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    printf '%s\n' \
        'Start the PA Master local server and open its portfolio analytics page.' \
        '' \
        'Usage: ./scripts/start_local.sh' \
        '' \
        'Environment overrides:' \
        '  PA_HOST=127.0.0.1       Bind address' \
        '  PA_PORT=8000            Port' \
        '  PA_OPEN_BROWSER=true    Open the frontend when ready' \
        '  PA_RELOAD=false         Enable Uvicorn auto-reload' \
        '  PA_LOG_FILE=...         Server log path'
    exit 0
fi

UVICORN="$BACKEND_DIR/.venv/bin/uvicorn"
if [ ! -x "$UVICORN" ]; then
    printf '%s\n' "Missing $UVICORN. Create the backend virtualenv and install dependencies first." >&2
    exit 1
fi

set -- "$UVICORN" pa_investing.main:app --host "$PA_HOST" --port "$PA_PORT"
if [ "$PA_RELOAD" = "true" ]; then
    set -- "$@" --reload
fi

printf '%s\n' "Starting PA Master at $PA_URL"
printf '%s\n' "Using the configured database and environment from $BACKEND_DIR/.env"
printf '%s\n' "Logs: $PA_LOG_FILE"

"$@" >"$PA_LOG_FILE" 2>&1 &
SERVER_PID=$!

cleanup() {
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup INT TERM EXIT

READY=false
if command -v curl >/dev/null 2>&1; then
    attempt=1
    while [ "$attempt" -le 30 ]; do
        if curl -fsS --max-time 2 "$PA_URL/health" >/dev/null 2>&1; then
            READY=true
            break
        fi
        if ! kill -0 "$SERVER_PID" 2>/dev/null; then
            break
        fi
        sleep 1
        attempt=$((attempt + 1))
    done
else
    printf '%s\n' 'curl is unavailable; skipping health check.' >&2
    READY=true
fi

if [ "$READY" != "true" ]; then
    printf '%s\n' 'PA Master did not become ready. Recent server output:' >&2
    tail -n 40 "$PA_LOG_FILE" >&2 || true
    exit 1
fi

printf '%s\n' "PA Master is ready: $PA_FRONTEND_URL"
if [ "$PA_OPEN_BROWSER" = "true" ]; then
    if command -v open >/dev/null 2>&1; then
        open "$PA_FRONTEND_URL" >/dev/null 2>&1 || true
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$PA_FRONTEND_URL" >/dev/null 2>&1 || true
    else
        printf '%s\n' 'No browser opener found; open the URL above manually.' >&2
    fi
fi

printf '%s\n' 'Press Ctrl-C to stop PA Master.'
wait "$SERVER_PID"
