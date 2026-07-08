# PA Investing Phase 2 MVP Notion And Price Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first visible MVP loop after Phase 1 by connecting the backend to a real Notion workspace and one live market price API, then exposing a triggerable refresh-and-sync workflow.

**Architecture:** This phase keeps PostgreSQL as the source of truth and Notion as a UI adapter. The backend will add a live Notion client, a live market-data provider, and one workflow that refreshes persisted portfolio state and syncs selected user-facing results into Notion. Agent endpoints, broker live connectors, and broader knowledge retrieval remain deferred.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL, Pydantic v2, pytest, httpx, Docker Compose, Alpha Vantage HTTP API for first live price provider.

## Global Constraints

- No order placement.
- No day-trading or high-frequency workflows.
- No storing secrets in Notion.
- No treating Notion as the only source of portfolio truth.
- No broker live connectors in this phase.
- No agent or LLM explanation features in this phase.
- Notion is a UI adapter.
- PostgreSQL is the source of truth.
- Keep live integrations behind explicit interfaces so fake/test providers remain available.
- Favor idempotent sync behavior for Notion writes.
- Do not couple market data fetching directly to Notion page-writing logic.

---

## Scope Check

This plan implements the roadmap pivot documented in [2026-07-08-pa-investing-mvp-roadmap-pivot-design.md](/Users/chenkangan/Documents/PAMASTER/docs/superpowers/specs/2026-07-08-pa-investing-mvp-roadmap-pivot-design.md). It covers only:

- live Notion client support;
- selected Notion sync targets (`Signals`, `Daily Review`);
- one live market price provider using Alpha Vantage;
- one triggerable end-to-end backend workflow.

It does not implement broker auth, Obsidian retrieval, agent orchestration, notifications, or a richer analytics cockpit.

## Planned File Structure

```text
backend/
  .env.example
  README.md
  src/pa_investing/
    main.py
    core/
      config.py
      dependencies.py
    api/
      routes.py
      schemas.py
    notion/
      client.py
      live.py
      schemas.py
      sync.py
    market_data/
      interfaces.py
      manual_prices.py
      alpha_vantage.py
    workflows/
      daily_review.py
      refresh_and_sync.py
  tests/
    fixtures/
      alpha_vantage_global_quote_aapl.json
      alpha_vantage_btc_usd.json
      notion_create_page_response.json
    unit/
      test_config.py
      test_alpha_vantage_provider.py
      test_live_notion_client.py
      test_notion_sync.py
    integration/
      test_refresh_and_sync_workflow.py
      test_api_routes.py
```

## Task 1: Live Integration Settings And Dependency Wiring

**Files:**
- Modify: `backend/src/pa_investing/core/config.py`
- Create: `backend/src/pa_investing/core/dependencies.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/unit/test_config.py`

**Interfaces:**
- Produces: `Settings.notion_signals_database_id: str`
- Produces: `Settings.notion_daily_review_database_id: str`
- Produces: `Settings.market_data_provider: str`
- Produces: `Settings.alpha_vantage_api_key: str`
- Produces: `get_settings() -> Settings`

- [ ] **Step 1: Write failing config tests**

Add config assertions for:

```python
def test_settings_include_live_notion_and_market_data_fields() -> None:
    settings = Settings(
        notion_enabled=True,
        notion_api_key="secret",
        notion_signals_database_id="signals-db",
        notion_daily_review_database_id="daily-review-db",
        market_data_provider="alpha_vantage",
        alpha_vantage_api_key="alpha-key",
    )

    assert settings.notion_signals_database_id == "signals-db"
    assert settings.notion_daily_review_database_id == "daily-review-db"
    assert settings.market_data_provider == "alpha_vantage"
    assert settings.alpha_vantage_api_key == "alpha-key"
```

- [ ] **Step 2: Run focused tests to verify the fields are missing**

Run: `cd backend && ./.venv/bin/pytest tests/unit/test_config.py -v`
Expected: FAIL with missing `Settings` fields.

- [ ] **Step 3: Implement settings and dependency helpers**

Add fields to `Settings`:

```python
market_data_provider: str = "manual"
alpha_vantage_api_key: str = ""
notion_signals_database_id: str = ""
notion_daily_review_database_id: str = ""
```

Create `core/dependencies.py` with a cached settings accessor:

```python
from functools import lru_cache

from pa_investing.core.config import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Update `.env.example`:

```bash
PA_MARKET_DATA_PROVIDER=manual
PA_ALPHA_VANTAGE_API_KEY=
PA_NOTION_SIGNALS_DATABASE_ID=
PA_NOTION_DAILY_REVIEW_DATABASE_ID=
```

- [ ] **Step 4: Re-run the focused config tests**

Run: `cd backend && ./.venv/bin/pytest tests/unit/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/core/config.py backend/src/pa_investing/core/dependencies.py backend/.env.example backend/tests/unit/test_config.py
git commit -m "feat: add live integration settings"
```

## Task 2: Live Notion Client And Database-Aware Sync Payloads

**Files:**
- Modify: `backend/src/pa_investing/notion/client.py`
- Create: `backend/src/pa_investing/notion/live.py`
- Modify: `backend/src/pa_investing/notion/schemas.py`
- Modify: `backend/src/pa_investing/notion/sync.py`
- Test: `backend/tests/unit/test_live_notion_client.py`
- Test: `backend/tests/unit/test_notion_sync.py`
- Create: `backend/tests/fixtures/notion_create_page_response.json`

**Interfaces:**
- Produces: `LiveNotionClient.upsert_page(database_name: str, external_id: str, payload: NotionPagePayload) -> str`
- Produces: `NotionSync.sync_signal(signal: Signal) -> str`
- Produces: `NotionSync.sync_daily_review(result: DailyReviewResult) -> str`
- Consumes: `Settings.notion_signals_database_id`
- Consumes: `Settings.notion_daily_review_database_id`

- [ ] **Step 1: Write failing live Notion client tests**

Add a unit test using `httpx.MockTransport`:

```python
def test_live_notion_client_upserts_page_to_configured_database() -> None:
    payload = NotionPagePayload(
        title="AAPL stop_reference",
        properties={"Symbol": "AAPL"},
        body="Signal body",
    )
    client = LiveNotionClient(
        api_key="notion-secret",
        database_ids={"Signals": "signals-db"},
        transport=mock_transport,
    )

    page_id = client.upsert_page("Signals", "sig-1", payload)

    assert page_id == "notion-page-1"
```

Add a sync test for daily review:

```python
def test_notion_sync_builds_daily_review_payload() -> None:
    payload = sync.build_daily_review_payload(result)
    assert payload.properties["Snapshot ID"] == result.snapshot.snapshot_id
    assert payload.properties["Signal Count"] == "1"
```

- [ ] **Step 2: Run focused Notion tests to verify missing behavior**

Run: `cd backend && ./.venv/bin/pytest tests/unit/test_live_notion_client.py tests/unit/test_notion_sync.py -v`
Expected: FAIL with missing `LiveNotionClient` and missing daily review sync behavior.

- [ ] **Step 3: Implement the live Notion client**

Keep `NotionClient` as the shared interface in `client.py`, keep `FakeNotionClient`, and add a separate `live.py` implementation that:

- posts to `https://api.notion.com/v1/pages`;
- sends `Authorization`, `Notion-Version`, and JSON body;
- stores `external_id` in page properties or dedicated metadata block for idempotent matching logic;
- returns created or updated Notion page id.

Use constructor shape:

```python
class LiveNotionClient(NotionClient):
    def __init__(
        self,
        api_key: str,
        database_ids: dict[str, str],
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        ...
```

- [ ] **Step 4: Expand Notion sync**

Keep signal sync, and add:

```python
def build_daily_review_payload(self, result: DailyReviewResult) -> NotionPagePayload:
    ...

def sync_daily_review(self, result: DailyReviewResult) -> str:
    ...
```

Use only a limited first mapping:

- `Signals`: symbol, signal type, severity, status, recommendation, audit id, analytics link
- `Daily Review`: snapshot id, nav, gross exposure, net exposure, unrealized pnl, signal count, summary body

- [ ] **Step 5: Re-run focused Notion tests**

Run: `cd backend && ./.venv/bin/pytest tests/unit/test_live_notion_client.py tests/unit/test_notion_sync.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/src/pa_investing/notion/client.py backend/src/pa_investing/notion/live.py backend/src/pa_investing/notion/schemas.py backend/src/pa_investing/notion/sync.py backend/tests/unit/test_live_notion_client.py backend/tests/unit/test_notion_sync.py backend/tests/fixtures/notion_create_page_response.json
git commit -m "feat: add live Notion client"
```

## Task 3: Alpha Vantage Market Data Provider

**Files:**
- Create: `backend/src/pa_investing/market_data/alpha_vantage.py`
- Modify: `backend/src/pa_investing/market_data/interfaces.py`
- Test: `backend/tests/unit/test_alpha_vantage_provider.py`
- Create: `backend/tests/fixtures/alpha_vantage_global_quote_aapl.json`
- Create: `backend/tests/fixtures/alpha_vantage_btc_usd.json`

**Interfaces:**
- Produces: `AlphaVantageProvider.get_latest_prices(symbols: set[str]) -> dict[str, PricePoint]`
- Consumes: `MarketDataProvider`
- Consumes: Alpha Vantage `GLOBAL_QUOTE` for equities/ETFs and `CURRENCY_EXCHANGE_RATE` for crypto-vs-base-currency pairs

- [ ] **Step 1: Write failing Alpha Vantage provider tests**

Create focused tests for:

```python
def test_alpha_vantage_provider_reads_equity_quote() -> None:
    provider = AlphaVantageProvider(api_key="demo", transport=mock_transport)
    prices = provider.get_latest_prices({"AAPL"})
    assert prices["AAPL"].price == Decimal("210.55")


def test_alpha_vantage_provider_reads_crypto_quote_against_usd() -> None:
    provider = AlphaVantageProvider(api_key="demo", transport=mock_transport)
    prices = provider.get_latest_prices({"BTC-USD"})
    assert prices["BTC-USD"].price == Decimal("65000.00")
```

- [ ] **Step 2: Run focused provider tests to verify adapter missing**

Run: `cd backend && ./.venv/bin/pytest tests/unit/test_alpha_vantage_provider.py -v`
Expected: FAIL with missing provider implementation.

- [ ] **Step 3: Implement the provider**

Create `alpha_vantage.py` with:

```python
class AlphaVantageProvider(MarketDataProvider):
    def __init__(
        self,
        api_key: str,
        base_currency: str = "USD",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        ...
```

Implementation rules:

- symbols without `-` use `GLOBAL_QUOTE`;
- symbols like `BTC-USD` map to `CURRENCY_EXCHANGE_RATE` with `from_currency=BTC`, `to_currency=USD`;
- return `PricePoint` values using UTC timestamps and provider name `alpha_vantage`;
- if the API omits a symbol or returns an error note, skip the symbol and let the caller decide how to surface sync status.

- [ ] **Step 4: Re-run focused provider tests**

Run: `cd backend && ./.venv/bin/pytest tests/unit/test_alpha_vantage_provider.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/market_data/alpha_vantage.py backend/src/pa_investing/market_data/interfaces.py backend/tests/unit/test_alpha_vantage_provider.py backend/tests/fixtures/alpha_vantage_global_quote_aapl.json backend/tests/fixtures/alpha_vantage_btc_usd.json
git commit -m "feat: add Alpha Vantage price provider"
```

## Task 4: End-To-End Refresh And Notion Sync Workflow

**Files:**
- Create: `backend/src/pa_investing/workflows/refresh_and_sync.py`
- Modify: `backend/src/pa_investing/workflows/daily_review.py`
- Modify: `backend/src/pa_investing/db/repositories.py`
- Test: `backend/tests/integration/test_refresh_and_sync_workflow.py`

**Interfaces:**
- Produces: `RefreshAndSyncWorkflow.run(stop_prices: dict[str, Decimal]) -> DailyReviewResult`
- Consumes: `PositionRepository.list_open_positions() -> list[Position]`
- Consumes: `PriceRepository.upsert(price_point: PricePoint) -> None`
- Consumes: `AlphaVantageProvider.get_latest_prices(symbols: set[str]) -> dict[str, PricePoint]`
- Consumes: `DailyReviewWorkflow.run(positions: list[Position], stop_prices: dict[str, Decimal]) -> DailyReviewResult`
- Consumes: `NotionSync.sync_daily_review(result: DailyReviewResult) -> str`

- [ ] **Step 1: Write failing workflow integration test**

Create an integration test that:

- seeds account, positions, and instruments in SQLite;
- injects fake market-data provider quotes;
- injects fake Notion client;
- runs the workflow;
- verifies:
  - prices persisted,
  - daily review snapshot persisted,
  - signals persisted,
  - Notion `Signals` page updated,
  - Notion `Daily Review` page updated.

Skeleton:

```python
def test_refresh_and_sync_workflow_updates_prices_and_syncs_notion(session: Session) -> None:
    workflow = RefreshAndSyncWorkflow(...)
    result = workflow.run(stop_prices={"AAPL": Decimal("180")})

    assert result.snapshot.nav > Decimal("0")
    assert "Signals" in notion_client.pages
    assert "Daily Review" in notion_client.pages
    assert price_repository.latest_prices()["AAPL"].provider == "alpha_vantage"
```

- [ ] **Step 2: Run focused workflow test to verify missing workflow**

Run: `cd backend && ./.venv/bin/pytest tests/integration/test_refresh_and_sync_workflow.py -v`
Expected: FAIL with missing workflow.

- [ ] **Step 3: Implement the workflow**

Create `refresh_and_sync.py` with:

```python
class RefreshAndSyncWorkflow:
    def __init__(
        self,
        position_repository: PositionRepository,
        price_repository: PriceRepository,
        market_data_provider: MarketDataProvider,
        daily_review_workflow: DailyReviewWorkflow,
        notion_sync: NotionSync,
    ) -> None:
        ...

    def run(self, stop_prices: dict[str, Decimal]) -> DailyReviewResult:
        ...
```

Execution order:

1. load open positions from DB;
2. fetch latest prices for their symbols;
3. persist fetched `PricePoint` values;
4. update in-memory positions with refreshed latest prices;
5. run daily review workflow;
6. sync daily review page to Notion;
7. return `DailyReviewResult`.

- [ ] **Step 4: Re-run focused workflow test**

Run: `cd backend && ./.venv/bin/pytest tests/integration/test_refresh_and_sync_workflow.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/workflows/refresh_and_sync.py backend/src/pa_investing/workflows/daily_review.py backend/src/pa_investing/db/repositories.py backend/tests/integration/test_refresh_and_sync_workflow.py
git commit -m "feat: add refresh and sync workflow"
```

## Task 5: API Trigger Surface For The MVP Loop

**Files:**
- Modify: `backend/src/pa_investing/api/routes.py`
- Create: `backend/src/pa_investing/api/schemas.py`
- Modify: `backend/src/pa_investing/main.py`
- Modify: `backend/src/pa_investing/core/dependencies.py`
- Test: `backend/tests/integration/test_api_routes.py`

**Interfaces:**
- Produces: `POST /workflows/refresh-and-sync`
- Produces: `RefreshAndSyncRequest(stop_prices: dict[str, Decimal])`
- Produces: `RefreshAndSyncResponse(snapshot_id: str, nav: str, signal_count: int, notion_sync_enabled: bool)`

- [ ] **Step 1: Write failing API route test**

Add:

```python
def test_refresh_and_sync_route_returns_summary() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/workflows/refresh-and-sync",
        json={"stop_prices": {"AAPL": "180"}},
    )

    assert response.status_code == 200
    assert "snapshot_id" in response.json()
    assert "signal_count" in response.json()
```

Override dependencies in the test with a fake `RefreshAndSyncWorkflow` so the route test stays deterministic and does not call real Notion or Alpha Vantage.

- [ ] **Step 2: Run focused API tests to verify route missing**

Run: `cd backend && ./.venv/bin/pytest tests/integration/test_api_routes.py -v`
Expected: FAIL with missing route/schema wiring.

- [ ] **Step 3: Implement the request and route**

Create `api/schemas.py`:

```python
class RefreshAndSyncRequest(BaseModel):
    stop_prices: dict[str, Decimal]


class RefreshAndSyncResponse(BaseModel):
    snapshot_id: str
    nav: str
    signal_count: int
    notion_sync_enabled: bool
```

Add route:

```python
@router.post("/workflows/refresh-and-sync", response_model=RefreshAndSyncResponse)
def refresh_and_sync_route(
    payload: RefreshAndSyncRequest,
    workflow: RefreshAndSyncWorkflow = Depends(get_refresh_and_sync_workflow),
) -> RefreshAndSyncResponse:
    ...
```

- [ ] **Step 4: Re-run focused API tests**

Run: `cd backend && ./.venv/bin/pytest tests/integration/test_api_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/api/routes.py backend/src/pa_investing/api/schemas.py backend/src/pa_investing/main.py backend/src/pa_investing/core/dependencies.py backend/tests/integration/test_api_routes.py
git commit -m "feat: add refresh and sync API route"
```

## Task 6: Environment Docs, Local Runbook, And Full Verification

**Files:**
- Modify: `backend/README.md`
- Modify: `backend/.env.example`
- Test: full suite and local config checks

**Interfaces:**
- Produces: documented local setup for live Notion and Alpha Vantage
- Produces: verification commands for Phase 2 MVP

- [ ] **Step 1: Update the README runbook**

Add sections covering:

- required `.env` values for live Notion and Alpha Vantage;
- how to run migrations;
- how to trigger the workflow by API;
- how to verify that Notion sync is disabled safely when credentials are absent.

Include:

```bash
curl -X POST http://localhost:8000/workflows/refresh-and-sync \
  -H "Content-Type: application/json" \
  -d '{"stop_prices": {"AAPL": "180"}}'
```

- [ ] **Step 2: Run full verification**

Run:

```bash
cd backend
./.venv/bin/pytest
./.venv/bin/ruff check .
docker compose config
git status --short
```

Expected:

- full test suite passes;
- ruff is clean;
- `docker compose config` succeeds if Docker CLI is available, otherwise record the exact environment limitation;
- git status is clean after the final commit.

- [ ] **Step 3: Commit**

```bash
git add backend/README.md backend/.env.example
git commit -m "docs: add phase 2 MVP runbook"
```

## Self-Review

Spec coverage:

- Live Notion client and real workspace sync are covered by Tasks 1, 2, 4, and 5.
- One live delayed/free market price provider is covered by Task 3.
- End-to-end refresh loop is covered by Tasks 4 and 5.
- Backend/API trigger surface is covered by Task 5.
- Agent work remains explicitly deferred and is not included in any task.

Placeholder scan:

- No `TBD` or `TODO` placeholders remain.
- Later tasks only use interfaces defined in earlier tasks.

Type consistency:

- Settings fields are introduced in Task 1 before being consumed later.
- `RefreshAndSyncWorkflow.run(stop_prices: dict[str, Decimal]) -> DailyReviewResult` is defined before Task 5 consumes it.
- Notion sync methods for signal and daily review are introduced in Task 2 before Task 4 uses them.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-08-pa-investing-phase-2-mvp-notion-and-price-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
