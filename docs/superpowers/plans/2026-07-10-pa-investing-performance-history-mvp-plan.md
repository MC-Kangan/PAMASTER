# PA Investing Performance History MVP Implementation Plan

**Goal:** Build the next MVP slice after the Notion-connected refresh loop by turning persisted portfolio snapshots into a mobile-capable performance-history analytics surface with authentication and scheduled snapshot support.

**Architecture:** This plan reuses `portfolio_snapshots` as the historical source of truth. The backend will add a performance-history analytics service, an API endpoint for chart-ready history data, a responsive browser analytics view, a lightweight browser auth gate, and a fixed-cadence snapshot scheduler. Notion remains the summary layer rather than the charting surface.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Pydantic v2, pytest, existing analytics HTML surface, scheduler via lightweight in-process or host-triggered orchestration, responsive web UI rather than a Streamlit-first assumption.

## Global Constraints

- No trade execution.
- No broker live-read integration in this slice.
- No realized PnL accounting yet.
- No benchmark comparison yet.
- No desktop-only analytics UI.
- No public unauthenticated browser surface.
- Keep performance history derived from stored snapshots rather than introducing a second history store.
- Keep scheduled snapshots usable without interactive login.

---

## Scope Check

This plan implements the design documented in [2026-07-10-pa-investing-performance-history-mvp-design.md](/Users/chenkangan/Documents/PAMASTER/docs/superpowers/specs/2026-07-10-pa-investing-performance-history-mvp-design.md). It covers only:

- snapshot-based performance calculations;
- one performance-history API;
- one responsive browser performance page;
- one lightweight browser auth layer;
- fixed scheduled snapshot cadence at `00:00`, `06:00`, `12:00`, `18:00`;
- focused tests and runbook updates.

It does not implement multi-user auth, benchmark analytics, realized return accounting, broker connectivity, or a fully rebuilt frontend stack.

## Planned File Structure

```text
backend/
  README.md
  src/pa_investing/
    analytics/
      metrics.py
      performance.py
    analytics_app/
      pages.py
    api/
      routes.py
      schemas.py
    core/
      config.py
      dependencies.py
    db/
      repositories.py
    workflows/
      refresh_and_sync.py
      snapshot_schedule.py
  tests/
    integration/
      test_api_routes.py
      test_snapshot_schedule.py
    unit/
      test_performance_history.py
      test_auth.py
```

## Task 1: Build Performance History Analytics Service

**Files:**
- Create: `backend/src/pa_investing/analytics/performance.py`
- Modify: `backend/src/pa_investing/db/repositories.py`
- Create: `backend/tests/unit/test_performance_history.py`

**Interfaces:**
- Produces: `build_performance_history(snapshots: list[PortfolioSnapshot]) -> PerformanceHistory`
- Produces: repository method to read ordered snapshots, for example `PortfolioSnapshotRepository.list_history(days: int | None = None) -> list[PortfolioSnapshot]`

- [ ] **Step 1: Write failing unit tests for performance history**

Add focused tests covering:

```python
def test_build_performance_history_calculates_peak_drawdown_and_return() -> None:
    ...


def test_build_performance_history_handles_single_snapshot() -> None:
    ...


def test_build_performance_history_handles_empty_history() -> None:
    ...
```

Verify:

- running peak NAV is correct;
- drawdown uses `(nav - peak_nav) / peak_nav`;
- simple return uses the first point in the window;
- empty history returns an empty series and neutral summary values.

- [ ] **Step 2: Run focused performance unit tests**

Run: `cd backend && ./.venv/bin/pytest tests/unit/test_performance_history.py -v`

Expected: FAIL because the performance module does not exist yet.

- [ ] **Step 3: Implement the performance history service**

Create a small service that returns:

- ordered points with timestamp, nav, unrealized_pnl, peak_nav, drawdown, simple_return
- summary values such as starting NAV, ending NAV, simple return, max drawdown

Add the repository helper needed to fetch ordered snapshots, with optional `days` filtering.

- [ ] **Step 4: Re-run focused performance unit tests**

Run: `cd backend && ./.venv/bin/pytest tests/unit/test_performance_history.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/analytics/performance.py backend/src/pa_investing/db/repositories.py backend/tests/unit/test_performance_history.py
git commit -m "feat: add performance history analytics"
```

## Task 2: Expose Performance History API

**Files:**
- Modify: `backend/src/pa_investing/api/routes.py`
- Modify: `backend/src/pa_investing/api/schemas.py`
- Modify: `backend/src/pa_investing/core/dependencies.py`
- Modify: `backend/tests/integration/test_api_routes.py`

**Interfaces:**
- Produces: `GET /analysis/performance`
- Consumes: performance-history service
- Consumes: snapshot repository history reader

- [ ] **Step 1: Write failing API route tests**

Add focused tests for:

```python
def test_performance_route_returns_history_summary_and_points() -> None:
    ...


def test_performance_route_returns_empty_series_when_no_history_exists() -> None:
    ...
```

Include an optional query parameter path such as `?days=30`.

- [ ] **Step 2: Run focused API tests**

Run: `cd backend && ./.venv/bin/pytest tests/integration/test_api_routes.py -v`

Expected: FAIL because the performance route does not exist yet.

- [ ] **Step 3: Implement schemas and route**

Add request/response contracts for:

- summary block
- ordered performance points
- optional `days` query parameter

Keep decimal serialization consistent with the existing API style.

- [ ] **Step 4: Re-run focused API tests**

Run: `cd backend && ./.venv/bin/pytest tests/integration/test_api_routes.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/api/routes.py backend/src/pa_investing/api/schemas.py backend/src/pa_investing/core/dependencies.py backend/tests/integration/test_api_routes.py
git commit -m "feat: add performance history API"
```

## Task 3: Add Lightweight Browser Auth Gate

**Files:**
- Modify: `backend/src/pa_investing/core/config.py`
- Modify: `backend/src/pa_investing/api/routes.py`
- Create: `backend/tests/unit/test_auth.py`

**Interfaces:**
- Produces: simple auth requirement for browser analytics surface
- Consumes: settings-backed credentials or token guard for MVP

- [ ] **Step 1: Write failing auth tests**

Add focused tests for:

```python
def test_browser_analytics_route_denies_unauthenticated_requests() -> None:
    ...


def test_browser_analytics_route_allows_authenticated_requests() -> None:
    ...
```

The MVP auth layer can be simple, such as a sessionless password gate or bearer token suitable for a personal deployment.

- [ ] **Step 2: Run focused auth tests**

Run the smallest relevant target, for example:

`cd backend && ./.venv/bin/pytest tests/unit/test_auth.py tests/integration/test_api_routes.py -v`

Expected: FAIL because the auth requirement is not implemented yet.

- [ ] **Step 3: Implement the auth gate**

Add minimal config-backed auth for browser-facing analytics routes only.

Constraints:

- backend scheduled jobs must not depend on interactive login;
- API and browser route protection should be simple but explicit;
- Notion integration remains token-based and unaffected.

- [ ] **Step 4: Re-run focused auth tests**

Run the same focused test targets.

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/core/config.py backend/src/pa_investing/api/routes.py backend/tests/unit/test_auth.py backend/tests/integration/test_api_routes.py
git commit -m "feat: add analytics auth gate"
```

## Task 4: Add Responsive Browser Performance View

**Files:**
- Modify: `backend/src/pa_investing/analytics_app/pages.py`
- Modify: `backend/src/pa_investing/api/routes.py`
- Test: extend `backend/tests/integration/test_api_routes.py`

**Interfaces:**
- Produces: browser page for performance history
- Consumes: performance history API or shared service output

- [ ] **Step 1: Write failing browser page tests**

Add route smoke tests asserting the performance page renders:

```python
def test_performance_analysis_page_renders() -> None:
    ...
```

Verify presence of:

- title
- summary labels
- performance history container

- [ ] **Step 2: Run focused browser page tests**

Run: `cd backend && ./.venv/bin/pytest tests/integration/test_api_routes.py -v`

Expected: FAIL because the page does not exist yet.

- [ ] **Step 3: Implement responsive page**

Add a simple responsive HTML view that:

- renders summary metrics;
- renders one or more chart-ready containers;
- stacks cleanly on small screens;
- remains lightweight and consistent with the current app.

It is acceptable for the first version to render basic inline chart scaffolding or minimal client-side data embedding, as long as the page is clearly structured for mobile and desktop.

- [ ] **Step 4: Re-run focused browser page tests**

Run: `cd backend && ./.venv/bin/pytest tests/integration/test_api_routes.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/analytics_app/pages.py backend/src/pa_investing/api/routes.py backend/tests/integration/test_api_routes.py
git commit -m "feat: add responsive performance analytics page"
```

## Task 5: Add Fixed-Cadence Snapshot Scheduling

**Files:**
- Create: `backend/src/pa_investing/workflows/snapshot_schedule.py`
- Modify: `backend/src/pa_investing/workflows/refresh_and_sync.py`
- Create: `backend/tests/integration/test_snapshot_schedule.py`

**Interfaces:**
- Produces: schedule definition for `00:00`, `06:00`, `12:00`, `18:00`
- Produces: callable path to run snapshot-producing workflow on schedule

- [ ] **Step 1: Write failing schedule tests**

Add tests covering:

```python
def test_snapshot_schedule_defines_four_fixed_run_times() -> None:
    ...


def test_snapshot_schedule_triggers_snapshot_capable_workflow() -> None:
    ...
```

The MVP can keep scheduling logic simple:

- explicit run times
- explicit callable integration point
- no full distributed scheduler required

- [ ] **Step 2: Run focused schedule tests**

Run: `cd backend && ./.venv/bin/pytest tests/integration/test_snapshot_schedule.py -v`

Expected: FAIL because schedule support does not exist yet.

- [ ] **Step 3: Implement schedule support**

Add a small module that:

- defines the fixed run times;
- exposes the schedule configuration clearly;
- supports invoking snapshot-producing workflow logic at those times.

This can target host cron, NAS scheduler, or a lightweight in-process scheduler later. The MVP focus is on making the cadence explicit and testable.

- [ ] **Step 4: Re-run focused schedule tests**

Run: `cd backend && ./.venv/bin/pytest tests/integration/test_snapshot_schedule.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/workflows/snapshot_schedule.py backend/src/pa_investing/workflows/refresh_and_sync.py backend/tests/integration/test_snapshot_schedule.py
git commit -m "feat: add snapshot schedule support"
```

## Task 6: Update Runbook And Full Verification

**Files:**
- Modify: `backend/README.md`

**Interfaces:**
- Produces: documented performance-history MVP workflow

- [ ] **Step 1: Update the backend runbook**

Document:

- how performance history is generated from snapshots;
- how to call `GET /analysis/performance`;
- how the browser analytics page should be accessed;
- how auth is configured for the browser page;
- how scheduled snapshots run at `00:00`, `06:00`, `12:00`, `18:00`.

- [ ] **Step 2: Run full verification**

Run:

```bash
cd backend
./.venv/bin/pytest
./.venv/bin/ruff check .
git status --short
```

Expected:

- all tests pass;
- Ruff is clean;
- git status is clean after the final commit.

- [ ] **Step 3: Commit**

```bash
git add backend/README.md
git commit -m "docs: add performance history runbook"
```

## Self-Review

Spec coverage:

- snapshot-based history is covered by Tasks 1 and 2;
- browser auth is covered by Task 3;
- responsive browser analytics is covered by Task 4;
- scheduled snapshot cadence is covered by Task 5;
- runbook updates are covered by Task 6.

Placeholder scan:

- no `TODO` or `TBD` placeholders remain;
- fixed schedule times are explicitly listed.

Type consistency:

- performance history is derived from existing `PortfolioSnapshot` data;
- the browser layer consumes backend-calculated outputs instead of duplicating logic;
- auth remains scoped to browser-facing analytics access;
- scheduling remains backend-operational and independent of browser login.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-10-pa-investing-performance-history-mvp-plan.md`.

Recommended next step: implement Task 1 first with TDD, then continue task-by-task in order.
