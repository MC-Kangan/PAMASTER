# UGREEN NAS Docker MVP Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy PA Investing as a persistent, scheduled, private Docker Compose workload on the UGREEN NASync DXP4800 Plus, with reliable IBKR imports, Notion refreshes, health checks, and recoverable PostgreSQL backups.

**Architecture:** Run the existing FastAPI backend and PostgreSQL database as two Docker containers managed by UGOS Pro. Keep PostgreSQL on the private Compose network and bind the API to NAS loopback for this first slice; Notion remains the remote/mobile operating surface. Use the UGOS task scheduler to run one morning IBKR-import-plus-refresh cycle, three additional snapshot refreshes, and one database backup without introducing an application-level scheduler.

**Tech Stack:** UGOS Pro Docker/Compose, Python 3.12, FastAPI, PostgreSQL 16, SQLAlchemy/Alembic, IBKR Flex, Yahoo Finance, Twelve Data, Notion API.

## Global Constraints

- Choose Docker Compose, not a virtual machine.
- Deploy the repository at `/volume1/docker/pa-investing` on the NAS.
- Keep PostgreSQL private; never publish port `5432`.
- Bind the FastAPI port to `127.0.0.1:8000` for this slice.
- Do not configure router port forwarding, a public reverse proxy, or Tailscale Funnel.
- Keep Notion as the remote/mobile MVP surface until private browser access is implemented separately.
- Keep the system analysis-only; no broker order endpoint or credential expansion is allowed.
- Store all secrets in `backend/.env`, which remains ignored by Git and excluded from Docker build context.
- Run IBKR Flex import once each morning before the first refresh.
- Preserve the existing snapshot cadence at `00:00`, `06:00`, `12:00`, and `18:00` Europe/London.
- Fail the morning refresh when the IBKR import fails; never present stale positions as a successful full cycle.
- Retain 30 days of daily PostgreSQL dumps under `backend/backups/`.
- PostgreSQL remains the source of truth; Notion failures must not roll back committed portfolio data.
- Do not add Redis, Kubernetes, Portainer, Celery, or a general scheduler service.

## Deployment Decision

Use UGOS Pro Docker rather than a VM.

The DXP4800 Plus has an Intel 8505 x86 processor, 8 GB DDR5 RAM, and official Docker support through the UGOS Pro App Center. The application already ships with a Dockerfile and a two-service Compose topology, so Docker gives process isolation, restart policies, portable configuration, and simple volume backup without maintaining another guest operating system. A VM would reserve additional memory and storage, duplicate operating-system updates, and complicate access to NAS-managed backups without solving a current application requirement.

Official references:

- UGREEN DXP4800 Plus specifications and Docker support:
  `https://nas.ugreen.com/products/ugreen-nasync-dxp4800-plus-nas-storage`
- Tailscale Docker networking, reserved for a later private-browser slice:
  `https://tailscale.com/docs/features/containers/docker/how-to/connect-docker-container`

## File Structure

Files changed by this implementation:

- Modify `backend/docker-compose.yml`: production-safe environment forwarding, health checks, dependency readiness, restart behavior, and loopback publishing.
- Modify `backend/.env.example`: add the PostgreSQL production secret and retain every NAS-required provider setting.
- Create `backend/.dockerignore`: prevent secrets, databases, caches, and backups from entering the Docker build context.
- Modify `.gitignore`: ignore NAS backup artifacts.
- Create `backend/scripts/backup_postgres.sh`: produce, validate, and retain PostgreSQL dumps.
- Modify `backend/tests/unit/test_deployment_config.py`: enforce deployment security and recoverability invariants.
- Modify `backend/README.md`: add the DXP4800 Plus deployment, scheduler, backup, restore, and rollback runbook.
- Modify `README.md`: point the recommended next step to the completed NAS operating path after implementation.

---

### Task 1: Harden the Docker Compose Boundary

**Files:**

- Modify: `backend/tests/unit/test_deployment_config.py`
- Modify: `backend/docker-compose.yml`
- Modify: `backend/.env.example`
- Create: `backend/.dockerignore`

**Interfaces:**

- Consumes: existing `backend/Dockerfile`, `Settings` environment variables, and PostgreSQL named volume.
- Produces: a Compose stack that starts only after PostgreSQL is ready, restarts after NAS reboot, forwards IBKR Flex configuration, and reports container health.

- [ ] **Step 1: Add failing deployment-configuration tests**

Append these tests to `backend/tests/unit/test_deployment_config.py`:

```python
def test_compose_forwards_required_nas_provider_configuration() -> None:
    compose_text = (BACKEND_ROOT / "docker-compose.yml").read_text()

    assert 'PA_IBKR_FLEX_TOKEN: "${PA_IBKR_FLEX_TOKEN:-}"' in compose_text
    assert 'PA_IBKR_FLEX_QUERY_ID: "${PA_IBKR_FLEX_QUERY_ID:-}"' in compose_text
    assert 'PA_IBKR_FLEX_BASE_URL: "${PA_IBKR_FLEX_BASE_URL:-' in compose_text
    assert 'PA_TWELVE_DATA_API_KEY: "${PA_TWELVE_DATA_API_KEY:-}"' in compose_text
    assert 'PA_WORKFLOW_API_TOKEN: "${PA_WORKFLOW_API_TOKEN:-}"' in compose_text


def test_compose_has_health_checks_and_restart_policies() -> None:
    compose_text = (BACKEND_ROOT / "docker-compose.yml").read_text()

    assert compose_text.count("restart: unless-stopped") == 2
    assert compose_text.count("healthcheck:") == 2
    assert "condition: service_healthy" in compose_text
    assert "pg_isready" in compose_text
    assert 'http://127.0.0.1:8000/health' in compose_text


def test_docker_build_context_excludes_secrets_and_runtime_data() -> None:
    ignored_paths = {
        line.strip()
        for line in (BACKEND_ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert ".env" in ignored_paths
    assert "backups/" in ignored_paths
    assert "*.db" in ignored_paths
    assert "__pycache__/" in ignored_paths
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_deployment_config.py -v
```

Expected: the existing two tests pass and the three new tests fail because the Compose hardening and `.dockerignore` do not exist yet.

- [ ] **Step 3: Replace the Compose file with the hardened topology**

Set `backend/docker-compose.yml` to:

```yaml
services:
  postgres:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_USER: pa_investing
      POSTGRES_PASSWORD: "${PA_POSTGRES_PASSWORD:?PA_POSTGRES_PASSWORD is required}"
      POSTGRES_DB: pa_investing
    volumes:
      - pa_postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U pa_investing -d pa_investing"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 10s
    stop_grace_period: 30s

  backend-api:
    build: .
    restart: unless-stopped
    init: true
    environment:
      PA_ENVIRONMENT: "${PA_ENVIRONMENT:-local}"
      PA_DATABASE_URL: "postgresql+psycopg://pa_investing:${PA_POSTGRES_PASSWORD:?PA_POSTGRES_PASSWORD is required}@postgres:5432/pa_investing"
      PA_NOTION_ENABLED: "${PA_NOTION_ENABLED:-false}"
      PA_NOTION_API_KEY: "${PA_NOTION_API_KEY:-}"
      PA_NOTION_SETTINGS_DATABASE_ID: "${PA_NOTION_SETTINGS_DATABASE_ID:-}"
      PA_NOTION_ACCOUNTS_DATABASE_ID: "${PA_NOTION_ACCOUNTS_DATABASE_ID:-}"
      PA_NOTION_POSITIONS_DATABASE_ID: "${PA_NOTION_POSITIONS_DATABASE_ID:-}"
      PA_NOTION_SIGNALS_DATABASE_ID: "${PA_NOTION_SIGNALS_DATABASE_ID:-}"
      PA_NOTION_DAILY_REVIEW_DATABASE_ID: "${PA_NOTION_DAILY_REVIEW_DATABASE_ID:-}"
      PA_MARKET_DATA_PROVIDER: "${PA_MARKET_DATA_PROVIDER:-manual}"
      PA_ALPHA_VANTAGE_API_KEY: "${PA_ALPHA_VANTAGE_API_KEY:-}"
      PA_TWELVE_DATA_API_KEY: "${PA_TWELVE_DATA_API_KEY:-}"
      PA_IBKR_GATEWAY_BASE_URL: "${PA_IBKR_GATEWAY_BASE_URL:-https://127.0.0.1:5000/v1/api}"
      PA_IBKR_FLEX_BASE_URL: "${PA_IBKR_FLEX_BASE_URL:-https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService}"
      PA_IBKR_FLEX_TOKEN: "${PA_IBKR_FLEX_TOKEN:-}"
      PA_IBKR_FLEX_QUERY_ID: "${PA_IBKR_FLEX_QUERY_ID:-}"
      PA_ANALYTICS_AUTH_ENABLED: "${PA_ANALYTICS_AUTH_ENABLED:-true}"
      PA_ANALYTICS_AUTH_USERNAME: "${PA_ANALYTICS_AUTH_USERNAME:-}"
      PA_ANALYTICS_AUTH_PASSWORD: "${PA_ANALYTICS_AUTH_PASSWORD:-}"
      PA_WORKFLOW_API_TOKEN: "${PA_WORKFLOW_API_TOKEN:-}"
      PA_LLM_PROVIDER: "${PA_LLM_PROVIDER:-mock}"
      PA_OPENAI_API_KEY: "${PA_OPENAI_API_KEY:-}"
      PA_DEFAULT_BASE_CURRENCY: "${PA_DEFAULT_BASE_CURRENCY:-USD}"
    ports:
      - "${PA_BIND_ADDRESS:-127.0.0.1}:8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read()
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 20s
    stop_grace_period: 30s

volumes:
  pa_postgres_data:
```

Use a URL-safe alphanumeric value for `PA_POSTGRES_PASSWORD`; the password is interpolated into the SQLAlchemy URL.

- [ ] **Step 4: Add the required environment setting**

Add this immediately after `PA_DATABASE_URL` in `backend/.env.example`:

```dotenv
PA_POSTGRES_PASSWORD=replace_with_a_long_url_safe_alphanumeric_secret
```

Do not add a real password to the example.

- [ ] **Step 5: Exclude secrets and runtime artifacts from Docker builds**

Create `backend/.dockerignore`:

```text
.env
.venv/
.pytest_cache/
.ruff_cache/
__pycache__/
*.py[cod]
*.db
*.db-*
*.sqlite*
backups/
tests/
```

- [ ] **Step 6: Run focused tests and validate Compose**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_deployment_config.py -v
cp .env.example .env.compose-test
PA_POSTGRES_PASSWORD=composeconfigtest docker compose --env-file .env.compose-test config --quiet
rm .env.compose-test
```

Expected: all deployment tests pass and `docker compose config --quiet` exits with status `0`.

- [ ] **Step 7: Commit Task 1**

```bash
git add backend/docker-compose.yml backend/.env.example backend/.dockerignore backend/tests/unit/test_deployment_config.py
git commit -m "chore: harden NAS compose deployment"
```

---

### Task 2: Add a Validated PostgreSQL Backup Command

**Files:**

- Modify: `.gitignore`
- Create: `backend/scripts/backup_postgres.sh`
- Modify: `backend/tests/unit/test_deployment_config.py`

**Interfaces:**

- Consumes: running Compose `postgres` service and its configured credentials.
- Produces: timestamped custom-format dumps in `backend/backups/`, verified with `pg_restore --list`, with files older than 30 days removed only after a new dump validates.

- [ ] **Step 1: Add failing backup-boundary tests**

Append to `backend/tests/unit/test_deployment_config.py`:

```python
def test_postgres_backups_are_ignored_by_git() -> None:
    ignored_paths = {
        line.strip()
        for line in (REPOSITORY_ROOT / ".gitignore").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "backend/backups/" in ignored_paths


def test_backup_script_dumps_validates_then_applies_retention() -> None:
    script = (BACKEND_ROOT / "scripts" / "backup_postgres.sh").read_text()

    dump_index = script.index("pg_dump")
    validation_index = script.index("pg_restore --list")
    retention_index = script.index("-mtime +30 -delete")
    assert dump_index < validation_index < retention_index
    assert "set -eu" in script
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_deployment_config.py -v
```

Expected: the two new tests fail because the ignore rule and backup script do not exist.

- [ ] **Step 3: Ignore backup output**

Append to the repository `.gitignore`:

```text
backend/backups/
```

- [ ] **Step 4: Create the backup script**

Create `backend/scripts/backup_postgres.sh`:

```sh
#!/bin/sh
set -eu

backend_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$backend_dir"

mkdir -p backups
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
output="backups/pa_investing-${timestamp}.dump"

docker compose exec -T postgres \
  pg_dump -U pa_investing -d pa_investing -Fc > "$output"

docker compose exec -T postgres \
  pg_restore --list < "$output" > /dev/null

find backups -type f -name 'pa_investing-*.dump' -mtime +30 -delete

printf 'PostgreSQL backup completed: %s\n' "$output"
```

Make it executable:

```bash
chmod 750 backend/scripts/backup_postgres.sh
```

- [ ] **Step 5: Verify tests and shell syntax**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_deployment_config.py -v
sh -n scripts/backup_postgres.sh
```

Expected: all deployment tests pass and the shell syntax check exits `0`.

- [ ] **Step 6: Commit Task 2**

```bash
git add .gitignore backend/scripts/backup_postgres.sh backend/tests/unit/test_deployment_config.py
git commit -m "feat: add validated PostgreSQL backups"
```

---

### Task 3: Write the DXP4800 Plus Operating Runbook

**Files:**

- Modify: `backend/README.md`
- Modify: `README.md`

**Interfaces:**

- Consumes: the hardened Compose stack and backup script from Tasks 1–2.
- Produces: one exact deployment and operating path for the NAS administrator.

- [ ] **Step 1: Add the Docker-versus-VM decision to the backend runbook**

Add a `UGREEN DXP4800 Plus Deployment` section before `## Docker` in `backend/README.md`. State:

```markdown
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
forwarding. Private browser/PWA access is a separate deployment slice.
```

- [ ] **Step 2: Document initial NAS installation commands**

Add these commands to the same section:

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

Document that the administrator must set these `.env` values before `docker compose config`:

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
PA_ANALYTICS_AUTH_ENABLED=true
PA_ANALYTICS_AUTH_USERNAME
PA_ANALYTICS_AUTH_PASSWORD
PA_WORKFLOW_API_TOKEN
PA_DEFAULT_BASE_CURRENCY
PA_BIND_ADDRESS=127.0.0.1
```

Require distinct URL-safe secrets for PostgreSQL, analytics authentication, and the workflow token.

- [ ] **Step 3: Document the manual end-to-end smoke test**

Add:

```bash
cd /volume1/docker/pa-investing/backend

docker compose exec -T backend-api \
  python -m pa_investing.scripts.import_ibkr_positions --source flex

docker compose exec -T backend-api \
  python -m pa_investing.scripts.run_scheduled_snapshot

docker compose exec -T backend-api \
  python -m pa_investing.scripts.show_positions
```

Expected evidence:

- IBKR command reports imported accounts, positions, transactions, and reconciliation status.
- Snapshot command prints a new snapshot ID.
- `show_positions` displays the real internal instrument IDs.
- Notion shows a Daily Review for the current Europe/London date.
- Position `Price As Of`, `FX As Of`, reporting value, and portfolio weight are populated.

- [ ] **Step 4: Document the UGOS task schedule**

Add the exact commands and times below. Each task must run as the NAS account that can execute Docker Compose.

**06:00 Europe/London — full morning cycle:**

```bash
cd /volume1/docker/pa-investing/backend && docker compose exec -T backend-api python -m pa_investing.scripts.import_ibkr_positions --source flex && docker compose exec -T backend-api python -m pa_investing.scripts.run_scheduled_snapshot
```

**12:00, 18:00, and 00:00 Europe/London — snapshot refresh:**

```bash
cd /volume1/docker/pa-investing/backend && docker compose exec -T backend-api python -m pa_investing.scripts.run_scheduled_snapshot
```

**02:30 Europe/London — database backup:**

```bash
/volume1/docker/pa-investing/backend/scripts/backup_postgres.sh
```

Document that scheduler output must be retained in UGOS task logs and that the morning command intentionally uses `&&`: a failed IBKR import prevents the refresh from being reported as a successful full cycle.

- [ ] **Step 5: Document backup validation and restore drill**

Add:

```bash
cd /volume1/docker/pa-investing/backend
scripts/backup_postgres.sh
latest=$(ls -1t backups/pa_investing-*.dump | head -1)
docker compose exec -T postgres createdb -U pa_investing pa_investing_restore_test
docker compose exec -T postgres pg_restore -U pa_investing -d pa_investing_restore_test < "$latest"
docker compose exec -T postgres psql -U pa_investing -d pa_investing_restore_test -c 'SELECT count(*) FROM portfolio_snapshots;'
docker compose exec -T postgres dropdb -U pa_investing pa_investing_restore_test
```

Expected: restore completes, the snapshot count is non-zero after the first real refresh, and the temporary database is removed.

- [ ] **Step 6: Document update and rollback procedures**

Add:

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

State that application rollback means checking out the previously deployed commit and rebuilding the backend image. Database rollback must use the pre-update dump; never run an Alembic downgrade against the only production database without a tested restore.

- [ ] **Step 7: Update the root project next step**

In `README.md`, replace the NAS deployment recommendation with a link to the new UGREEN section in `backend/README.md`, and state that the next app-layer milestone begins only after seven consecutive successful morning cycles.

- [ ] **Step 8: Validate documentation**

Run:

```bash
git diff --check
rg -n "UGREEN DXP4800 Plus Deployment|06:00 Europe/London|backup_postgres" backend/README.md README.md
```

Expected: no whitespace errors and all three operating concepts are present.

- [ ] **Step 9: Commit Task 3**

```bash
git add README.md backend/README.md
git commit -m "docs: add UGREEN NAS deployment runbook"
```

---

### Task 4: Run the Local Container Release Gate

**Files:**

- No source changes expected.

**Interfaces:**

- Consumes: the completed Compose, backup, test, and documentation changes.
- Produces: an image and stack proven locally before copying to the NAS.

- [ ] **Step 1: Run the complete deterministic test suite**

```bash
cd backend
.venv/bin/python -m pytest
```

Expected: all tests pass.

- [ ] **Step 2: Run Ruff**

```bash
cd backend
.venv/bin/ruff check .
```

Expected: `All checks passed!`.

- [ ] **Step 3: Validate and build Compose**

With `backend/.env` configured for a disposable local stack, run:

```bash
cd backend
docker compose config --quiet
docker compose build --pull
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1:8000/health
```

Expected: PostgreSQL and backend report healthy and the health endpoint returns `{"status":"ok"}`.

- [ ] **Step 4: Verify restart behavior**

```bash
cd backend
docker compose restart
docker compose ps
curl --retry 12 --retry-delay 5 --retry-connrefused --fail http://127.0.0.1:8000/health
```

Expected: both services return to healthy without manual intervention.

- [ ] **Step 5: Stop the disposable local stack without deleting data**

```bash
cd backend
docker compose down
```

Expected: containers stop and the named `pa_postgres_data` volume remains. Do not use `docker compose down -v`.

---

### Task 5: Deploy and Prove the NAS MVP

**Files:**

- NAS runtime copy at `/volume1/docker/pa-investing`.
- NAS secret file at `/volume1/docker/pa-investing/backend/.env`.

**Interfaces:**

- Consumes: the verified repository commit, real provider credentials, and UGOS Docker/task scheduler.
- Produces: a continuously running Notion-first production MVP with scheduled data refresh and backup evidence.

- [ ] **Step 1: Install Docker from the UGOS Pro App Center**

Confirm `docker version` and `docker compose version` succeed over NAS SSH before copying the project.

- [ ] **Step 2: Copy the verified repository to the canonical NAS path**

Place the checked-out repository at:

```text
/volume1/docker/pa-investing
```

Do not copy the Mac `.venv`, `.env`, database files, caches, or `.DS_Store` files.

- [ ] **Step 3: Configure production secrets**

Create `/volume1/docker/pa-investing/backend/.env` from `.env.example`, fill every value listed in Task 3, and run:

```bash
chmod 600 /volume1/docker/pa-investing/backend/.env
```

Confirm the Notion integration still has access to the five source databases.

- [ ] **Step 4: Start the production stack**

```bash
cd /volume1/docker/pa-investing/backend
docker compose config --quiet
docker compose build --pull
docker compose run --rm backend-api alembic upgrade head
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1:8000/health
```

Expected: both containers are healthy and PostgreSQL is not published on a host port.

- [ ] **Step 5: Run the manual full cycle and backup**

Run the smoke-test and backup commands from Task 3. Do not create scheduler tasks until all three succeed.

- [ ] **Step 6: Create the five UGOS scheduler entries**

Create one full-cycle task at `06:00`, snapshot tasks at `12:00`, `18:00`, and `00:00`, and a backup task at `02:30`, all in the `Europe/London` timezone.

- [ ] **Step 7: Perform a restart drill**

Restart the Docker application from UGOS, then run:

```bash
cd /volume1/docker/pa-investing/backend
docker compose ps
curl --retry 12 --retry-delay 5 --retry-connrefused --fail http://127.0.0.1:8000/health
```

Expected: services recover automatically and the previous Notion/portfolio data remains intact.

- [ ] **Step 8: Observe seven consecutive morning cycles**

For seven days, verify:

- the 06:00 task exits successfully;
- a current Daily Review appears in Notion;
- position and FX timestamps advance;
- the latest provider runs show no unexplained failure;
- a valid daily dump appears under `backend/backups/`;
- no duplicate IBKR transactions or duplicate Daily Review rows appear.

If one check fails, keep the app layer milestone paused, retain the failure log, and diagnose the specific provider or boundary before adding retries.

## Acceptance Criteria

The NAS deployment slice is complete only when:

- Docker Compose, not a VM, runs the workload on the DXP4800 Plus.
- PostgreSQL and FastAPI both report healthy after a restart.
- PostgreSQL has no published host port.
- the API remains bound to NAS loopback.
- IBKR Flex secrets are present inside `backend-api` without appearing in Git or image layers.
- a manual IBKR import followed by refresh produces a current Notion Daily Review.
- all five UGOS scheduler tasks are enabled and emit retained logs.
- a dump can be restored into a temporary PostgreSQL database.
- seven consecutive morning cycles complete without manual intervention.
- the full pytest suite and Ruff pass on the deployment commit.

## Explicitly Deferred

- Tailscale container or HTTPS reverse-proxy exposure.
- Next.js/PWA or native mobile application.
- Public internet access.
- Push notifications.
- Exchange-aware market calendars.
- Cash-flow-aware performance.
- Additional finance skills or agents.
