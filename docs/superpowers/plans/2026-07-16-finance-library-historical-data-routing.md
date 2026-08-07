# Finance Library Historical Data Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable, persisted daily historical-market-data library for portfolio workflows and standalone research, using whole-series fallback across Yahoo, Twelve Data, and optional IBKR TWS/Gateway.

**Architecture:** Keep `pa_investing` as the finance library rather than adding another wrapper package. Add a focused `market_data/history` subsystem with immutable datasets, strict validation, provider provenance, and two entry paths: mapped portfolio instruments and temporary research identities. The PA app, scripts, skills, and agents consume one application service; they never call provider adapters or repositories directly.

**Tech Stack:** Python 3.12, Pydantic 2, SQLAlchemy 2, Alembic, PostgreSQL/SQLite, pandas, yfinance, httpx, pytest, Ruff.

## Global Constraints

- Initial frequency is daily only; no intraday bars.
- Initial providers are exactly `yahoo`, `twelve_data`, and optional `ibkr_tws`.
- Default provider order is Yahoo, Twelve Data, then IBKR.
- A request accepts one provider's entire series or rejects it; provider bars are never silently stitched together.
- Corporate-action-adjusted OHLC is the default analysis series.
- Preserve the least-adjusted provider series and its exact adjustment mode when available; never label split-adjusted IBKR bars as unadjusted.
- Portfolio mode starts from internal `instrument_id` and explicit provider mappings.
- Research mode may start from a standalone symbol query and must return ambiguity rather than silently selecting a listing.
- Research datasets remain outside the permanent instrument master until promotion.
- Validated datasets are persisted and reused by portfolio workflows, scripts, skills, and agents.
- Analysis requiring a complete window fails closed when no provider passes validation.
- Daily review may reuse the last validated dataset only when the response is explicitly marked stale.
- Provider failures and validation rejection reasons are persisted and returned to consumers.
- Market holidays are not missing observations.
- IBKR availability must never determine whether the core application runs.
- No order placement, cancellation, transfer, or trading interface is added.
- Reuse from Vibe-Trading is permitted under its MIT license only with the upstream copyright and license notice retained for copied substantial portions.

---

## Upstream Assessment

### Adopt

- A small loader protocol with provider name, availability diagnostics, and a normalized OHLCV return type.
- Shared bounded retries, wall-clock request budgets, and cache-safe failure behavior.
- Loader-boundary OHLC validation.
- Code-first provider registration with tests that prevent documentation and registry drift.
- Strict JSON output that converts non-finite values to null.
- IBKR's optional `ib_async` dependency and read-only connection profile idea.

### Adapt

- Replace Vibe-Trading's class-level availability fallback with per-request fallback. In the upstream implementation, Yahoo and Stooq report themselves as always available, so a live timeout, rate limit, empty payload, or symbol failure generally ends as unresolved rather than trying the next provider.
- Replace symbol-regex routing with explicit portfolio mappings and a candidate-based research resolver.
- Replace transient DataFrames and file cache entries with immutable persisted datasets and provenance.
- Replace generic bar dictionaries with typed daily bars that distinguish unadjusted, split-adjusted, and split-and-dividend-adjusted prices.
- Adapt the Yahoo loader through the maintained `yfinance` package instead of copying the full upstream loader registry.

### Avoid

- Do not copy the large Vibe-Trading loader catalogue.
- Do not make every provider a mandatory dependency.
- Do not let agents write one-off yfinance scripts.
- Do not allow a provider fallback to change silently between calls without recording it.
- Do not use IBKR Flex as a historical-price provider.
- Do not build an MCP layer, background queue, plugin system, or multi-agent runtime in this slice.

## Target File Structure

```text
backend/src/pa_investing/
  instruments/
    __init__.py
    resolution.py          # portfolio and research identity entry paths
  market_data/
    interfaces.py          # existing latest-quote interface remains supported
    history/
      __init__.py          # public historical-data exports
      models.py            # requests, bars, datasets, attempts, result types
      provider.py          # HistoricalDataProvider protocol
      validation.py        # whole-series validation
      router.py            # ordered per-request fallback
      service.py           # persistence-aware public application service
      providers/
        __init__.py
        yahoo.py
        twelve_data.py
        ibkr.py             # depends on optional shared IBKR client
  db/
    models.py
    repositories.py
  api/
    routes.py
    schemas.py
```

The existing latest-price and FX code remains in place. Historical routing is added alongside it, then later refresh workflows can consume the new service without a flag-day rewrite.

### Task 1: Define the Historical Data Contract

**Files:**
- Create: `backend/src/pa_investing/market_data/history/__init__.py`
- Create: `backend/src/pa_investing/market_data/history/models.py`
- Create: `backend/src/pa_investing/market_data/history/provider.py`
- Modify: `backend/src/pa_investing/domain/enums.py`
- Test: `backend/tests/unit/test_historical_data_models.py`

**Interfaces:**
- Produces: `HistoricalDataRequest`, `HistoricalInstrumentRef`, `DailyBar`, `HistoricalDataset`, `ProviderAttempt`, `HistoricalDataResult`, and `HistoricalDataProvider`.
- Consumes: existing permanent `Instrument` and `MarketDataMapping` models without modifying their meaning.

- [ ] **Step 1: Write failing model tests**

```python
from datetime import date, datetime, UTC
from decimal import Decimal

import pytest

from pa_investing.domain.enums import AdjustmentMode, InstrumentScope
from pa_investing.market_data.history.models import (
    DailyBar,
    HistoricalDataRequest,
    HistoricalInstrumentRef,
)


def test_research_request_has_stable_identity_without_permanent_instrument() -> None:
    ref = HistoricalInstrumentRef(
        scope=InstrumentScope.RESEARCH,
        display_symbol="NVDA",
        asset_class="equity",
        currency="USD",
        exchange="NASDAQ",
        provider_symbols={"yahoo": "NVDA", "twelve_data": "NVDA"},
    )
    request = HistoricalDataRequest(
        instrument=ref,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )

    assert request.instrument.instrument_id is None
    assert request.interval == "1d"
    assert request.required_adjustment == AdjustmentMode.ALL
    assert request.series_key.startswith("research:")


def test_daily_bar_rejects_invalid_ohlc() -> None:
    with pytest.raises(ValueError, match="OHLC"):
        DailyBar(
            trading_date=date(2026, 7, 15),
            open=Decimal("100"),
            high=Decimal("90"),
            low=Decimal("80"),
            close=Decimal("85"),
            volume=Decimal("1000"),
            adjustment_mode=AdjustmentMode.ALL,
        )
```

- [ ] **Step 2: Run the tests and verify contract types are missing**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_historical_data_models.py -q
```

Expected: collection fails because the historical-data models do not exist.

- [ ] **Step 3: Add exact enums**

Add to `domain/enums.py`:

```python
class AdjustmentMode(StrEnum):
    NONE = "none"
    SPLITS = "splits"
    ALL = "all"


class InstrumentScope(StrEnum):
    PORTFOLIO = "portfolio"
    RESEARCH = "research"


class HistoricalDatasetStatus(StrEnum):
    VALID = "valid"
    REJECTED = "rejected"
    STALE = "stale"
```

- [ ] **Step 4: Implement typed models and provider protocol**

Use Pydantic models with these fields:

```python
class HistoricalInstrumentRef(BaseModel):
    scope: InstrumentScope
    display_symbol: str
    asset_class: str
    currency: str
    exchange: str | None = None
    instrument_id: str | None = None
    provider_symbols: dict[str, str] = Field(default_factory=dict)
    provider_exchanges: dict[str, str] = Field(default_factory=dict)
    provider_ids: dict[str, str] = Field(default_factory=dict)


class HistoricalDataRequest(BaseModel):
    instrument: HistoricalInstrumentRef
    start_date: date
    end_date: date
    interval: Literal["1d"] = "1d"
    required_adjustment: AdjustmentMode = AdjustmentMode.ALL
    allow_stale: bool = False

    @property
    def series_key(self) -> str:
        identity = self.instrument.instrument_id or "|".join(
            (
                self.instrument.display_symbol,
                self.instrument.exchange or "",
                self.instrument.currency,
            )
        )
        return f"{self.instrument.scope.value}|{identity}|{self.required_adjustment.value}"


class DailyBar(BaseModel):
    trading_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None
    adjustment_mode: AdjustmentMode
    dividend: Decimal = Decimal("0")
    split_ratio: Decimal = Decimal("1")


class ProviderAttempt(BaseModel):
    provider: str
    accepted: bool
    started_at: datetime
    finished_at: datetime
    error_code: str | None = None
    message: str | None = None
    warnings: list[str] = Field(default_factory=list)


class HistoricalDataset(BaseModel):
    dataset_id: str
    series_key: str
    provider: str
    provider_symbol: str
    provider_exchange: str | None = None
    currency: str
    fetched_at: datetime
    bars: list[DailyBar]
    unadjusted_bars: list[DailyBar] | None = None
    warnings: list[str] = Field(default_factory=list)


class HistoricalDataResult(BaseModel):
    dataset: HistoricalDataset
    attempts: list[ProviderAttempt]
    stale: bool = False
```

`HistoricalDataProvider` must expose:

```python
class HistoricalDataProvider(Protocol):
    provider_name: str

    def diagnose(self) -> ProviderDiagnostic:
        raise NotImplementedError

    def fetch_daily(
        self,
        request: HistoricalDataRequest,
    ) -> HistoricalDataset:
        raise NotImplementedError
```

`ProviderDiagnostic` contains `available: bool`, `code: str`, and `message: str`.

- [ ] **Step 5: Run model tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_historical_data_models.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/pa_investing/domain/enums.py backend/src/pa_investing/market_data/history backend/tests/unit/test_historical_data_models.py
git commit -m "feat: define historical market data contracts"
```

### Task 2: Persist Immutable Historical Datasets

**Files:**
- Create: `backend/alembic/versions/0009_add_historical_market_data.py`
- Modify: `backend/src/pa_investing/db/models.py`
- Modify: `backend/src/pa_investing/db/repositories.py`
- Test: `backend/tests/integration/test_historical_data_repository.py`

**Interfaces:**
- Consumes: `HistoricalDataset` from Task 1.
- Produces: `HistoricalDataRepository.save_dataset()`, `latest_covering()`, `get_dataset()`, and `promote_series()`.

- [ ] **Step 1: Write repository tests**

Cover these named behaviors:

- `test_repository_saves_dataset_atomically_and_returns_exact_version`
- `test_research_series_can_be_linked_to_permanent_instrument_without_copying_bars`
- `test_latest_covering_does_not_return_partial_date_window`

The first test must save an adjusted dataset and an unadjusted companion series, reload it, and compare every Decimal and date. The promotion test must assert the same `dataset_id` remains active after an `instrument_id` is linked.

- [ ] **Step 2: Run repository tests and verify the tables are absent**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/integration/test_historical_data_repository.py -q
```

Expected: failure because historical persistence is not implemented.

- [ ] **Step 3: Add database tables**

Create:

```text
historical_series
  series_key              primary key
  instrument_id           nullable FK to instruments
  scope                   portfolio|research
  display_symbol
  asset_class
  currency
  exchange                nullable
  provider_identity_json  JSON/text
  active_dataset_id       nullable
  created_at
  updated_at

historical_datasets
  dataset_id              primary key
  series_key              FK
  provider
  provider_symbol
  provider_exchange       nullable
  currency
  start_date
  end_date
  fetched_at
  adjustment_mode
  unadjusted_mode         nullable
  warnings_json

historical_daily_bars
  id                      integer primary key
  dataset_id              FK
  trading_date
  adjustment_mode
  open/high/low/close     Numeric(24, 10)
  volume                  Numeric(30, 8), nullable
  dividend                Numeric(24, 10)
  split_ratio             Numeric(24, 10)
```

Add unique constraint `(dataset_id, trading_date, adjustment_mode)`. Use the project's `UTCDateTime` for timestamps. Store provider identities and warnings with SQLAlchemy JSON so PostgreSQL uses JSON-compatible storage and SQLite tests remain supported.

- [ ] **Step 4: Implement atomic dataset persistence**

`save_dataset()` must:

1. Upsert the stable `historical_series` metadata.
2. Insert a new immutable dataset row.
3. Insert all adjusted and optional unadjusted bars.
4. Set `active_dataset_id` only after every bar insert succeeds.
5. Flush but leave transaction commit ownership to the calling workflow.

`latest_covering(series_key, start_date, end_date)` must return a dataset only when its stored range covers the complete requested boundaries.

- [ ] **Step 5: Run migration and repository tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/integration/test_historical_data_repository.py tests/integration/test_repositories.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/0009_add_historical_market_data.py backend/src/pa_investing/db/models.py backend/src/pa_investing/db/repositories.py backend/tests/integration/test_historical_data_repository.py
git commit -m "feat: persist immutable historical datasets"
```

### Task 3: Implement Strict Whole-Series Validation

**Files:**
- Create: `backend/src/pa_investing/market_data/history/validation.py`
- Test: `backend/tests/unit/test_historical_data_validation.py`

**Interfaces:**
- Consumes: `HistoricalDataRequest` and `HistoricalDataset`.
- Produces: `validate_dataset(request, dataset, calendar_dates=None) -> ValidationResult`.

- [ ] **Step 1: Write validation tests**

Tests must cover:

- duplicate or descending dates are rejected;
- future dates are rejected;
- non-positive prices and broken OHLC relationships are rejected;
- wrong listing currency is rejected;
- adjusted analysis requested but only unadjusted bars returned is rejected;
- missing weekdays are warnings when no exchange calendar is supplied;
- explicitly supplied exchange holidays are not missing dates;
- insufficient coverage at either requested boundary is rejected;
- one invalid bar rejects the entire dataset.

Use a `ValidationResult` with:

```python
class ValidationResult(BaseModel):
    accepted: bool
    code: str
    warnings: list[str]
    message: str
```

- [ ] **Step 2: Run tests and verify the validator is missing**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_historical_data_validation.py -q
```

Expected: collection failure for the missing validation module.

- [ ] **Step 3: Implement deterministic validation**

Validation order must be stable:

1. request range and dataset identity;
2. currency and exchange metadata;
3. date ordering and uniqueness;
4. future-date check;
5. OHLC and positivity;
6. required adjustment mode;
7. boundary coverage;
8. expected-session coverage.

Do not fetch calendars inside the validator. Accept a supplied `set[date]` so calendar acquisition remains a separate concern and tests stay deterministic.

- [ ] **Step 4: Run validation tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_historical_data_validation.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/market_data/history/validation.py backend/tests/unit/test_historical_data_validation.py
git commit -m "feat: validate complete historical data series"
```

### Task 4: Add Yahoo as the Primary Historical Provider

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/src/pa_investing/market_data/history/providers/__init__.py`
- Create: `backend/src/pa_investing/market_data/history/providers/yahoo.py`
- Test: `backend/tests/unit/test_yahoo_historical_provider.py`

**Interfaces:**
- Consumes: explicit Yahoo symbol from `HistoricalInstrumentRef.provider_symbols`.
- Produces: `YahooHistoricalDataProvider.fetch_daily()`.

- [ ] **Step 1: Add failing provider tests**

Mock the yfinance call seam rather than the network. Cover:

- adjusted OHLC is produced from `Adj Close / Close`;
- original OHLC is preserved with `AdjustmentMode.NONE`;
- dividends and splits are retained;
- end date is converted from inclusive library semantics to yfinance's exclusive end;
- returned exchange/currency metadata must match the resolved identity;
- empty or malformed frames raise `HistoricalProviderError`;
- no symbol guessing occurs inside the provider.

- [ ] **Step 2: Run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_yahoo_historical_provider.py -q
```

Expected: failure because the provider does not exist.

- [ ] **Step 3: Add yfinance as a bounded dependency**

Add:

```toml
"pandas>=2.2,<3.0",
"yfinance>=1.1,<2.0",
```

The implementation must call yfinance with:

```python
auto_adjust=False
actions=True
repair=False
keepna=True
progress=False
threads=False
timeout=10
```

Use the returned adjustment factor to produce `AdjustmentMode.ALL` OHLC. Treat a missing or zero raw close as invalid rather than inventing a factor.

- [ ] **Step 4: Implement provider diagnostics and fetch**

`diagnose()` verifies the Python dependency is importable; it does not make a network request.

`fetch_daily()` requires `provider_symbols["yahoo"]`. If absent, raise:

```python
HistoricalProviderError(
    code="mapping_missing",
    message="Yahoo mapping is missing for <display_symbol>",
)
```

- [ ] **Step 5: Run provider tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_yahoo_historical_provider.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/src/pa_investing/market_data/history/providers backend/tests/unit/test_yahoo_historical_provider.py
git commit -m "feat: add Yahoo historical data provider"
```

### Task 5: Add Twelve Data as the Mapped Fallback

**Files:**
- Create: `backend/src/pa_investing/market_data/history/providers/twelve_data.py`
- Test: `backend/tests/unit/test_twelve_data_historical_provider.py`

**Interfaces:**
- Consumes: Twelve Data API key and explicit symbol/exchange mapping.
- Produces: `TwelveDataHistoricalDataProvider.fetch_daily()`.

- [ ] **Step 1: Write HTTP-mocked tests**

Cover:

- one `time_series` request with `adjust=none`;
- one `time_series` request with `adjust=all`;
- exact date alignment between the two responses;
- response metadata currency and exchange validation;
- `price_multiplier` application for units such as GBX to GBP;
- provider error envelopes;
- mismatched adjusted/unadjusted dates reject the complete provider result;
- bounded pagination when a requested window exceeds one response.

- [ ] **Step 2: Run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_twelve_data_historical_provider.py -q
```

Expected: failure because the provider does not exist.

- [ ] **Step 3: Implement the adapter**

Use `httpx.Client` with the same authorization convention as the existing latest-quote adapter. Use `/time_series`, `interval=1day`, explicit `start_date`, `end_date`, `symbol`, and optional `exchange`.

Do not merge a partial adjusted response with a larger unadjusted response. The provider either returns an aligned complete dataset or raises a typed error.

- [ ] **Step 4: Run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_twelve_data_historical_provider.py tests/unit/test_twelve_data_provider.py -q
```

Expected: all tests pass and the existing latest-quote adapter remains unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/market_data/history/providers/twelve_data.py backend/tests/unit/test_twelve_data_historical_provider.py
git commit -m "feat: add Twelve Data historical fallback"
```

### Task 6: Implement Portfolio and Research Instrument Resolution

**Files:**
- Create: `backend/src/pa_investing/instruments/__init__.py`
- Create: `backend/src/pa_investing/instruments/resolution.py`
- Modify: `backend/src/pa_investing/db/repositories.py`
- Test: `backend/tests/unit/test_instrument_resolution.py`
- Test: `backend/tests/integration/test_instrument_resolution.py`

**Interfaces:**
- Produces: `InstrumentResolutionService.for_portfolio(instrument_id)` and `search(query)`.
- Consumes: permanent instrument records, market-data mappings, Yahoo search candidates, and Twelve Data symbol-search candidates.

- [ ] **Step 1: Write portfolio-resolution tests**

Assert that a permanent instrument resolves to:

```python
HistoricalInstrumentRef(
    scope=InstrumentScope.PORTFOLIO,
    instrument_id=instrument_id,
    display_symbol="SGLN",
    currency="GBP",
    exchange="LSEETF",
    provider_symbols={
        "yahoo": "SGLN.L",
        "twelve_data": "SGLN",
    },
    provider_exchanges={"twelve_data": "LSE"},
    provider_ids={"ibkr_tws": "conid:<integer>"},
)
```

Missing provider mappings remain absent; resolution must not guess them.

- [ ] **Step 2: Write research-resolution tests**

Cover:

- `NVDA` returns a confirmed unambiguous US candidate when provider results agree;
- `SGLN` returns multiple candidates when exchange is omitted;
- `SGLN LSE` narrows to the LSE listing;
- candidates expose provider identifiers, currency, exchange/MIC, and asset class;
- ambiguous resolution cannot be converted into a `HistoricalDataRequest`;
- no permanent instrument row is inserted during search.

- [ ] **Step 3: Run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_instrument_resolution.py tests/integration/test_instrument_resolution.py -q
```

Expected: failure because the service does not exist.

- [ ] **Step 4: Implement candidate resolution**

Define:

```python
class InstrumentCandidate(BaseModel):
    display_symbol: str
    name: str
    asset_class: str
    currency: str
    exchange: str | None
    mic_code: str | None
    provider_symbols: dict[str, str]
    provider_exchanges: dict[str, str]
    confidence: Decimal


class InstrumentSearchResult(BaseModel):
    query: str
    candidates: list[InstrumentCandidate]
    unambiguous: bool
```

Research search is advisory. Only an unambiguous result or an explicitly selected candidate becomes a research `HistoricalInstrumentRef`.

- [ ] **Step 5: Add promotion linking**

Add `promote_research_series(series_key: str, instrument_id: str) -> None`
to `InstrumentResolutionService`.

It verifies currency and exchange compatibility before linking the existing series to the permanent instrument. It does not copy bars or create a new dataset.

- [ ] **Step 6: Run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_instrument_resolution.py tests/integration/test_instrument_resolution.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/src/pa_investing/instruments backend/src/pa_investing/db/repositories.py backend/tests/unit/test_instrument_resolution.py backend/tests/integration/test_instrument_resolution.py
git commit -m "feat: resolve portfolio and research instruments"
```

### Task 7: Add Per-Request Whole-Series Routing

**Files:**
- Create: `backend/src/pa_investing/market_data/history/router.py`
- Test: `backend/tests/unit/test_historical_data_router.py`

**Interfaces:**
- Consumes: ordered `HistoricalDataProvider` instances and `validate_dataset`.
- Produces: `HistoricalDataRouter.fetch(request) -> HistoricalDataResult`.

- [ ] **Step 1: Write router tests**

Cover the exact routing behavior with these tests:

- `test_timeout_from_yahoo_falls_back_to_twelve_data`
- `test_invalid_yahoo_ohlc_falls_back_to_twelve_data`
- `test_partial_yahoo_series_is_not_stitched_with_twelve_data`
- `test_all_failures_return_every_attempt_reason`
- `test_provider_without_mapping_is_skipped_with_mapping_missing_attempt`

The accepted result must contain bars from exactly one provider.

- [ ] **Step 2: Run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_historical_data_router.py -q
```

Expected: failure because the router does not exist.

- [ ] **Step 3: Implement bounded routing**

Default provider order:

```python
("yahoo", "twelve_data", "ibkr_tws")
```

For every provider:

1. record attempt start;
2. run diagnostics;
3. fetch with a provider-specific timeout;
4. validate the complete dataset;
5. accept and stop, or record the typed rejection;
6. never mutate a previously returned dataset.

When all providers fail, raise `HistoricalDataUnavailable` containing the ordered attempts.

- [ ] **Step 4: Run router tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_historical_data_router.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/market_data/history/router.py backend/tests/unit/test_historical_data_router.py
git commit -m "feat: route complete historical series"
```

### Task 8: Add the Persistence-Aware Public Service

**Files:**
- Create: `backend/src/pa_investing/market_data/history/service.py`
- Modify: `backend/src/pa_investing/core/dependencies.py`
- Test: `backend/tests/integration/test_historical_data_service.py`

**Interfaces:**
- Produces the public library entry point:

```python
class HistoricalDataService:
    def get_for_portfolio(
        self,
        instrument_id: str,
        start_date: date,
        end_date: date,
        *,
        allow_stale: bool = False,
    ) -> HistoricalDataResult:
        raise NotImplementedError

    def get_for_research(
        self,
        instrument: HistoricalInstrumentRef,
        start_date: date,
        end_date: date,
        *,
        allow_stale: bool = False,
    ) -> HistoricalDataResult:
        raise NotImplementedError
```

- [ ] **Step 1: Write integration tests**

Cover:

- an existing active dataset covering the requested range causes no provider call;
- an uncovered range triggers the router and persists the accepted dataset;
- provider failure with `allow_stale=False` raises;
- provider failure with `allow_stale=True` returns the last validated dataset with `stale=True`;
- stale fallback preserves all provider-attempt warnings;
- a failed fetch never replaces `active_dataset_id`;
- portfolio and research calls share the same router and repository.

- [ ] **Step 2: Run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/integration/test_historical_data_service.py -q
```

Expected: failure because the service does not exist.

- [ ] **Step 3: Implement service transaction boundaries**

The service:

1. resolves identity;
2. checks persisted coverage;
3. routes only when necessary;
4. saves the accepted dataset;
5. records a provider run with attempt counts and warnings;
6. commits only after the dataset and provider run are consistent;
7. returns typed stale status when permitted.

Do not embed HTTP, SQLAlchemy queries, or provider-specific symbol logic in this class.

- [ ] **Step 4: Wire dependencies**

Add a dependency factory that constructs the repository, resolver, providers, router, and service. IBKR is included only when its optional client configuration is enabled; its absence is represented by a diagnostic, not an import failure.

- [ ] **Step 5: Run service and regression tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/integration/test_historical_data_service.py tests/integration/test_refresh_and_sync_workflow.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/pa_investing/market_data/history/service.py backend/src/pa_investing/core/dependencies.py backend/tests/integration/test_historical_data_service.py
git commit -m "feat: expose persisted historical data service"
```

### Task 9: Expose Thin App and Agent Boundaries

**Files:**
- Modify: `backend/src/pa_investing/api/schemas.py`
- Modify: `backend/src/pa_investing/api/routes.py`
- Test: `backend/tests/integration/test_api_routes.py`
- Create: `backend/src/pa_investing/scripts/fetch_historical_data.py`
- Test: `backend/tests/unit/test_fetch_historical_data.py`

**Interfaces:**
- Produces:
  - `GET /analysis/instruments/search?q=<query>`
  - `GET /analysis/market-data/{instrument_id}?start=YYYY-MM-DD&end=YYYY-MM-DD`
  - `POST /analysis/market-data/research`
  - one CLI for local diagnostics.

- [ ] **Step 1: Write API tests**

Assert:

- permanent instrument history requires analytics authentication;
- research request accepts an explicitly selected candidate object;
- response includes `dataset_id`, provider, exact adjustment modes, stale flag, warnings, and attempts;
- no secrets, raw provider payloads, or filesystem paths appear;
- ambiguous search returns candidates and does not fetch bars.

- [ ] **Step 2: Run API tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/integration/test_api_routes.py -q
```

Expected: new route tests fail with 404.

- [ ] **Step 3: Implement thin routes**

Routes only validate input, call `HistoricalDataService` or `InstrumentResolutionService`, and serialize results. They contain no provider order, fallback, validation, or persistence logic.

- [ ] **Step 4: Add diagnostic CLI**

Support:

```bash
python -m pa_investing.scripts.fetch_historical_data \
  --research "NVDA" \
  --start 2025-01-01 \
  --end 2025-12-31
```

If resolution is ambiguous, print candidates and exit with code 2. If all providers fail, print ordered attempt reasons and exit with code 1. On success, print provider, dataset ID, date coverage, bar count, adjustment modes, and warnings.

- [ ] **Step 5: Run API and CLI tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/integration/test_api_routes.py tests/unit/test_fetch_historical_data.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/pa_investing/api backend/src/pa_investing/scripts/fetch_historical_data.py backend/tests/integration/test_api_routes.py backend/tests/unit/test_fetch_historical_data.py
git commit -m "feat: expose historical data library"
```

### Task 10: Documentation, Attribution, and Final Verification

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Create: `backend/THIRD_PARTY_NOTICES.md`
- Modify: `docs/superpowers/specs/2026-07-10-pa-investing-external-inspiration-note.md`

**Interfaces:**
- Documents the public contract for app and agent consumers.

- [ ] **Step 1: Add operational documentation**

Document:

- provider order and how to override it;
- portfolio versus research entry mode;
- mapping setup for Yahoo, Twelve Data, and IBKR;
- corporate-action semantics;
- stale and fail-closed behavior;
- research-series promotion;
- provider diagnostics;
- why agents must not call providers directly.

- [ ] **Step 2: Add upstream attribution**

If any Vibe-Trading code is copied rather than independently reimplemented, add its MIT copyright and license text to `THIRD_PARTY_NOTICES.md` and identify the adapted files. If only ideas are used, state that no substantial source was copied.

- [ ] **Step 3: Run the complete verification suite**

Run:

```bash
cd backend
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
```

Expected: all tests pass and Ruff reports no errors.

- [ ] **Step 4: Verify migration**

Run against a disposable database:

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/alembic downgrade 0008_operational_foundation
.venv/bin/alembic upgrade head
```

Expected: upgrade, downgrade, and re-upgrade complete without errors.

- [ ] **Step 5: Commit**

```bash
git add README.md backend/README.md backend/THIRD_PARTY_NOTICES.md docs/superpowers/specs/2026-07-10-pa-investing-external-inspiration-note.md
git commit -m "docs: document historical data routing"
```

## Completion Criteria

- The same daily historical-data service works for permanent portfolio instruments and standalone research.
- A provider failure during a request triggers the next configured provider.
- No successful dataset contains bars from more than one provider.
- Every accepted dataset has strict adjustment, listing, currency, date, and OHLC provenance.
- Research lookups do not create permanent instruments.
- Promotion links the existing dataset without refetching.
- Agents and app routes consume the service rather than provider adapters.
- Yahoo and Twelve Data work without IBKR.
- IBKR absence is diagnostic only.
- Existing latest-price, FX, broker-import, and daily-review tests remain green.
