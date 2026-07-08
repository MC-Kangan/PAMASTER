## What I implemented

- Added a new `pa_investing.analytics` package with portfolio metric helpers and snapshot construction.
- Implemented `calculate_nav`, `calculate_unrealized_pnl`, and `calculate_exposure_by_asset_class` in [`backend/src/pa_investing/analytics/metrics.py`](</Users/chenkangan/Documents/PAMASTER/backend/src/pa_investing/analytics/metrics.py:1>).
- Implemented `build_portfolio_snapshot` in [`backend/src/pa_investing/analytics/snapshots.py`](</Users/chenkangan/Documents/PAMASTER/backend/src/pa_investing/analytics/snapshots.py:1>) using the existing domain models and position properties.
- Added focused unit tests in [`backend/tests/unit/test_metrics.py`](</Users/chenkangan/Documents/PAMASTER/backend/tests/unit/test_metrics.py:1>) covering NAV, exposure by asset class, and portfolio snapshot assembly.

## What I tested and test results

- `cd backend && ./.venv/bin/pytest tests/unit/test_metrics.py -v`
- `cd backend && ./.venv/bin/ruff check .`

Both passed after implementation.

## TDD Evidence

- RED command: `cd backend && ./.venv/bin/pytest tests/unit/test_metrics.py -v`
- RED output: test collection failed with `ModuleNotFoundError: No module named 'pa_investing.analytics'`, which was expected because the analytics package had not been created yet.
- GREEN command: `cd backend && ./.venv/bin/pytest tests/unit/test_metrics.py -v`
- GREEN output: `2 passed`

## Files changed

- [`backend/tests/unit/test_metrics.py`](</Users/chenkangan/Documents/PAMASTER/backend/tests/unit/test_metrics.py:1>)
- [`backend/src/pa_investing/analytics/__init__.py`](</Users/chenkangan/Documents/PAMASTER/backend/src/pa_investing/analytics/__init__.py:1>)
- [`backend/src/pa_investing/analytics/metrics.py`](</Users/chenkangan/Documents/PAMASTER/backend/src/pa_investing/analytics/metrics.py:1>)
- [`backend/src/pa_investing/analytics/snapshots.py`](</Users/chenkangan/Documents/PAMASTER/backend/src/pa_investing/analytics/snapshots.py:1>)

## Self-review findings

- The implementation stays within Task 6 scope and only adds analytics helpers plus snapshot construction.
- The snapshot builder reuses existing `Position` properties, which keeps the logic deterministic and small.
- The exposure calculation only includes asset classes that are present in the supplied positions, matching the test contract.

## Any issues or concerns

- None.
