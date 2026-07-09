# PA Investing Backend

This backend powers the first MVP loop for the PA investing workflow:

- PostgreSQL remains the source of truth.
- Notion is the first lightweight frontend.
- the backend refreshes prices, computes metrics and signals, and syncs user-facing pages.

The system is analysis-only. It does not place trades.

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
```

For safe local development without live Notion writes, keep:

```bash
PA_NOTION_ENABLED=false
```

When Notion sync is disabled, the API route still runs but writes only to the fake Notion client in memory.

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

## Refresh-And-Sync Workflow Trigger

The first MVP trigger surface is:

```text
POST /workflows/refresh-and-sync
```

Example:

```bash
curl -X POST http://localhost:8000/workflows/refresh-and-sync \
  -H "Content-Type: application/json" \
  -d '{"stop_prices": {"AAPL": "180"}}'
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

## Docker

Run the database migration once before starting the API container for a fresh Postgres volume:

```bash
docker compose run --rm backend-api alembic upgrade head
```

Then start the stack:

```bash
docker compose up --build
```

## Verification

```bash
pytest
ruff check .
docker compose config
```
