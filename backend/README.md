# PA Investing Backend

Phase 1 backend for the PA investing workflow. The system uses Notion as the first UI adapter,
PostgreSQL as the source of truth, and Python modules for analytics, signal generation, sizing,
and agent workflows.

## Local Commands

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```

## Docker

Run the database migration once before starting the API container for a fresh Postgres volume:

```bash
docker compose run --rm backend-api alembic upgrade head
```

Then start the stack:

```bash
docker compose up --build
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## Phase 1 Verification

```bash
pytest
ruff check .
```
