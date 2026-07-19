# Task 2 Report: Typed Daily P&L and Browser Refresh APIs

## Changed files

- `backend/src/pa_investing/api/schemas.py`
  - Added typed `IndicativeDailyPnlPointResponse` and `IndicativeDailyPnlResponse` schemas.
- `backend/src/pa_investing/api/routes.py`
  - Added protected `GET /analysis/daily-pnl` backed by `build_indicative_daily_pnl`.
  - Added protected `POST /analysis/refresh` using `RefreshAndSyncWorkflow.run(stop_prices={})`.
  - Extracted `_refresh_response` so the pre-existing Bearer workflow route keeps the same mapping and behavior.
- `backend/tests/integration/test_api_routes.py`
  - Added daily P&L populated and empty-history coverage.
  - Added browser refresh typed-response and missing Basic credential coverage.

## RED evidence

Command:

```bash
cd backend
/Users/chenkangan/Documents/PAMASTER/backend/.venv/bin/python -m pytest tests/integration/test_api_routes.py -v
```

Before implementation: 17 passed, 4 failed. The four new route tests failed as expected because both `/analysis/daily-pnl` and `/analysis/refresh` returned HTTP 404.

## GREEN evidence

The same focused integration command completed with **21 passed** (one existing third-party `httpx` deprecation warning). The final verification also ran:

```bash
/Users/chenkangan/Documents/PAMASTER/backend/.venv/bin/ruff check src/pa_investing/api/routes.py src/pa_investing/api/schemas.py tests/integration/test_api_routes.py
git diff --check
```

Both completed successfully.

## Self-review

- The daily P&L API is Basic-auth protected through `require_analytics_auth`, defaults `days` to 90, serializes Decimal values through the existing formatting helpers, and returns typed summary/point payloads.
- The browser refresh API is Basic-auth protected and deliberately always supplies an empty stop-price mapping.
- The existing `/workflows/refresh-and-sync` endpoint still requires its Bearer workflow authentication and retains its response shape; only its response construction was shared.
- No Notion synchronization behavior was changed; `notion_sync_enabled` remains sourced from `Settings`.

## Commit

The task report is included in the final `Add indicative P&L analysis APIs` commit; its
immutable hash is supplied in the task handoff after the commit is finalized.

## Concerns

- An unrelated untracked file, `docs/superpowers/plans/2026-07-19-indicative-pnl-dashboard-mvp.md`, was already present and has been intentionally left out of this task's changes.
- The focused suite reports an existing Starlette `TestClient`/`httpx` deprecation warning.
