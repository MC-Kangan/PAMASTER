# Task 3 Report: Mobile-First Portfolio Dashboard Page

## Changed files

- `backend/src/pa_investing/analytics_app/pages.py`
  - Added a single active Portfolio tab, refresh control/status, four headline KPI cards,
    and a seven-column indicative P&L calendar without adding frontend dependencies.
  - Added daily-P&L loading, local display formatting, sign-based calendar styling,
    exact-date/coverage tooltips, missing-date spacing, and refresh/reload behavior.
  - Preserved the existing allocation donut, NAV history chart, performance summary,
    and performance table.
- `backend/tests/integration/test_api_routes.py`
  - Extended the existing page contract test with the required dashboard element and
    endpoint-fetch assertions.
- `backend/README.md`
  - Documented `GET /analysis/daily-pnl?days=90`, `POST /analysis/refresh`, the
    cash-flow limitation, reporting coverage, and continued enabled Notion sync.
- `backend/tests/unit/test_performance_history.py`
  - Mechanically reordered two imports after the required Ruff command exposed an
    import-order issue already present in the Task 2 baseline.

## RED evidence

Command:

```bash
cd backend
/Users/chenkangan/Documents/PAMASTER/backend/.venv/bin/python -m pytest tests/integration/test_api_routes.py::test_performance_analysis_page_renders -v
```

Before implementation: **1 failed** at the first new assertion because
`id="portfolio-tab"` was absent. The response was otherwise HTTP 200, confirming the
failure was caused by the missing dashboard contract rather than test setup or routing.

## GREEN evidence

After implementation, the same page contract command completed with **1 passed**.
Final focused verification ran:

```bash
cd backend
/Users/chenkangan/Documents/PAMASTER/backend/.venv/bin/python -m pytest tests/unit/test_performance_history.py tests/integration/test_api_routes.py -v
/Users/chenkangan/Documents/PAMASTER/backend/.venv/bin/ruff check src/pa_investing tests/unit/test_performance_history.py tests/integration/test_api_routes.py
git diff --check
```

Results: **31 passed**, Ruff reported **All checks passed**, and `git diff --check`
exited successfully. Pytest emitted one existing third-party Starlette `TestClient`/`httpx`
deprecation warning.

## UX and accessibility self-review

- The layout starts with two KPI columns on narrow screens and expands to four at 720px;
  calendar cells remain in a seven-column grid and preserve gaps between snapshot dates.
- The visible Portfolio link is marked with `aria-current="page"`; refresh status uses
  `aria-live="polite"`; the refresh button disables and exposes `aria-busy` during work;
  and keyboard focus has a visible outline.
- KPI, table, and calendar amounts use tabular numerals. Positive, negative, and flat
  calendar values differ by label/value as well as color. The first non-comparable point
  renders `--`.
- Calendar display dates use the browser locale, while each cell's tooltip and accessible
  label retain the exact ISO date, reporting coverage, and P&L value.
- Empty and request-failure states remain readable text, and refresh errors are announced
  in the status region.

## Commit

The task report is included in the final task commit; its immutable hash is supplied in the
task handoff after the commit is finalized.

## Concerns

- The page contract verifies the required markup and endpoint wiring, but the repository
  does not currently provide a browser JavaScript/E2E harness for automated interaction or
  visual-regression coverage.
- An unrelated untracked file,
  `docs/superpowers/plans/2026-07-19-indicative-pnl-dashboard-mvp.md`, was already present
  and remains intentionally outside this task commit.
- The focused suite reports the existing Starlette `TestClient`/`httpx` deprecation warning.

## Review-finding fix

Files updated:

- `backend/tests/integration/test_api_routes.py` now rejects the unsupported composite-grid
  roles, requires focusable semantic `<time>` day elements and visible coverage markup, and
  checks that raw JavaScript uses `P&L` rather than an HTML entity.
- `backend/src/pa_investing/analytics_app/pages.py` keeps the seven-column CSS layout and
  blank date spacers while replacing ARIA grid roles with focusable `<time datetime>` cells,
  a visible focus outline, and compact visible per-day coverage text.

Review-fix RED command:

```bash
cd backend
/Users/chenkangan/Documents/PAMASTER/backend/.venv/bin/python -m pytest tests/integration/test_api_routes.py::test_performance_analysis_page_renders -v
```

Result before the fix: **1 failed** at `assert 'role="grid"' not in response.text`,
confirming the contract detected the invalid composite role before implementation.

The same page contract test passed after implementation. Fresh focused verification ran:

```bash
/Users/chenkangan/Documents/PAMASTER/backend/.venv/bin/python -m pytest tests/unit/test_performance_history.py tests/integration/test_api_routes.py -v
/Users/chenkangan/Documents/PAMASTER/backend/.venv/bin/ruff check src/pa_investing tests/unit/test_performance_history.py tests/integration/test_api_routes.py
git diff --check
```

Result: **31 passed**, Ruff reported **All checks passed**, and `git diff --check`
exited successfully. The existing third-party Starlette `TestClient`/`httpx` warning remains.
The immutable review-fix commit hash is supplied in the task handoff.
