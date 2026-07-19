# Indicative P&L Dashboard MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing authenticated portfolio browser page with indicative daily P&L metrics, a calendar visualization, and a manual refresh action while preserving every existing Notion workflow and API.

**Architecture:** Derive cash-flow-unadjusted daily P&L from the latest persisted portfolio snapshot for each UTC calendar day and expose it through a new typed analysis endpoint. Reuse the existing `RefreshAndSyncWorkflow` behind a same-origin analytics-authenticated route so the page can refresh safely without embedding the workflow bearer token. Enhance the current dependency-free HTML/CSS/JavaScript page rather than introducing a separate frontend toolchain.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, PostgreSQL/SQLAlchemy snapshot repository, server-rendered HTML, browser-native JavaScript and CSS, pytest.

## Global Constraints

- PostgreSQL remains the source of truth.
- Notion synchronization remains enabled and unchanged; the MVP is additive.
- The dashboard is analysis-only and must not add trade execution.
- Daily and DTD P&L are explicitly labelled `Indicative` because they are not adjusted for cash flows, trades, dividends, fees, or taxes.
- Daily comparisons use the latest snapshot per UTC calendar day in the most recently observed reporting currency.
- The first available day has no P&L comparison and returns null amounts and percentages.
- Existing analytics Basic authentication and workflow Bearer authentication remain compatible.
- No JavaScript framework, task queue, database migration, or new runtime dependency is introduced.

---

### Task 1: Indicative Daily P&L Domain Calculation

**Files:**
- Create: `backend/src/pa_investing/analytics/daily_pnl.py`
- Modify: `backend/tests/unit/test_performance_history.py`

**Interfaces:**
- Consumes: `list[PortfolioSnapshot]` from `PortfolioSnapshotRepository.list_history()`.
- Produces: `build_indicative_daily_pnl(snapshots: list[PortfolioSnapshot]) -> IndicativeDailyPnlHistory`.
- Produces models `IndicativeDailyPnlPoint` and `IndicativeDailyPnlHistory` for the API adapter.

- [ ] **Step 1: Add failing calculation tests**

Add imports for `build_indicative_daily_pnl`, then add tests proving that the function:

```python
def test_indicative_daily_pnl_uses_latest_snapshot_and_previous_available_day() -> None:
    result = build_indicative_daily_pnl(
        [
            _snapshot("day-1-morning", "2026-07-10T06:00:00+00:00", "1000", "0"),
            _snapshot("day-1-close", "2026-07-10T18:00:00+00:00", "1020", "20"),
            _snapshot("day-2", "2026-07-11T12:00:00+00:00", "1050", "50"),
        ]
    )

    assert result.reporting_currency == "USD"
    assert result.latest_nav == Decimal("1050")
    assert result.dtd_pnl_amount == Decimal("30")
    assert result.dtd_pnl_percent == Decimal("30") / Decimal("1020")
    assert [point.pnl_amount for point in result.points] == [None, Decimal("30")]
    assert result.points[1].comparison_date == date(2026, 7, 10)
    assert result.indicative is True
```

Add these focused assertions as separate tests:

```python
def test_indicative_daily_pnl_handles_empty_history() -> None:
    result = build_indicative_daily_pnl([])
    assert result.reporting_currency is None
    assert result.latest_nav is None
    assert result.dtd_pnl_amount is None
    assert result.dtd_pnl_percent is None
    assert result.points == []


def test_indicative_daily_pnl_handles_zero_prior_nav_and_propagates_coverage() -> None:
    first = _snapshot("zero", "2026-07-10T18:00:00+00:00", "0", "0")
    second = _snapshot("valued", "2026-07-11T18:00:00+00:00", "100", "100")
    second.reporting_coverage = Decimal("0.8")
    result = build_indicative_daily_pnl([first, second])
    assert result.points[1].pnl_amount == Decimal("100")
    assert result.points[1].pnl_percent is None
    assert result.points[1].reporting_coverage == Decimal("0.8")


def test_indicative_daily_pnl_uses_most_recent_reporting_currency() -> None:
    gbp = _snapshot("gbp", "2026-07-10T18:00:00+00:00", "800", "0")
    gbp.base_currency = "GBP"
    usd = _snapshot("usd", "2026-07-11T18:00:00+00:00", "1000", "0")
    result = build_indicative_daily_pnl([gbp, usd])
    assert result.reporting_currency == "USD"
    assert [point.ending_nav for point in result.points] == [Decimal("1000")]
```

- [ ] **Step 2: Run the focused unit tests and verify RED**

Run:

```bash
cd backend
/Users/chenkangan/Documents/PAMASTER/backend/.venv/bin/python -m pytest tests/unit/test_performance_history.py -v
```

Expected: collection fails because `pa_investing.analytics.daily_pnl` does not exist.

- [ ] **Step 3: Implement the calculation models and function**

Create immutable Pydantic models with these fields:

```python
class IndicativeDailyPnlPoint(BaseModel):
    model_config = ConfigDict(frozen=True)
    calendar_date: date
    observed_at: datetime
    comparison_date: date | None
    ending_nav: Decimal
    pnl_amount: Decimal | None
    pnl_percent: Decimal | None
    reporting_coverage: Decimal


class IndicativeDailyPnlHistory(BaseModel):
    model_config = ConfigDict(frozen=True)
    reporting_currency: str | None
    latest_nav: Decimal | None
    latest_observed_at: datetime | None
    dtd_pnl_amount: Decimal | None
    dtd_pnl_percent: Decimal | None
    indicative: bool = True
    points: list[IndicativeDailyPnlPoint]
```

`build_indicative_daily_pnl` must select the latest snapshot's `base_currency`, filter to that currency, use `latest_snapshot_per_day`, and calculate each non-first delta as `current.nav - previous.nav`; percent is null when `previous.nav == 0`.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the command from Step 2. Expected: all performance-history unit tests pass.

---

### Task 2: Typed Daily P&L and Browser Refresh APIs

**Files:**
- Modify: `backend/src/pa_investing/api/schemas.py`
- Modify: `backend/src/pa_investing/api/routes.py`
- Modify: `backend/tests/integration/test_api_routes.py`

**Interfaces:**
- Consumes: `build_indicative_daily_pnl(repository.list_history(days=days))`.
- Produces: `GET /analysis/daily-pnl?days=90 -> IndicativeDailyPnlResponse`.
- Produces: `POST /analysis/refresh -> RefreshAndSyncResponse`, guarded by `require_analytics_auth` and reusing `RefreshAndSyncWorkflow.run(stop_prices={})`.
- Preserves: `POST /workflows/refresh-and-sync`, including Bearer authentication and response shape.

- [ ] **Step 1: Add failing integration tests for the daily P&L route**

Add a fake snapshot repository with two daily snapshots and assert:

```python
response = client.get("/analysis/daily-pnl?days=90")
assert response.status_code == 200
assert response.json()["dtd_pnl_amount"] == "50"
assert response.json()["dtd_pnl_percent"] == "0.05"
assert response.json()["points"][0]["pnl_amount"] is None
assert response.json()["points"][1]["calendar_date"] == "2026-07-10"
assert response.json()["indicative"] is True
```

Add an empty-history assertion with null summary values and an empty `points` list.

- [ ] **Step 2: Add a failing integration test for browser refresh**

Override `get_refresh_and_sync_workflow` with a fake accepting `{}`, POST `{}` to `/analysis/refresh`, and assert the same typed response as the existing workflow endpoint. Add an authenticated configuration test proving missing Basic credentials returns 401. Assert the existing Bearer route still passes its current tests.

- [ ] **Step 3: Run the focused integration tests and verify RED**

Run:

```bash
cd backend
/Users/chenkangan/Documents/PAMASTER/backend/.venv/bin/python -m pytest tests/integration/test_api_routes.py -v
```

Expected: new requests return 404 because neither route exists.

- [ ] **Step 4: Add typed response schemas**

Add `IndicativeDailyPnlPointResponse` and `IndicativeDailyPnlResponse` matching Task 1, with Decimal values serialized through the existing `_format_decimal_or_none` route helper.

- [ ] **Step 5: Implement both additive routes**

Add:

```python
@router.get("/analysis/daily-pnl", response_model=IndicativeDailyPnlResponse)
def indicative_daily_pnl_analysis(
    repository: Annotated[
        PortfolioSnapshotRepository,
        Depends(get_portfolio_snapshot_repository),
    ],
    _: Annotated[None, Depends(require_analytics_auth)],
    days: int | None = 90,
) -> IndicativeDailyPnlResponse:
    history = build_indicative_daily_pnl(repository.list_history(days=days))
    return IndicativeDailyPnlResponse(
        reporting_currency=history.reporting_currency,
        latest_nav=_format_decimal_or_none(history.latest_nav),
        latest_observed_at=history.latest_observed_at,
        dtd_pnl_amount=_format_decimal_or_none(history.dtd_pnl_amount),
        dtd_pnl_percent=_format_decimal_or_none(history.dtd_pnl_percent),
        indicative=history.indicative,
        points=[
            IndicativeDailyPnlPointResponse(
                calendar_date=point.calendar_date,
                observed_at=point.observed_at,
                comparison_date=point.comparison_date,
                ending_nav=_format_decimal(point.ending_nav),
                pnl_amount=_format_decimal_or_none(point.pnl_amount),
                pnl_percent=_format_decimal_or_none(point.pnl_percent),
                reporting_coverage=_format_decimal(point.reporting_coverage),
            )
            for point in history.points
        ],
    )


@router.post("/analysis/refresh", response_model=RefreshAndSyncResponse)
def browser_refresh_route(
    _: Annotated[None, Depends(require_analytics_auth)],
    workflow: Annotated[
        RefreshAndSyncWorkflow,
        Depends(get_refresh_and_sync_workflow),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RefreshAndSyncResponse:
    return _refresh_response(workflow.run(stop_prices={}), settings)
```

Extract only the duplicated response mapping shared with `/workflows/refresh-and-sync`; do not change workflow behavior or authentication on the existing route.

- [ ] **Step 6: Run the focused integration tests and verify GREEN**

Run the command from Step 3. Expected: all API integration tests pass.

---

### Task 3: Mobile-First Portfolio Dashboard Page

**Files:**
- Modify: `backend/src/pa_investing/analytics_app/pages.py`
- Modify: `backend/tests/integration/test_api_routes.py`
- Modify: `backend/README.md`

**Interfaces:**
- Consumes: `GET /analysis/current`, `GET /analysis/performance`, `GET /analysis/daily-pnl?days=90`, and `POST /analysis/refresh`.
- Produces: the existing `GET /analysis/portfolio` page with one visible `Portfolio` tab, refresh controls, KPI cards, NAV chart, P&L calendar, allocation, and the existing performance table.

- [ ] **Step 1: Add a failing dashboard contract test**

Extend `test_performance_analysis_page_renders` to assert the page includes:

```python
assert 'id="portfolio-tab"' in response.text
assert 'id="refresh-portfolio"' in response.text
assert 'id="dtd-pnl-amount"' in response.text
assert 'id="dtd-pnl-percent"' in response.text
assert 'id="pnl-calendar"' in response.text
assert "Indicative P&amp;L" in response.text
assert "fetch('/analysis/daily-pnl?days=90')" in response.text
assert "fetch('/analysis/refresh'" in response.text
```

- [ ] **Step 2: Run the page test and verify RED**

Run:

```bash
cd backend
/Users/chenkangan/Documents/PAMASTER/backend/.venv/bin/python -m pytest tests/integration/test_api_routes.py::test_performance_analysis_page_renders -v
```

Expected: failure because the new dashboard elements are absent.

- [ ] **Step 3: Implement the page markup and mobile styling**

Keep `portfolio_page()` dependency-free. Add a compact top navigation with one active Portfolio tab, a refresh button/status region, four KPI cards (NAV, indicative DTD amount, indicative DTD percent, reporting coverage), and a calendar panel. Use a seven-column CSS grid for weekday headers and cells, responsive card grids, accessible button states, tabular numerals, and `aria-live` for refresh status.

- [ ] **Step 4: Implement calendar and refresh JavaScript**

Add `loadDailyPnl()` to populate KPI values and calendar cells. Calendar cells must use local formatting only for display, derive positive/negative/flat CSS classes from `pnl_amount`, show `--` for the first comparable day, and include the exact date and coverage in a tooltip. Add `refreshPortfolio()` to disable the button, POST JSON `{}` to `/analysis/refresh`, report errors, then reload current, performance, and daily-P&L views on success.

- [ ] **Step 5: Update the backend runbook**

Document `/analysis/daily-pnl`, `/analysis/refresh`, the indicative cash-flow limitation, and that browser refresh continues to run enabled Notion synchronization.

- [ ] **Step 6: Run focused tests and lint**

Run:

```bash
cd backend
/Users/chenkangan/Documents/PAMASTER/backend/.venv/bin/python -m pytest tests/unit/test_performance_history.py tests/integration/test_api_routes.py -v
/Users/chenkangan/Documents/PAMASTER/backend/.venv/bin/ruff check src/pa_investing tests/unit/test_performance_history.py tests/integration/test_api_routes.py
```

Expected: all focused tests pass and Ruff exits 0.

---

### Task 4: Full Verification

**Files:**
- No production files beyond Tasks 1-3.

**Interfaces:**
- Verifies the complete backend and unchanged Notion behavior.

- [ ] **Step 1: Run the complete test suite**

Run:

```bash
cd backend
/Users/chenkangan/Documents/PAMASTER/backend/.venv/bin/python -m pytest -q
```

Expected: all tests pass; the pre-existing Starlette/httpx deprecation warning may remain.

- [ ] **Step 2: Run full lint**

Run:

```bash
cd backend
/Users/chenkangan/Documents/PAMASTER/backend/.venv/bin/ruff check .
```

Expected: Ruff exits 0.

- [ ] **Step 3: Inspect the final diff and repository status**

Run `git diff --check`, `git diff --stat`, and `git status --short`. Confirm there are no changes to `pa_investing/notion/`, Notion tests, Docker secrets, database migrations, or trade-execution boundaries.
