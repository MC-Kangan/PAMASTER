# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Personal-account investing workflow backend — analysis-only (no trade execution). PostgreSQL is the source of truth; Notion is a UI adapter. The backend refreshes prices, computes metrics/signals, syncs to Notion, and serves browser analytics.

## Commands

All commands run from `backend/`.

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

# Run locally
uvicorn pa_investing.main:app --reload          # API at :8000
alembic upgrade head                             # migrate before first run

# Demo data
python -m pa_investing.scripts.seed_demo_portfolio
python -m pa_investing.scripts.import_ibkr_positions

# Scheduled snapshot (calls the workflow API internally)
python -m pa_investing.scripts.run_scheduled_snapshot

# Test & lint
pytest                          # all tests (uses sqlite :memory:)
pytest tests/path/test_file.py  # single file
ruff check .

# Docker
docker compose run --rm backend-api alembic upgrade head
docker compose up --build
docker compose config           # validate compose
```

## Architecture

### Config & DI

[`core/config.py`](backend/src/pa_investing/core/config.py) — `Settings(BaseSettings)` reads `PA_*` env vars (via `pydantic-settings`). Defaults to sqlite `:memory:` and `PA_ENVIRONMENT=test`, so tests get safe no-config defaults.

[`core/dependencies.py`](backend/src/pa_investing/core/dependencies.py) — FastAPI `Depends` wiring. Returns singletons (`get_settings`, `get_database_session_factory`) and request-scoped resources (workflow, repos — each gets a fresh DB session that commits or rolls back). Provider selection (Alpha Vantage vs manual, live Notion vs fake) is resolved here based on settings.

### Domain Layer

[`domain/`](backend/src/pa_investing/domain/) — Core business models and enums. The canonical types that everything else reads from and writes to. ORM models in `db/` map to/from these.

### Data Layer

[`db/`](backend/src/pa_investing/db/) — SQLAlchemy ORM models, `DatabaseSessionFactory`, and repository classes (one per aggregate: positions, prices, snapshots, signals, audit events). Repositories receive a session at construction — session lifecycle is managed by the DI layer.

Alembic migrations in `alembic/`. The env.py reads `Settings().database_url`, so `alembic upgrade head` picks up whatever `PA_DATABASE_URL` is set to (or `.env`).

### Workflows (the orchestration core)

[`workflows/refresh_and_sync.py`](backend/src/pa_investing/workflows/refresh_and_sync.py) — Central orchestration: load positions → refresh prices → update marks → build snapshot → generate signals → persist everything → sync to Notion. DB commit happens before any Notion write.

Other workflows: `daily_review.py` (review generation), `broker_import.py` (shared import logic for IBKR connectors), `snapshot_schedule.py` (fixed 4× daily cadence definition).

### API Surface

- `GET /health`
- `GET /analysis/portfolio` — browser HTML page (auth-gated)
- `GET /analysis/signal/{signal_id}` — browser HTML page (auth-gated)
- `GET /analysis/performance` — JSON performance history from snapshots (auth-gated)
- `POST /workflows/refresh-and-sync` — trigger the refresh pipeline (Bearer token-gated via `PA_WORKFLOW_API_TOKEN`)

### Broker Import

Two IBKR connectors behind a shared import workflow:
- **Flex Web Service** (`ibkr_flex.py`) — production path for NAS. Token + query ID, no IBKR password stored.
- **Client Portal Gateway** (`ibkr_client_portal.py`) — local manual testing only. Requires interactive browser login.

The CLI auto-selects Flex when `PA_IBKR_FLEX_TOKEN` and `PA_IBKR_FLEX_QUERY_ID` are set.

### Key Boundaries

- Notion is a UI adapter, not the source of truth
- Deterministic backend rules own numeric recommendations (signal prices, sizing)
- Secrets stay in backend config, never in Notion or committed code
- The system is analysis-only — no trade execution
- FX conversion and mixed-currency logic are not yet implemented; current multi-currency data is demo-only
