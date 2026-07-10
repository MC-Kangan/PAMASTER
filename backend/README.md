# PA Investing Backend

This backend powers the first MVP loop for the PA investing workflow:

- PostgreSQL remains the source of truth.
- Notion is the first lightweight frontend.
- the backend refreshes prices, computes metrics and signals, and syncs user-facing pages.
- the backend also now exposes a first performance-history analytics slice for browser drilldown.

The system is analysis-only. It does not place trades.

## Current Data Limitation

The present MVP calculations assume position prices are already expressed in one common
portfolio currency. The demo portfolio intentionally contains USD, EUR, and GBP instruments,
but FX conversion and exchange-specific provider symbols are not implemented yet. Treat its
NAV, return, drawdown, and sizing outputs as workflow demonstrations until the instrument and
FX layer is complete. The first live Notion verification should therefore use seeded/manual
prices rather than treating mixed-currency Alpha Vantage output as portfolio truth.

## Implemented So Far

The backend currently includes:

- domain models for accounts, instruments, positions, prices, snapshots, and signals
- SQLAlchemy repositories and Alembic migrations
- demo portfolio seeding
- live market data through Alpha Vantage
- live Notion sync for `Signals` and `Daily Review`
- refresh-and-sync workflow
- performance-history analytics from persisted snapshots
- browser auth gate for analytics pages
- responsive browser performance page shell
- fixed snapshot cadence definition at `00:00`, `06:00`, `12:00`, `18:00`
- one-shot scheduled snapshot command for NAS or host schedulers

## Backend Structure

Main package layout under [src/pa_investing](src/pa_investing/):

- `analytics/`: calculations and snapshot/performance logic
- `analytics_app/`: browser-facing HTML page builders
- `api/`: FastAPI routes, schemas, and auth helper
- `brokers/`: CSV import path
- `core/`: config and dependency wiring
- `db/`: ORM models, repositories, session factory
- `domain/`: core business models and enums
- `market_data/`: provider interface and implementations
- `notion/`: Notion client and sync layer
- `scripts/`: CLI entrypoints
- `seeds/`: reusable seeding helpers
- `signals/`: signal rules and evaluation
- `sizing/`: deterministic sizing logic
- `workflows/`: daily review, refresh-and-sync, and snapshot schedule

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Required Environment Values

For the live Phase 2 MVP flow, configure these in `.env`:

```bash
PA_DATABASE_URL=postgresql+psycopg://pa_investing:pa_investing@localhost:5432/pa_investing
PA_NOTION_ENABLED=true
PA_NOTION_API_KEY=secret_xxx
PA_NOTION_SIGNALS_DATABASE_ID=xxxxxxxxxxxxxxxx
PA_NOTION_DAILY_REVIEW_DATABASE_ID=yyyyyyyyyyyyyyyy
PA_MARKET_DATA_PROVIDER=alpha_vantage
PA_ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key
PA_ANALYTICS_AUTH_ENABLED=true
PA_ANALYTICS_AUTH_USERNAME=your_username
PA_ANALYTICS_AUTH_PASSWORD=your_password
PA_WORKFLOW_API_TOKEN=generate_a_long_random_token
PA_BIND_ADDRESS=127.0.0.1
```

For safe local development without live Notion writes, keep:

```bash
PA_NOTION_ENABLED=false
```

When Notion sync is disabled, the API route still runs but writes only to the fake Notion client in memory.

Outside the test environment, `PA_WORKFLOW_API_TOKEN` is required for the write-trigger
endpoint. A missing token returns `503` and leaves the trigger closed. Compose enables
analytics auth by default; enabled analytics auth with a blank username or password also
returns `503` until credentials are configured.

## Database And API Runbook

Run migrations before starting the app against a fresh database:

```bash
alembic upgrade head
```

Start the API locally:

```bash
uvicorn pa_investing.main:app --reload
```

Health check:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Demo Portfolio Seed

To load the first MVP demo portfolio into PostgreSQL:

```bash
python -m pa_investing.scripts.seed_demo_portfolio
```

The seeded account is `pa-demo` and the starter symbols are:

- `SPGI`
- `ASML`
- `SAP`
- `SGLN`
- `SMH`

The CSV-backed seed fixture includes placeholder `latest_price` values so the portfolio is complete immediately after loading. Those are only starting marks. The refresh workflow is expected to replace them with provider prices where supported.

## Refresh-And-Sync Workflow Trigger

The first MVP trigger surface is:

```text
POST /workflows/refresh-and-sync
```

Example:

```bash
export PA_WORKFLOW_API_TOKEN=generate_a_long_random_token
curl -X POST http://localhost:8000/workflows/refresh-and-sync \
  -H "Authorization: Bearer ${PA_WORKFLOW_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"stop_prices": {"SPGI": "470", "ASML": "900", "SAP": "240", "SGLN": "22", "SMH": "250"}}'
```

Example response:

```json
{
  "snapshot_id": "snap-123",
  "nav": "1750",
  "signal_count": 1,
  "notion_sync_enabled": true
}
```

For the first visible MVP loop, the intended sequence is:

```bash
alembic upgrade head
python -m pa_investing.scripts.seed_demo_portfolio
uvicorn pa_investing.main:app --reload
export PA_WORKFLOW_API_TOKEN=generate_a_long_random_token
curl -X POST http://localhost:8000/workflows/refresh-and-sync \
  -H "Authorization: Bearer ${PA_WORKFLOW_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"stop_prices": {"SPGI": "470", "ASML": "900", "SAP": "240", "SGLN": "22", "SMH": "250"}}'
```

After the workflow runs, inspect Notion `Signals` and `Daily Review`.

Successful refresh requests commit the updated prices, positions, snapshot, signals, and
audit records before any Notion write begins. Performance history therefore survives across
requests and application restarts when PostgreSQL is configured. If the database commit
fails, no Signal or Daily Review write is attempted in Notion.

## Performance History And Browser Access

The chart-ready history endpoint is:

```text
GET /analysis/performance
```

With analytics auth enabled, inspect it locally with:

```bash
curl -u your_username:your_password http://localhost:8000/analysis/performance
```

Open the browser analytics page at:

```text
http://localhost:8000/analysis/portfolio
```

The browser surface is intended for both computer and smartphone browsers. The current
version is a responsive page shell; richer visual chart rendering is the next UI task.

## Scheduled Snapshots

The application defines four local deployment times:

- `00:00`
- `06:00`
- `12:00`
- `18:00`

The application does not run a second scheduler process. Configure the uGREEN NAS task
scheduler, cron, or another host scheduler to invoke this one-shot command at each time:

```bash
docker compose exec -T backend-api python -m pa_investing.scripts.run_scheduled_snapshot
```

Run that command from the directory containing `backend/docker-compose.yml`. It calls the
existing refresh-and-sync API over container loopback and uses an empty stop-price map. This
creates a regular portfolio snapshot without duplicating the workflow logic. Compose forwards
`PA_WORKFLOW_API_TOKEN` from `.env`, and the command reads it from the container environment.

For a backend running at another address, use:

```bash
export PA_WORKFLOW_API_TOKEN=generate_a_long_random_token
python -m pa_investing.scripts.run_scheduled_snapshot \
  --base-url http://localhost:8000
```

The command has no token command-line option, so the secret does not appear in process
listings. It exits non-zero when the token is absent or an HTTP request fails, and prints the
snapshot ID after success, making its output suitable for NAS scheduler logs.

## Docker

Run the database migration once before starting the API container for a fresh Postgres volume:

```bash
docker compose run --rm backend-api alembic upgrade head
```

Then start the stack:

```bash
docker compose up --build
```

Compose reads the live values above from `backend/.env` while retaining the
container-internal PostgreSQL URL. Analytics auth defaults to enabled for Compose, and the
workflow trigger remains unavailable until `PA_WORKFLOW_API_TOKEN` is set.

PostgreSQL is private to the Compose network. The backend binds to `127.0.0.1:8000` by
default so browser and workflow credentials are not sent over an unprotected LAN connection.
For computer and smartphone access, place the backend behind the NAS HTTPS reverse proxy or
a trusted VPN. Set `PA_BIND_ADDRESS` explicitly only when the deployment network boundary is
understood.

## Verification

```bash
pytest
ruff check .
docker compose config
```
