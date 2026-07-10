# PA Investing Workflow

This repository contains a personal-account investing workflow that is being built in phases.

The working architecture today is:

- Notion as the first summary and operating surface
- Python backend as the compute and workflow layer
- PostgreSQL as the structured source of truth
- browser analytics pages for deeper drilldown on phone and desktop

The system is intentionally analysis-only. It does not place trades or submit broker orders.

The current mixed-currency demo proves the workflow, not portfolio accounting. FX conversion,
exchange-specific symbols, cash flows, and transaction-aware returns must be added before NAV,
drawdown, and sizing outputs are treated as investment-grade analytics.

## Current Status

The project has:

- completed the Phase 1 backend foundation
- completed the first visible Phase 2 MVP loop for demo data
- started the next MVP slice for performance history analytics

In practical terms, the repo can now:

- seed a demo portfolio
- refresh prices through a live market-data adapter
- compute and persist snapshots and signals
- sync `Signals` and `Daily Review` to Notion
- expose a manual refresh API
- expose a performance-history API
- protect browser analytics routes with a simple auth gate
- provide a NAS-runnable command for the fixed snapshot cadence

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
  - `Signals`
  - `Daily Review`
- Alpha Vantage market-data provider
- end-to-end refresh-and-sync workflow
- `POST /workflows/refresh-and-sync`
- demo portfolio seed flow
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

Still pending in this slice:

- richer visual chart rendering
- entering the four command triggers in the uGREEN NAS scheduler
- visual verification of the richer dashboard on computer and smartphone browsers

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
  - import interfaces and CSV importer
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

1. load positions from PostgreSQL
2. refresh prices through a market-data provider
3. update stored marks
4. build a portfolio snapshot
5. generate deterministic signals
6. persist snapshots, signals, and audit data
7. sync summary outputs to Notion
8. expose deeper history through browser analytics endpoints

## Current API Surface

Implemented routes:

- `GET /health`
- `GET /analysis/portfolio`
- `GET /analysis/signal/{signal_id}`
- `GET /analysis/performance`
- `POST /workflows/refresh-and-sync`

## What Still Needs To Be Done For The First Real Notion MVP

The main missing step is no longer code structure. It is environment hookup:

1. configure a real `.env`
2. connect real Notion databases
3. run the seed command
4. run the refresh workflow
5. inspect the real Notion output

For Compose or NAS deployment, set `PA_WORKFLOW_API_TOKEN` in `backend/.env`; scheduled
snapshot commands read it from the environment and send it as a Bearer token. Compose keeps
analytics auth enabled by default. Blank enabled analytics credentials or a missing workflow
token in a non-test environment return a service-configuration error rather than opening an
endpoint. PostgreSQL is private to the Compose network and the backend binds to loopback by
default; remote browser access should use the NAS HTTPS reverse proxy or a trusted VPN. The
full setup and scheduler commands are in the [backend runbook](backend/README.md).

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
