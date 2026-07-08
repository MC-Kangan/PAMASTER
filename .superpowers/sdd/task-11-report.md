# Task 11 Report: FastAPI Routes And Minimal Analytics Pages

## What I implemented
- Added `create_app() -> FastAPI` in `backend/src/pa_investing/main.py`.
- Added a router module with:
  - `GET /health`
  - `GET /analysis/portfolio`
  - `GET /analysis/signal/{signal_id}`
- Added minimal HTML page helpers for portfolio and signal analysis targets.
- Added integration coverage for the health endpoint and both analysis pages.

## What I tested and test results
- Ran `backend/.venv/bin/python -m pytest backend/tests/integration/test_api_routes.py -v`
  - Result: passed, 3 tests collected, 3 passed.
  - Warning observed: FastAPI/TestClient emits a Starlette deprecation warning about `httpx`/`httpx2`.
- Ran `backend/.venv/bin/python -m ruff check backend`
  - Result: passed, no lint errors.

## TDD Evidence
- RED:
  - Command: `backend/.venv/bin/python -m pytest backend/tests/integration/test_api_routes.py -v`
  - Output: `ModuleNotFoundError: No module named 'pa_investing.main'`
- GREEN:
  - Command: `backend/.venv/bin/python -m pytest backend/tests/integration/test_api_routes.py -v`
  - Output: `3 passed`

## Files changed
- `backend/src/pa_investing/main.py`
- `backend/src/pa_investing/api/__init__.py`
- `backend/src/pa_investing/api/routes.py`
- `backend/src/pa_investing/analytics_app/__init__.py`
- `backend/src/pa_investing/analytics_app/pages.py`
- `backend/tests/integration/test_api_routes.py`

## Self-review findings
- The implementation stays within the task scope: read-only analysis and link pages only, no trade execution path.
- The app factory is minimal and includes the router directly, which keeps the entry point obvious.
- The analysis pages are intentionally bare link targets, matching the Phase 1 brief.

## Any issues or concerns
- No functional blockers found.
- Non-blocking test warning from Starlette/FastAPI about `httpx2` appeared during the integration test run.

## Task 11 follow-up: HTML escaping regression fix

### What I changed
- Escaped `signal_id` before embedding it in `backend/src/pa_investing/analytics_app/pages.py` with `html.escape(...)`.
- Added a regression test that requests `/analysis/signal/<sig&123>` and expects the rendered HTML to contain `Signal ID: &lt;sig&amp;123&gt;`.

### TDD evidence
- RED:
  - Command: `cd backend && .venv/bin/python -m pytest tests/integration/test_api_routes.py -v`
  - Result: failed as expected on `test_analysis_signal_page_escapes_signal_id_html`
  - Output excerpt:
    ```text
    E       AssertionError: assert 'Signal ID: &lt;sig&amp;123&gt;' in '\n    <html>\n      <head><title>Signal Analysis</title></head>\n      <body>\n        <h1>Signal Analysis</h1>\n        <p>Signal ID: <sig&123></p>\n      </body>\n    </html>\n    '
    ```
- GREEN:
  - Command: `cd backend && .venv/bin/python -m pytest tests/integration/test_api_routes.py -v`
  - Result: passed, 4 tests collected, 4 passed.
  - Command: `cd backend && .venv/bin/ruff check .`
  - Result: passed, `All checks passed!`
