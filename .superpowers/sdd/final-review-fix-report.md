# Final Review Fix Report

## What changed

- Fixed stop-signal analytics links to be keyed by the generated `signal_id` instead of the symbol in `backend/src/pa_investing/signals/rules.py`.
- Added optional daily review persistence wiring in `backend/src/pa_investing/workflows/daily_review.py` so a supplied persistence dependency stores review outputs before Notion sync while the existing in-memory path remains unchanged.
- Added database models/repositories for `portfolio_snapshots` and `audit_events`, and reused `SignalRepository` to persist generated signals.
- Added Alembic migration `backend/alembic/versions/0002_add_portfolio_snapshots.py` to create the new `portfolio_snapshots` and `audit_events` tables.
- Added regression coverage for signal analytics links and a SQLite integration test that verifies CSV-imported positions produce persisted snapshot/signal/audit rows and fake Notion payloads keyed to the generated `signal_id`.

## TDD RED/GREEN evidence

### Important 1: `analytics_path` must use `signal_id`

- RED:
  - Command: `cd backend && ./.venv/bin/pytest tests/unit/test_signals.py -q`
  - Result: failed in `test_stop_reference_rule_creates_signal_when_price_breaches_stop`
  - Key failure: `'/analysis/signal/AAPL'.endswith(signal.signal_id)` was `False`
- GREEN:
  - Command: `cd backend && ./.venv/bin/pytest tests/unit/test_signals.py tests/integration/test_daily_review_workflow.py -q`
  - Result: `5 passed in 0.30s`

### Important 2: persist daily review outputs to DB before Notion sync

- RED:
  - Command: `cd backend && ./.venv/bin/pytest tests/integration/test_daily_review_workflow.py::test_daily_review_workflow_persists_snapshot_and_signals_before_notion_sync -q`
  - First failure: `ImportError: cannot import name 'PortfolioSnapshotRepository'`
  - Follow-up RED after adding snapshot/signal persistence expectation:
    - `ImportError: cannot import name 'AuditEventRecord'`
  - These failures confirmed the persistence surface and tables were missing.
- GREEN:
  - Command: `cd backend && ./.venv/bin/pytest tests/unit/test_signals.py tests/integration/test_daily_review_workflow.py -q`
  - Result: `5 passed in 0.30s`
  - Verified outcomes:
    - snapshot row persisted
    - signal row persisted with matching `signal_id`
    - audit event row persisted with matching `audit_id`
    - fake Notion payload `Analytics Link` equals `/analysis/signal/<signal_id>`

## Verification commands and outputs

- `cd backend && ./.venv/bin/pytest`
  - Result: `29 passed, 1 warning in 0.45s`
- `cd backend && ./.venv/bin/ruff check .`
  - Result: `All checks passed!`
- `cd backend && docker compose config`
  - Result:
    - `/opt/homebrew/Library/Homebrew/cmd/shellenv.sh: line 18: /bin/ps: Operation not permitted`
    - `zsh:1: command not found: docker`

## Files changed

- `backend/src/pa_investing/signals/rules.py`
- `backend/src/pa_investing/workflows/daily_review.py`
- `backend/src/pa_investing/db/models.py`
- `backend/src/pa_investing/db/repositories.py`
- `backend/alembic/versions/0002_add_portfolio_snapshots.py`
- `backend/tests/unit/test_signals.py`
- `backend/tests/integration/test_daily_review_workflow.py`
- `.superpowers/sdd/final-review-fix-report.md`

## Self-review notes

- Kept persistence optional so existing fake/in-memory workflow tests and call sites keep working unchanged.
- Persisted review outputs before Notion sync, matching the review requirement and making the fake Notion payload assertions meaningful.
- Used the existing repository pattern and kept schema additions limited to Phase 1 review artifacts.
- Added minimal audit-event persistence as a direct projection of generated signals to fully close the review note about missing audit persistence.

## Concerns

- `docker` is not installed in this environment, so `docker compose config` could not be validated beyond recording the exact shell output above.
