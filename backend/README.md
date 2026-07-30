# PA Investing Backend

This backend powers the first MVP loop for the PA investing workflow:

- PostgreSQL remains the source of truth.
- Notion is the first lightweight frontend.
- the backend refreshes prices, computes metrics and signals, and syncs user-facing pages.
- the backend also now exposes a first performance-history analytics slice for browser drilldown.

The system is analysis-only. It does not place trades.

## Current Data Limitation

The backend now converts mapped USD, EUR, and GBP positions into the configured USD or GBP
reporting currency. Missing FX excludes a position from aggregate reporting totals and lowers
the visible coverage ratio; stale persisted FX remains usable but is marked stale. Cash balances
are not implemented, and performance is not adjusted for cash flows, trades, dividends, fees, or
taxes, so the current portfolio total is invested value rather than complete broker NAV.

## Implemented So Far

The backend currently includes:

- domain models for accounts, instruments, positions, prices, snapshots, and signals
- SQLAlchemy repositories and Alembic migrations
- demo portfolio seeding
- IBKR Flex Web Service position import for NAS-friendly scheduled reads
- persistent broker/manual cost-basis separation with explicit reliability status
- optional IBKR Client Portal Gateway connector for local/manual testing
- live market data through Alpha Vantage
- mapped quotes and FX through Twelve Data
- persisted quote/FX observations, EOD fallback, and reporting coverage
- live Notion sync for `Signals` and `Daily Review`
- refresh-and-sync workflow
- performance-history analytics from persisted snapshots
- browser auth gate for analytics pages
- responsive browser performance page shell
- fixed snapshot cadence definition at `00:00`, `06:00`, `12:00`, `18:00`
- one-shot scheduled snapshot command for NAS or host schedulers
- persisted daily historical data with Yahoo-to-Twelve-Data whole-series fallback
- reusable portfolio and standalone research instrument resolution

## Backend Structure

Main package layout under [src/pa_investing](src/pa_investing/):

- `analytics/`: calculations and snapshot/performance logic
- `analytics_app/`: browser-facing HTML page builders
- `api/`: FastAPI routes, schemas, and auth helper
- `brokers/`: CSV import path and broker connectors
- `core/`: config and dependency wiring
- `db/`: ORM models, repositories, session factory
- `domain/`: core business models and enums
- `instruments/`: portfolio mappings and research candidate resolution
- `market_data/`: quote providers plus persisted daily-history routing
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
PA_NOTION_SETTINGS_DATABASE_ID=settings_database_id
PA_NOTION_ACCOUNTS_DATABASE_ID=accounts_database_id
PA_NOTION_POSITIONS_DATABASE_ID=positions_database_id
PA_NOTION_SIGNALS_DATABASE_ID=xxxxxxxxxxxxxxxx
PA_NOTION_DAILY_REVIEW_DATABASE_ID=yyyyyyyyyyyyyyyy
PA_MARKET_DATA_PROVIDER=twelve_data
PA_TWELVE_DATA_API_KEY=your_twelve_data_key
PA_DEFAULT_BASE_CURRENCY=USD
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

The portfolio databases are optional as a group. If any of `Settings`, `Accounts`, or
`Positions` is not configured, portfolio input/output sync is skipped and the existing
`Signals` and `Daily Review` flow continues.

For the portfolio sync, create these properties. Only the title and `External ID` are required by
the adapter; the other output columns are written when they exist:

- `Settings`: title, `External ID` (text), `Base Currency` (select: `USD` or `GBP`)
- `Accounts`: title, `External ID` (text), `Account ID` (text), `Source` (select),
  `Base Currency` (select), `Position Count` (number), `Currencies` (text),
  `Reporting Currency` (select), `Reporting Market Value` (number),
  `Reporting Coverage` (number)
- `Positions`: title, `External ID` (text), `Instrument ID` (text), `Symbol` (text),
  `Venue` (select), `Account` (text), `Asset Class` (select), `Quantity` (number),
  `Currency` (select), `Price` (number),
  `Market Value` (number), `Unrealized PnL` (number), `Cost Status` (select),
  `Effective Cost` (number), `Broker Cost` (number), `Cost Override` (number),
  `Price As Of` (text), `Price Source` (select), `Price Quality` (select),
  `Reporting Currency` (select), `Reporting Market Value` (number),
  `Reporting Unrealized PnL` (number), `FX Rate` (number), `FX As Of` (text),
  `FX Status` (select),
  `Theme` (select), `Notes` (text)

`Base Currency`, `Cost Override`, `Theme`, and `Notes` are user-owned. Backend upserts do not
write them. A present empty `Cost Override` clears a stored manual cost, while an explicit zero
is retained as a valid manual cost. If a Notion read fails, existing settings and overrides are
left unchanged. Other backend output columns are schema-flexible: compatible properties are
written when present and ignored when absent.

Outside the test environment, `PA_WORKFLOW_API_TOKEN` is required for the write-trigger
endpoint. A missing token returns `503` and leaves the trigger closed. Compose enables
analytics auth by default; enabled analytics auth with a blank username or password also
returns `503` until credentials are configured.

## Database And API Runbook

Run migrations before starting the app against a fresh database:

```bash
alembic upgrade head
```

Migration `0006_instrument_identity` converts legacy symbol primary keys into deterministic
internal instrument IDs while preserving positions, manual and broker costs, and price history.
New instruments can carry optional provider identifiers without requiring them, keeping the same
model usable for equities, ETFs, and future Coinbase crypto products.

Migration `0007_quotes_fx_reporting` adds provider mappings, quote metadata, FX observations,
and reporting-coverage fields.

Migration `0009_historical_market_data` adds immutable historical series, dataset versions, and
daily bars. A series points to its active validated dataset; promotion from research to a
permanent instrument links the existing data instead of copying or refetching it.

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

## IBKR Position Import

The preferred IBKR path for NAS deployment is Flex Web Service. In IBKR Client Portal,
enable Flex Web Service, create an Activity Flex Query that includes open positions and
account information, then copy the token and query id into `.env`:

```bash
PA_IBKR_FLEX_TOKEN=your_flex_token
PA_IBKR_FLEX_QUERY_ID=your_query_id
```

Then run:

```bash
python -m pa_investing.scripts.import_ibkr_positions
```

The command auto-selects Flex when `PA_IBKR_FLEX_TOKEN` and `PA_IBKR_FLEX_QUERY_ID` are
present. It upserts IBKR accounts and supported positions into PostgreSQL, and closes
previous IBKR positions that are missing from the latest import by setting quantity to zero.

The older Client Portal Gateway connector is still available for local/manual testing:

```bash
python -m pa_investing.scripts.import_ibkr_positions --source gateway --gateway-url https://localhost:5001/v1/api
```

Gateway is not the recommended NAS path because it relies on an interactive browser login
and a short-lived session. The import command does not place trades.

The importer stores broker-derived cost independently from a nullable manual override. An explicit
manual value of zero is valid and is distinguishable from a missing cost. Re-importing IBKR data
updates the broker value without clearing the override. Clearing the override restores the latest
broker or reconstructed cost. This behavior is available through the Notion `Cost Override` field
as well as the domain and repository layers.

## Market-Data Mappings And Reporting Currency

Run the position inspection command to obtain stable internal instrument IDs:

```bash
python -m pa_investing.scripts.show_positions
```

Create a CSV with one row per provider mapping:

```csv
instrument_id,provider,provider_symbol,provider_exchange,expected_currency,price_multiplier,enabled
your-spgi-id,twelve_data,SPGI,NYSE,USD,1,true
your-sgln-id,twelve_data,SGLN,LSE,GBX,0.01,true
```

`expected_currency` is the currency returned by the provider. `price_multiplier` converts that
raw quote into the instrument's normalized trading currency; for example, `0.01` converts GBX
to GBP. Exchange names must match the provider's accepted values.

Import or update the mappings idempotently:

```bash
python -m pa_investing.scripts.import_market_data_mappings mappings.csv
```

Then configure `PA_MARKET_DATA_PROVIDER=twelve_data` and `PA_TWELVE_DATA_API_KEY`. The refresh
workflow requests only mapped listings. It rejects currency or exchange mismatches, selects the
newest valid persisted quote, and falls back to the timestamped broker mark when needed. A quote
more than 50% away from the current broker/persisted mark is also quarantined as an unexplained
jump instead of silently replacing the portfolio value.

The reporting currency comes from the Notion `Portfolio` Settings row when available, otherwise
`PA_DEFAULT_BASE_CURRENCY`. Change the `Base Currency` select on that row to `USD` or `GBP`; the
selection takes effect on the next refresh. Missing FX leaves the position visible but excludes it
from aggregate reporting totals. `Reporting Coverage` and `FX Status` make that incompleteness
explicit.

IBKR Flex `CashReportCurrency` rows are imported as provider-neutral cash positions such as
`CASH.GBP`. This keeps the domain model compatible with future brokers while allowing cash to be
included in account totals, portfolio weights, and the allocation chart.

## Daily Historical Data

Install the normal project dependencies and configure `PA_TWELVE_DATA_API_KEY` to enable the
fallback provider. Yahoo is the primary provider and Twelve Data is the mapped fallback.

Portfolio history requires explicit rows in `market_data_mappings`. Yahoo mappings usually carry
the Yahoo ticker suffix, while Twelve Data mappings may include an exchange, provider currency,
and unit multiplier:

```csv
instrument_id,provider,provider_symbol,provider_exchange,expected_currency,price_multiplier,enabled
your-sgln-id,yahoo,SGLN.L,,GBP,1,true
your-sgln-id,twelve_data,SGLN,LSE,GBX,0.01,true
```

The router evaluates each provider for the complete requested window. A timeout, malformed
payload, listing mismatch, invalid OHLC relationship, wrong adjustment mode, or incomplete
boundary coverage rejects that provider and records the reason before trying the next one.
Accepted datasets never combine bars from multiple providers.

The default analysis bars are adjusted for splits and dividends. Yahoo raw OHLC and Twelve Data
`adjust=none` bars are retained as companion series. Adjustment mode, provider, symbol, exchange,
currency, fetch time, warnings, and every failed attempt remain visible to consumers.

Use an internal instrument ID for portfolio data:

```bash
python -m pa_investing.scripts.fetch_historical_data \
  --instrument-id your-instrument-id \
  --start 2025-01-01 \
  --end 2025-12-31
```

Use research mode for discovery:

```bash
python -m pa_investing.scripts.fetch_historical_data \
  --research "NVDA" \
  --start 2025-01-01 \
  --end 2025-12-31
```

Ambiguous research queries print candidate listings and exit with code `2`; all-provider failure
exits with code `1`. A successful request prints dataset ID, provider, coverage, adjustment modes,
warnings, and stale status. Add `--allow-stale` only for workflows such as daily review that may
explicitly reuse the last validated dataset.

The HTTP equivalents are:

- `GET /analysis/instruments/search?q=NVDA`
- `GET /analysis/market-data/{instrument_id}?start=2025-01-01&end=2025-12-31`
- `POST /analysis/market-data/research`

Application routes, agents, and skills must call `HistoricalDataService`. They must not call
Yahoo, Twelve Data, SQLAlchemy repositories, or fallback logic directly. This keeps analysis
reproducible and ensures validation and provenance cannot be bypassed.

The implementation was written independently. Vibe-Trading was used as a design reference for
small provider contracts and boundary validation; no substantial upstream source code was copied.

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

After the workflow runs, inspect the top-level Notion `PA Investing` dashboard. It contains compact
linked views for latest reviews, holdings, accounts, open signals, the review calendar, and the
portfolio settings row. The source databases live under `PA Investing Data` to avoid duplicate
tables on the operating page.

The daily-review page also includes deterministic finance evidence for each mapped equity and ETF
holding. This section records provider provenance, the last completed bar, notable findings, and
isolated data failures; it does not create PA signals. Notion values are rounded only for display:
money to two decimals, prices and quantities to four, percentage ratios to four (two percentage
points when displayed as a percent), and FX rates to six. Stored calculations retain full precision.

Successful refresh requests commit the updated prices, positions, snapshot, signals, and
audit records before any Notion write begins. Performance history therefore survives across
requests and application restarts when PostgreSQL is configured. If the database commit
fails, no Signal or Daily Review write is attempted in Notion.

## Performance History And Browser Access

The chart-ready history endpoint is:

```text
GET /analysis/performance
```

The current holdings and allocation endpoint is:

```text
GET /analysis/current
```

The indicative daily P&L history and browser refresh endpoints are:

```text
GET /analysis/daily-pnl?days=90
POST /analysis/refresh
```

Daily P&L is indicative because it compares the latest available NAV snapshot for each calendar
day and does not adjust for cash flows, trades, dividends, fees, or taxes. The reporting coverage
value shows how much of the portfolio had reporting-currency values in each snapshot.
Browser-initiated refresh runs the same refresh-and-sync workflow as the scheduled workflow, so
enabled Notion synchronization continues to run before the page reloads its current holdings,
performance history, and daily P&L data.

The provider-neutral transaction ledger and operational status endpoints are:

```text
GET /analysis/transactions
GET /analysis/operations
```

Both are protected by the same analytics authentication as the browser application.
`/analysis/transactions` currently contains idempotently imported IBKR Flex trade executions.
`/analysis/operations` contains the latest run for each provider/operation and the latest broker
NAV/cash reconciliation for each account.

With analytics auth enabled, inspect it locally with:

```bash
curl -u your_username:your_password http://localhost:8000/analysis/performance
```

Open the browser analytics page at:

```text
http://localhost:8000/analysis/portfolio
http://localhost:8000/analysis/position-chart
```

The browser surface is intended for both computer and smartphone browsers. It renders headline
NAV and indicative daily P&L cards, a daily P&L calendar, a current position-allocation donut, a
historical NAV line chart, and the daily performance table. Headline returns use the latest
snapshot from each calendar day so the four intraday scheduled snapshots do not create artificial
daily-return observations.

The Position Chart tab renders one open position at a time with Yahoo candles, authoritative IBKR
execution markers, broker average cost, optional SMA20 and volume, and a trade-price
reconciliation banner. Configure `PA_IBKR_FLEX_TIMEZONE` to match the timezone selected in the
Flex query (for example, `Europe/London`) so executions align with candles. The default
`PA_MARKET_DATA_RECONCILIATION_TOLERANCE=0.01` permits a one-percent near-match before showing a
warning. Provider price multipliers remain the explicit control for GBP/GBp and similar unit
normalization.

The Notion free plan permits only one native chart for the workspace and the available chart slot
is already consumed. Notion remains the compact operating dashboard; richer and interactive charts
belong on this browser surface and can be linked from Notion.

## Secure Browser Deployment

All `/analysis/*` routes use the HTTP Basic application-authentication dependency. Analytics
authentication must be enabled whenever the browser refresh endpoint is exposed. With
authentication enabled:

- missing or incorrect credentials return `401`;
- blank configured credentials return `503`, leaving the application closed;
- credential comparison uses constant-time comparison;
- browser-facing `POST /analysis/refresh` also requires `Content-Type: application/json` and the
  exact non-simple request header `X-PA-Request: refresh`;
- workflow-facing `POST /workflows/refresh-and-sync` remains independently protected by the
  `PA_WORKFLOW_API_TOKEN` Bearer token and is unchanged.

The custom request header and the application's absence of CORS permission form the CSRF boundary
for `/analysis/refresh`: a cross-site form cannot supply the marker, and a cross-origin script
cannot send it without a successful preflight. Do not add permissive CORS handling for this route.
This design deliberately does not compare `Origin`, `Host`, or absolute URLs, so it remains valid
behind a correctly configured reverse proxy.

The current application login uses HTTP Basic authentication. Basic authentication is suitable for
this single-user MVP only when it is transported over HTTPS and the application is not directly
exposed to the public internet.

The recommended NAS deployment is:

1. Keep the Docker port bound to NAS loopback with `PA_BIND_ADDRESS=127.0.0.1`.
2. Install Tailscale on the NAS, phone, and authorized computers.
3. Publish the loopback service through Tailscale Serve or an HTTPS NAS reverse proxy.
4. Restrict the service to the user's tailnet identity/devices with Tailscale grants or ACLs.
5. Keep application authentication enabled as a second layer.
6. Do not enable Tailscale Funnel or router port forwarding for this application.

Configure separate, randomly generated browser and workflow credentials:

```bash
PA_ANALYTICS_AUTH_ENABLED=true
PA_ANALYTICS_AUTH_USERNAME=your_private_username
PA_ANALYTICS_AUTH_PASSWORD=generate_a_long_random_password
PA_WORKFLOW_API_TOKEN=generate_a_different_long_random_token
PA_BIND_ADDRESS=127.0.0.1
```

Do not reuse the Notion, IBKR, market-data, NAS administrator, or Tailscale credentials. Store the
values only in the NAS secret/environment configuration and the local ignored `.env`, never in
Notion or Git.

The browser app should remain unavailable when Tailscale is disconnected. This provides:

- device and identity authorization at the private-network layer;
- encrypted transport through HTTPS;
- an additional application credential;
- no public listener for the application container.

Before any future public-internet deployment, replace Basic authentication with an
identity-aware proxy or OIDC provider supporting MFA and login throttling. Suitable self-hosted
options include Authentik or Authelia; a managed alternative is Cloudflare Access. The application
should consume trusted identity headers or OIDC claims from that layer instead of implementing a
new password database.

The local development command may explicitly set `PA_ANALYTICS_AUTH_ENABLED=false`, but that
override must never be used in the NAS deployment.

References:

- [Tailscale access controls](https://tailscale.com/docs/features/access-control)
- [Tailscale Serve](https://tailscale.com/kb/1242/tailscale-serve)
- [MDN HTTP authentication](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Authentication)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)

## UGREEN DXP4800 Plus Deployment

Deploy this application with UGOS Pro Docker Compose, not a virtual machine. The workload has two
Linux services, no kernel-specific dependency, and no requirement for a guest desktop or separate
operating system. Docker preserves NAS memory, uses the existing image definitions, and keeps
PostgreSQL storage and application restarts explicit.

The canonical NAS project location is:

```text
/volume1/docker/pa-investing
```

Keep the API bound to `127.0.0.1:8000` during the Notion-first MVP. Do not configure router port
forwarding, a public reverse proxy, or Tailscale Funnel. Private browser/PWA access is a separate
deployment slice. PostgreSQL must remain private to the Compose network: never publish host port
`5432`.

### Initial Installation

Create and protect `backend/.env` with the first three commands below. This ignored file is the
only location for production secrets: never commit a secret or place one in another file, a
command, a scheduler definition, Notion, or Git. Before running `docker compose config --quiet`,
set these values in `backend/.env`:

```text
PA_POSTGRES_PASSWORD
PA_NOTION_ENABLED=true
PA_NOTION_API_KEY
PA_NOTION_SETTINGS_DATABASE_ID
PA_NOTION_ACCOUNTS_DATABASE_ID
PA_NOTION_POSITIONS_DATABASE_ID
PA_NOTION_SIGNALS_DATABASE_ID
PA_NOTION_DAILY_REVIEW_DATABASE_ID
PA_MARKET_DATA_PROVIDER=twelve_data
PA_TWELVE_DATA_API_KEY
PA_IBKR_FLEX_TOKEN
PA_IBKR_FLEX_QUERY_ID
PA_IBKR_FLEX_HISTORY_QUERY_ID
PA_IBKR_FLEX_TIMEZONE=Europe/London
PA_MARKET_DATA_RECONCILIATION_TOLERANCE=0.01
PA_ANALYTICS_AUTH_ENABLED=true
PA_ANALYTICS_AUTH_USERNAME
PA_ANALYTICS_AUTH_PASSWORD
PA_WORKFLOW_API_TOKEN
PA_DEFAULT_BASE_CURRENCY
PA_BIND_ADDRESS=127.0.0.1
```

Use distinct URL-safe secrets for `PA_POSTGRES_PASSWORD`, analytics authentication, and
`PA_WORKFLOW_API_TOKEN`; do not reuse those credentials with Notion, IBKR, or Twelve Data.

```bash
cd /volume1/docker/pa-investing/backend
cp .env.example .env
chmod 600 .env
docker compose config --quiet
docker compose build --pull
docker compose run --rm backend-api alembic upgrade head
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1:8000/health
```

### Manual End-to-End Smoke Test

After the API health check succeeds, run the full production path manually:

```bash
cd /volume1/docker/pa-investing/backend

docker compose exec -T backend-api \
  python -m pa_investing.scripts.import_ibkr_positions --source flex

docker compose exec -T backend-api \
  python -m pa_investing.scripts.import_ibkr_history

docker compose exec -T backend-api \
  python -m pa_investing.scripts.run_scheduled_snapshot

docker compose exec -T backend-api \
  python -m pa_investing.scripts.show_positions
```

Expected evidence:

- The IBKR command reports imported accounts, positions, transactions, and reconciliation status.
- The IBKR history command reports broker daily NAV and P&L points.
- The snapshot command prints a new snapshot ID.
- `show_positions` displays the real internal instrument IDs.
- Notion shows a Daily Review for the current Europe/London date.
- Position `Price As Of`, `FX As Of`, reporting value, and portfolio weight are populated.

### UGOS Task Schedule

Before configuring these tasks, verify in UGOS that the system timezone is set to
`Europe/London`. This keeps the local cadence aligned with UK daylight-saving time instead of
shifting the jobs by an hour when the clocks change.

Configure each UGOS scheduled task to run as the NAS account that can execute Docker Compose.
Retain scheduler output in the UGOS task logs. Do not add a scheduler service to Compose or run a
separate scheduler container; UGOS Task Scheduler invokes these one-shot commands directly.

**06:00 Europe/London — full morning cycle:**

```bash
cd /volume1/docker/pa-investing/backend && docker compose exec -T backend-api python -m pa_investing.scripts.import_ibkr_positions --source flex && docker compose exec -T backend-api python -m pa_investing.scripts.import_ibkr_history && docker compose exec -T backend-api python -m pa_investing.scripts.run_scheduled_snapshot
```

The morning command intentionally uses `&&`: a failed IBKR import prevents the refresh from being
reported as a successful full cycle.

**12:00, 18:00, and 00:00 Europe/London — snapshot refresh:**

```bash
cd /volume1/docker/pa-investing/backend && docker compose exec -T backend-api python -m pa_investing.scripts.run_scheduled_snapshot
```

**02:30 Europe/London — database backup:**

```bash
/volume1/docker/pa-investing/backend/scripts/backup_postgres.sh
```

The backup script writes a private temporary file in `backups/`, validates it with
`pg_restore --list`, and atomically publishes the validated archive as a private `.dump` file.
Publication never replaces an existing same-second dump. Only after publication succeeds does the
script prune published dump files older than 30 days; failed dumps and failed validations are
cleaned up without running retention.

The snapshot command calls the authenticated refresh-and-sync workflow over container loopback.
It exits non-zero when the workflow token is absent or the request fails, and prints the snapshot
ID after success, so its output is suitable for the retained task logs.

### Backup Validation and Restore Drill

Run this drill after the initial real refresh and periodically thereafter:

```bash
cd /volume1/docker/pa-investing/backend
scripts/backup_postgres.sh
latest=$(ls -1t backups/pa_investing-*.dump | head -1)
docker compose exec -T postgres createdb -U pa_investing pa_investing_restore_test
docker compose exec -T postgres pg_restore -U pa_investing -d pa_investing_restore_test < "$latest"
docker compose exec -T postgres psql -U pa_investing -d pa_investing_restore_test -c 'SELECT count(*) FROM portfolio_snapshots;'
docker compose exec -T postgres dropdb -U pa_investing pa_investing_restore_test
```

The `latest` glob selects only atomically published, validated `.dump` files; in-progress temporary
files are hidden and are removed automatically on failure.

Expected: the restore completes, the snapshot count is non-zero after the first real refresh, and
the temporary database is removed.

### Update and Rollback

For each application update:

```bash
cd /volume1/docker/pa-investing/backend
scripts/backup_postgres.sh
git pull --ff-only
docker compose build --pull
docker compose run --rm backend-api alembic upgrade head
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1:8000/health
```

If the NAS does not have Git or should not build from source, build the backend image on a laptop
and load it on the NAS instead:

```bash
cd /Users/chenkangan/Documents/PAMASTER/backend
tag=$(git rev-parse --short HEAD)
docker build --platform linux/amd64 -t "pa-investing-backend:${tag}" .
docker save "pa-investing-backend:${tag}" -o "pa-investing-backend-${tag}.tar"
```

Transfer `pa-investing-backend-${tag}.tar` to the NAS. On the NAS:

```bash
docker load -i /path/to/pa-investing-backend-<tag>.tar
cd /volume1/docker/pa-investing/backend
export PA_BACKEND_IMAGE="pa-investing-backend:<tag>"
docker compose -f docker-compose.prebuilt.yml config --quiet
docker compose -f docker-compose.prebuilt.yml run --rm backend-api alembic upgrade head
docker compose -f docker-compose.prebuilt.yml up -d
docker compose -f docker-compose.prebuilt.yml ps
curl --fail http://127.0.0.1:8000/health
```

Application rollback means checking out the previously deployed commit and rebuilding the backend
image. Database rollback must use the pre-update dump; never run an Alembic downgrade against the
only production database without a tested restore.

## Docker

Run the database migration once before starting the API container for a fresh Postgres volume:

```bash
docker compose run --rm backend-api alembic upgrade head
```

Migration `0008_operational_foundation` adds the transaction ledger, broker reconciliation, and
provider-run tables. Run the same `alembic upgrade head` command for an existing volume before the
next broker import.

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
