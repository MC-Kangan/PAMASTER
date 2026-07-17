# PA Investing Workflow

This repository contains a personal-account investing workflow that is being built in phases.

The working architecture today is:

- Notion as the first summary and operating surface
- Python backend as the compute and workflow layer
- PostgreSQL as the structured source of truth
- browser analytics pages for deeper drilldown on phone and desktop

The system is intentionally analysis-only. It does not place trades or submit broker orders.

The current mixed-currency workflow supports explicit provider mappings, USD/GBP FX conversion,
and IBKR Flex cash balances. Cash-flow-aware returns and broker NAV reconciliation are still
required before drawdown and return outputs are treated as investment-grade analytics.

## Current Status

The project has:

- completed the Phase 1 backend foundation
- completed the first visible Phase 2 MVP loop for demo data
- completed the Notion portfolio settings/accounts/positions backend slice
- completed the general internal instrument identity backend slice
- completed the mapped quote, FX, and reporting-currency backend slice
- completed the reusable daily historical-data routing foundation

In practical terms, the repo can now:

- seed a demo portfolio
- import IBKR positions through a NAS-suitable Flex Web Service connector
- preserve broker cost separately from persistent manual cost overrides
- identify instruments internally instead of treating ticker symbols as database keys
- retain optional generic provider identifiers such as IBKR `conid`
- support the same display symbol on different venues without merging positions or prices
- exclude positions with unavailable cost basis from reliable P&L totals
- refresh prices through a live market-data adapter
- map each instrument to a provider symbol/listing and normalize minor currency units
- persist timestamped quotes and FX rates with source and quality metadata
- calculate USD/GBP reporting values with explicit incomplete-data coverage
- compute and persist snapshots and signals
- sync `Signals` and `Daily Review` to Notion
- read portfolio base currency and manual cost overrides from Notion
- sync compact `Settings`, `Accounts`, and `Positions` views without overwriting user fields
- show all holdings, rounded review totals, portfolio weights, and prior-day NAV change in Notion
- expose a manual refresh API
- expose a performance-history API
- expose responsive allocation and NAV-history charts for phone and desktop browsers
- protect browser analytics routes with a simple auth gate
- support a private NAS deployment model using Tailscale, HTTPS, and application authentication
- provide a NAS-runnable command for the fixed snapshot cadence
- fetch, validate, persist, and reuse daily historical bars for portfolio and research use
- fall back from Yahoo to Twelve Data without stitching providers into one series
- preserve adjusted and least-adjusted bar provenance with explicit stale-data behavior

## What Has Been Implemented

### Phase 1: Backend Foundation

Implemented:

- FastAPI backend scaffold
- SQLAlchemy models and repositories
- Alembic migrations
- pytest and Ruff setup
- Docker and Docker Compose scaffold
- domain models for:
  - accounts
  - instruments
  - positions
  - price points
  - portfolio snapshots
  - signals
- CSV position import
- broker import workflow boundary
- manual price provider
- deterministic sizing and stop/reference signal rules
- fake Notion client for local and test flows
- daily review workflow and persistence
- minimal analytics pages and API routes

### Phase 2: First MVP Loop

Implemented:

- live Notion client behind the existing interface
- idempotent Notion upsert behavior using `External ID`
- Notion sync targets:
  - `Settings`
  - `Accounts`
  - `Positions`
  - `Signals`
  - `Daily Review`
- Alpha Vantage market-data provider
- Twelve Data mapped quote and FX provider
- end-to-end refresh-and-sync workflow
- `POST /workflows/refresh-and-sync`
- demo portfolio seed flow
- IBKR broker import scaffolding:
  - Flex Web Service connector for secure scheduled NAS import
  - Client Portal Gateway connector kept as a local/manual fallback
  - shared import workflow that upserts broker accounts and positions
- backend runbook for local MVP execution

The demo seed flow includes:

- one demo account: `pa-demo`
- starter symbols:
  - `SPGI`
  - `ASML`
  - `SAP`
  - `SGLN`
  - `SMH`

### Phase 2: Performance History Slice

Implemented so far:

- snapshot-based performance history service
- ordered snapshot history reads from the repository layer
- `GET /analysis/performance`
- performance response schemas
- simple browser auth helper and config
- responsive performance-oriented portfolio analysis page shell
- fixed snapshot cadence definition:
  - `00:00`
  - `06:00`
  - `12:00`
  - `18:00`
- one-shot scheduled snapshot command that reuses the refresh API
- successful refresh transactions commit before any Notion write
- bearer-token protection for the refresh workflow trigger
- performance-history and scheduling runbook
- responsive position-allocation donut chart
- responsive historical NAV line chart
- one-snapshot-per-day performance series for daily return calculations

Still pending in this slice:

- entering the four command triggers in the uGREEN NAS scheduler
- production NAS authentication and visual verification on the deployed URL

### Phase 2: General Instrument Identity Slice

Implemented:

- stable internal instrument IDs for positions and historical prices
- deterministic migration of all legacy symbol-keyed data
- optional generic provider identifiers with uniqueness safeguards
- IBKR Flex parsing for `conid`, ISIN, local symbol, and listing venue when available
- Client Portal parsing for `conid` and venue when available
- duplicate-symbol support across distinct venues
- ambiguous symbol-only quote protection pending provider mapping in the FX/quote slice
- internal-ID-based Notion position external IDs with legacy external-ID read compatibility

### Phase 2: Quotes, FX, and Reporting Currency Slice

Implemented:

- provider-specific market-data mappings keyed by internal instrument ID
- timestamped quote and FX history with provider and quality metadata
- configurable Twelve Data adapter for mapped quotes and currency conversion
- listing currency and exchange validation before a quote can replace a broker mark
- persisted quote selection with IBKR EOD fallback
- explicit price multipliers for provider units such as GBX to GBP
- USD/GBP reporting values and coverage-aware aggregate calculations
- stale and missing FX status in schema-flexible Notion payloads
- CSV mapping importer and instrument-ID output in the position inspection command

Live Twelve Data validation is complete for the currently mapped portfolio. Unsupported listings
continue to use their timestamped IBKR Flex marks and are labelled as fallbacks.

### Historical Data Library

The reusable daily-history layer lives under `pa_investing.market_data.history`. It is shared by
the PA application, local scripts, and future agent or skill consumers.

Its current contract is deliberately narrow:

- daily bars only
- provider order: Yahoo, then Twelve Data
- one complete provider series per dataset; bars are never silently stitched
- split-and-dividend-adjusted OHLC is the default analysis series
- the least-adjusted provider series is retained when available
- portfolio requests use internal instrument IDs and explicit provider mappings
- research requests use candidate resolution and return ambiguity instead of guessing a listing
- accepted datasets are immutable, versioned, persisted, and reused
- analysis fails closed when all providers fail
- stale data is returned only when the caller explicitly opts in

IBKR TWS/Gateway historical data is intentionally not part of this slice. It remains a separate,
optional overlay so the NAS and research library do not depend on a logged-in IBKR session.

### Canonical Instrument References

User-facing instrument references use a compact Bloomberg-style convention while provider
symbols remain internal mappings:

```text
ADBE US
GLEN LN
SMH LN
```

The first token is the display symbol and the second is a canonical market code. Search accepts
case-insensitive input and normalizes aliases such as `U.S.` to `US`. An accepted candidate
returns `canonical_reference` alongside its exact exchange, currency, and provider mappings.
For example, `GLEN LN` may map to Yahoo `GLEN.L`, Twelve Data `GLEN` on `LSE`, and an IBKR
contract identifier without exposing those provider-specific values to finance skills.

### Deterministic Finance Skills

The reusable finance layer lives under `pa_investing.finance`. Skills consume an already
validated, adjusted daily `HistoricalDataset`; they do not download data or create PA signals.
The default bundle is:

```text
daily_market_review.v1
├── technical_snapshot.v1
├── candlestick_events.v1
└── market_risk_snapshot.v1
```

`FinanceAnalysisService` supports both portfolio instruments and standalone research:

```python
result = service.analyze_portfolio(
    instrument_id,
    as_of=date.today(),
)
```

The standalone smoke-test command runs the same default bundle:

```bash
cd backend
.venv/bin/python -m pa_investing.scripts.analyze_instrument \
  --research "ADBE US" \
  --as-of 2026-07-15
```

The default lookback is 365 calendar days. Callers may select explicit skill IDs, override
validated thresholds, or register additional deterministic or model-assisted skills through
`SkillRegistry`. Skill failures are isolated and produce a partial analysis with structured
warnings and a deterministic summary.

## Code Structure

The main application code lives in [backend/src/pa_investing](backend/src/pa_investing/).

High-level layout:

- `analytics/`
  - pure analytics logic
  - snapshot building
  - performance-history calculations
- `analytics_app/`
  - browser-facing HTML page builders
- `api/`
  - FastAPI route handlers
  - request and response schemas
  - browser auth helper
- `audit/`
  - audit event domain objects
- `brokers/`
  - import interfaces
  - CSV importer
  - IBKR Flex Web Service connector
  - optional IBKR Client Portal Gateway connector
- `core/`
  - settings
  - dependency wiring
- `db/`
  - SQLAlchemy base
  - ORM models
  - repositories
  - session factory
- `domain/`
  - central business models and enums
- `llm/`
  - mockable LLM abstraction and summarizer interface
- `market_data/`
  - market-data interface
  - manual provider
  - Alpha Vantage provider
  - Twelve Data provider
  - mapped quote selection
  - persisted daily-history contracts, validation, routing, and providers
- `instruments/`
  - strict portfolio resolution
  - standalone research candidate resolution
- `notion/`
  - client interfaces
  - live Notion adapter
  - payload mapping and sync logic
- `scripts/`
  - CLI entrypoints for demo portfolio seeding and scheduled snapshots
- `seeds/`
  - reusable seeding helpers
- `signals/`
  - signal rules and evaluation service
- `sizing/`
  - deterministic sizing models
- `workflows/`
  - daily review
  - refresh-and-sync
  - snapshot schedule definition

## Backend Flow

The current backend flow is roughly:

1. read configured portfolio settings and manual cost overrides from Notion
2. load reconciled positions from PostgreSQL
3. refresh prices through a market-data provider
4. update stored marks
5. build a portfolio snapshot
6. generate deterministic signals
7. persist snapshots, signals, settings, and audit data
8. sync accounts, positions, signals, and summary outputs to Notion
9. expose deeper history through browser analytics endpoints

## Broker Import Direction

For IBKR, the preferred deployable path is Flex Web Service. It uses a token and query id
created in IBKR Client Portal, does not require storing the IBKR username/password in this
app, and fits a NAS scheduler. It is best for daily or intermittent position/account reads,
not intraday trading workflows.

The Client Portal Gateway connector remains in the codebase for local manual testing, but it
is not the recommended NAS path because it depends on an interactive browser login and a
short-lived session. The app still does not place trades.

## Current API Surface

Implemented routes:

- `GET /health`
- `GET /analysis/portfolio`
- `GET /analysis/signal/{signal_id}`
- `GET /analysis/performance`
- `GET /analysis/current`
- `GET /analysis/transactions`
- `GET /analysis/operations`
- `GET /analysis/instruments/search?q={query}`
- `GET /analysis/market-data/{instrument_id}?start=YYYY-MM-DD&end=YYYY-MM-DD`
- `POST /analysis/market-data/research`
- `POST /workflows/refresh-and-sync`

## What Still Needs To Be Done For The First Real Notion MVP

The main missing step is no longer code structure. It is environment hookup:

1. configure a real `.env`
2. connect real Notion databases
3. run the seed command
4. run the refresh workflow
5. inspect the real Notion output

For the UGREEN NAS deployment, follow the canonical
[UGREEN DXP4800 Plus operating runbook](backend/README.md#ugreen-dxp4800-plus-deployment).
The next app-layer milestone begins only after seven consecutive successful 06:00 Europe/London
morning cycles.

For real IBKR position import, configure `PA_IBKR_FLEX_TOKEN` and
`PA_IBKR_FLEX_QUERY_ID`. The existing import command auto-selects Flex when those values are
present and otherwise falls back to the local Gateway connector.

Imported positions now retain broker cost provenance. A manual average-cost override, including
an explicit zero for a genuinely free share, survives later broker imports. Positions without a
reliable cost basis display `unavailable` and are excluded from reliable P&L. The user-facing
Notion `Cost Override` field is part of the next implementation slice.

IBKR Flex imports now also persist a provider-neutral trade ledger and a same-report NAV/cash
reconciliation. Repeated imports update the same external trade IDs rather than duplicating them.
Provider runs record IBKR import, market-data refresh, and enabled Notion sync status for the
authenticated operations endpoint.

## What Still Needs To Be Done For The Next MVP Slice

For the performance-history slice, the main next steps are:

1. improve the browser performance view from a responsive shell into a richer charting surface
2. verify the richer view at both computer and smartphone browser widths
3. configure the four fixed task times on the uGREEN NAS

## Important Boundaries

The project keeps these boundaries on purpose:

- Notion is a UI adapter, not the source of truth
- PostgreSQL remains the structured source of truth
- secrets stay in backend config, never in Notion
- deterministic backend rules own numeric recommendations
- the system remains read-only and analysis-only
- browser analytics auth is separate from backend-to-Notion integration

## Key Files

Good starting points if you want to orient yourself quickly:

- top-level project status: [README.md](README.md)
- backend runbook: [backend/README.md](backend/README.md)
- app entrypoint: [backend/src/pa_investing/main.py](backend/src/pa_investing/main.py)
- route layer: [backend/src/pa_investing/api/routes.py](backend/src/pa_investing/api/routes.py)
- dependency wiring: [backend/src/pa_investing/core/dependencies.py](backend/src/pa_investing/core/dependencies.py)
- refresh workflow: [backend/src/pa_investing/workflows/refresh_and_sync.py](backend/src/pa_investing/workflows/refresh_and_sync.py)
- performance history logic: [backend/src/pa_investing/analytics/performance.py](backend/src/pa_investing/analytics/performance.py)
- demo seed CLI: [backend/src/pa_investing/scripts/seed_demo_portfolio.py](backend/src/pa_investing/scripts/seed_demo_portfolio.py)
- IBKR import CLI: [backend/src/pa_investing/scripts/import_ibkr_positions.py](backend/src/pa_investing/scripts/import_ibkr_positions.py)
- scheduled snapshot CLI: [backend/src/pa_investing/scripts/run_scheduled_snapshot.py](backend/src/pa_investing/scripts/run_scheduled_snapshot.py)

## Related Documents

- architecture design:
  [2026-07-07-pa-investing-system-architecture-design.md](docs/superpowers/specs/2026-07-07-pa-investing-system-architecture-design.md)
- MVP roadmap pivot:
  [2026-07-08-pa-investing-mvp-roadmap-pivot-design.md](docs/superpowers/specs/2026-07-08-pa-investing-mvp-roadmap-pivot-design.md)
- demo seed design:
  [2026-07-10-pa-investing-demo-seed-portfolio-design.md](docs/superpowers/specs/2026-07-10-pa-investing-demo-seed-portfolio-design.md)
- demo seed plan:
  [2026-07-10-pa-investing-demo-seed-portfolio-plan.md](docs/superpowers/plans/2026-07-10-pa-investing-demo-seed-portfolio-plan.md)
- performance history design:
  [2026-07-10-pa-investing-performance-history-mvp-design.md](docs/superpowers/specs/2026-07-10-pa-investing-performance-history-mvp-design.md)
- performance history plan:
  [2026-07-10-pa-investing-performance-history-mvp-plan.md](docs/superpowers/plans/2026-07-10-pa-investing-performance-history-mvp-plan.md)
