# UGREEN NAS prebuilt Docker deployment guide

This is the canonical deployment path for running PA Investing on the UGREEN NAS without Git or
source-code builds on the NAS.

```text
build backend image on Mac
→ save Docker image tar
→ copy tar + LAN Compose file to NAS
→ import image in UGREEN Docker
→ create/update Docker Project from Compose
→ run migrations
→ open dashboard and use browser refresh buttons
```

The Docker image contains application code only. Do not put credentials inside the image. Keep
IBKR, Notion, PostgreSQL, and dashboard credentials in the UGREEN Docker Project environment.

## 0. Files and compose variant

Use this Compose file for the current UGREEN Docker app / LAN testing path:

```text
backend/docker-compose.ugreen-lan.yml
```

It publishes the app with:

```yaml
ports:
  - "${PA_NAS_HTTP_PORT:-8000}:8000"
```

Do not set `PA_BIND_ADDRESS` for this path. That older variable belongs to loopback/private-proxy
compose files and caused the previous “works inside container but not from Mac” confusion.

## 1. Build the backend image on Mac

Start Docker Desktop on the Mac first. Then run:

```bash
cd /Users/chenkangan/Documents/PAMASTER/backend

tag=$(git rev-parse --short HEAD)
docker build --platform linux/amd64 -t "pa-investing-backend:${tag}" .
docker save "pa-investing-backend:${tag}" -o "pa-investing-backend-${tag}.tar"
echo "Built pa-investing-backend:${tag}"
```

Use `linux/amd64` for the UGREEN DXP4800 Plus.

The output tar is a local deployment artifact, for example:

```text
backend/pa-investing-backend-d535cef.tar
```

Do not commit Docker image tar files.

## 2. Copy two deployment files to NAS

Copy these two files to a NAS folder visible from the UGREEN Docker app:

```text
backend/pa-investing-backend-<tag>.tar
backend/docker-compose.ugreen-lan.yml
```

For example:

```text
/volume1/docker/images/pa-investing-backend-<tag>.tar
/volume1/docker/pa-investing/docker-compose.ugreen-lan.yml
```

SMB, UGREEN file manager, or NAS folder sync are fine for copying these files. The tar is a built
artifact, not a live source-code deployment folder.

## 3. Import the image in UGREEN Docker

In the UGREEN Docker app:

```text
镜像 → 本地镜像 → 添加镜像 → 从NAS导入
```

Select:

```text
pa-investing-backend-<tag>.tar
```

After import, local images should show:

```text
pa-investing-backend:<tag>
```

If the image appears as `<none>` or `镜像异常`, the import did not produce a usable tagged image.
Delete that imported image, rebuild and re-export the tar from Docker Desktop, then import again.
Do not create/update the project until the image is healthy.

## 4. Create or update the UGREEN Docker Project

Use Docker Project / Compose rather than manually creating a single container. The app needs both:

- `backend-api`
- `postgres`

In UGREEN Docker:

1. Go to `项目` / `Projects`.
2. Create a new project or edit the existing `pa-investing` project.
3. Import/use `docker-compose.ugreen-lan.yml`.
4. Set the environment values in the project editor.
5. Start or recreate the project.

The important image setting is:

```text
PA_BACKEND_IMAGE=pa-investing-backend:<tag>
```

For this LAN Compose file, port exposure is controlled by:

```text
PA_NAS_HTTP_PORT=8000
```

Do not add `PA_BIND_ADDRESS` to this project.

## 5. Required NAS environment values

Set these in the UGREEN Docker Project environment:

```text
PA_BACKEND_IMAGE=pa-investing-backend:<tag>
PA_POSTGRES_PASSWORD=<long unique password>

PA_IBKR_FLEX_TOKEN=<IBKR Flex token>
PA_IBKR_FLEX_QUERY_ID=<current positions Flex Query ID>
PA_IBKR_FLEX_HISTORY_QUERY_ID=<YTD daily history Flex Query ID>
PA_IBKR_FLEX_TIMEZONE=Europe/London
PA_IBKR_FLEX_REFRESH_COOLDOWN_SECONDS=900
PA_MARKET_DATA_RECONCILIATION_TOLERANCE=0.01

PA_ANALYTICS_AUTH_ENABLED=true
PA_ANALYTICS_AUTH_USERNAME=<dashboard username>
PA_ANALYTICS_AUTH_PASSWORD=<dashboard password>
PA_WORKFLOW_API_TOKEN=<long unique token>

PA_DEFAULT_BASE_CURRENCY=GBP
PA_NAS_HTTP_PORT=8000
```

Optional Notion and market-data values, if using the existing Notion refresh stack and live market
data:

```text
PA_NOTION_ENABLED=true
PA_NOTION_API_KEY=<Notion integration token>
PA_NOTION_SETTINGS_DATABASE_ID=<id>
PA_NOTION_ACCOUNTS_DATABASE_ID=<id>
PA_NOTION_POSITIONS_DATABASE_ID=<id>
PA_NOTION_SIGNALS_DATABASE_ID=<id>
PA_NOTION_DAILY_REVIEW_DATABASE_ID=<id>

PA_MARKET_DATA_PROVIDER=twelve_data
PA_TWELVE_DATA_API_KEY=<Twelve Data key>
```

Use distinct secrets for PostgreSQL, dashboard auth, and workflow token. Do not reuse the IBKR,
Notion, NAS administrator, or Tailscale credentials.

## 6. Run database migrations

Run migrations once after creating a fresh project or deploying an image that includes new
migrations:

```bash
alembic upgrade head
```

In UGREEN Docker this is usually done from the `backend-api` container terminal.

If UGREEN only gives you container command fields, temporarily run the backend image with command:

```text
alembic upgrade head
```

Wait for it to finish successfully, then restore the normal API command:

```text
uvicorn pa_investing.main:app --host 0.0.0.0 --port 8000
```

If the database is already migrated, Alembic may print no upgrade lines.

## 7. Verify the backend is reachable

Find the NAS IP from:

```text
UGREEN Control Panel → Network → Network Connection
```

Example from the current deployment:

```text
192.168.1.137
```

From the Mac:

```bash
curl -v http://192.168.1.137:8000/health
```

Expected:

```json
{"status":"ok"}
```

If it works inside the backend container but not from the Mac, the app is healthy and the issue is
NAS port mapping. Check that the project uses `docker-compose.ugreen-lan.yml` and exposes NAS port
`8000` to container port `8000`.

## 8. Open the dashboard

From a Mac or phone on the same LAN:

```text
http://192.168.1.137:8000/analysis/portfolio
```

If analytics auth is enabled, use:

```text
PA_ANALYTICS_AUTH_USERNAME
PA_ANALYTICS_AUTH_PASSWORD
```

The Portfolio page should show:

- current NAV and allocation;
- P&L Calendar with a default one-month display range;
- Performance History with the same display range;
- `Positions query` and `History query` freshness labels;
- buttons for `Refresh Positions` and `Refresh History`.

## 9. First browser refresh

Use the browser buttons instead of opening the Docker terminal for normal manual refreshes:

1. Click `Refresh Positions`.
2. Confirm the status mentions positions and trades.
3. Wait for the IBKR cooldown, usually 15 minutes.
4. Click `Refresh History`.
5. Confirm the `Positions query` and `History query` freshness labels updated.
6. Confirm the P&L Calendar and Latest Broker P&L Contributors show the latest broker report date
   available from IBKR.

`Refresh Positions` imports current positions, closed positions, and trade executions, then
refreshes the dashboard snapshot. `Refresh History` imports YTD broker NAV and daily MTM P&L.
Those are intentionally separate because IBKR Flex rate-limits back-to-back requests from the same
token.

## 10. Optional terminal diagnostics

If browser refresh fails and you have a backend container terminal, inspect environment values:

```bash
python - <<'PY'
import os
for k in [
    "PA_IBKR_FLEX_TOKEN",
    "PA_IBKR_FLEX_QUERY_ID",
    "PA_IBKR_FLEX_HISTORY_QUERY_ID",
    "PA_IBKR_FLEX_TIMEZONE",
]:
    v = os.environ.get(k, "")
    print(k, "set" if v else "MISSING", v[:4] + "..." if v else "")
PY
```

Import current positions manually:

```bash
python -m pa_investing.scripts.import_ibkr_positions --source flex
```

Import YTD broker history manually:

```bash
python -m pa_investing.scripts.import_ibkr_history
```

Expected healthy history result resembles:

```text
IBKR history import completed: accounts=1 snapshots=148 nav_points=148 pnl_points=1166
```

Counts move over time. The important checks are:

- `accounts` is non-zero;
- `snapshots` and `nav_points` are non-zero;
- `pnl_points` is much larger than `21`;
- the saved history query is for the correct account.

If the import returns no rows, save raw XML for diagnosis:

```bash
python -m pa_investing.scripts.import_ibkr_history \
  --save-raw-xml /tmp/ibkr_history_raw.xml \
  --allow-empty
```

Then inspect it:

```bash
python - <<'PY'
import xml.etree.ElementTree as ET
from collections import Counter

p = "/tmp/ibkr_history_raw.xml"
root = ET.parse(p).getroot()
counts = Counter(el.tag for el in root.iter())

print("root", root.tag, root.attrib)
for tag in [
    "FlexStatement",
    "ChangeInNAV",
    "MTMPerformanceSummaryInBase",
    "MTMPerformanceSummaryUnderlying",
    "OpenPosition",
    "SymbolSummary",
]:
    print(tag, counts.get(tag, 0))

for stmt in root.findall(".//FlexStatement")[:3]:
    print("statement", stmt.attrib)
PY
```

Healthy evidence looks like:

```text
root FlexQueryResponse {'queryName': 'PA History YTD Daily XML', 'type': 'AF'}
FlexStatement 148
ChangeInNAV 148
MTMPerformanceSummaryUnderlying 1166
statement {'accountId': 'U24549379', ...}
```

If the account is wrong, fix the saved Flex Query account selection in IBKR. A previous failure
case was caused by the Web Service query returning the wrong account while the useful data was in
another account.

## 11. Scheduled refresh

For now, the lowest-friction manual NAS operation is the browser flow:

```text
Refresh Positions → wait 15 minutes → Refresh History
```

If you later configure UGOS scheduled tasks and the NAS has Docker Compose terminal support, use
commands based on `docker-compose.ugreen-lan.yml`, not the old prebuilt file:

```bash
cd /volume1/docker/pa-investing/backend && docker compose -f docker-compose.ugreen-lan.yml exec -T backend-api python -m pa_investing.scripts.import_ibkr_positions --source flex
```

Then wait for the IBKR cooldown before running history:

```bash
cd /volume1/docker/pa-investing/backend && docker compose -f docker-compose.ugreen-lan.yml exec -T backend-api python -m pa_investing.scripts.import_ibkr_history
```

Do not chain positions and history immediately unless IBKR rate limiting is no longer an issue for
your token.

## 12. Common failure modes

### `pull access denied for pa-investing-backend`

The NAS cannot find the local image tag and is trying to pull it from Docker Hub.

Fix:

```text
镜像 → 本地镜像 → 添加镜像 → 从NAS导入
```

Verify the imported image tag matches `PA_BACKEND_IMAGE` exactly:

```text
pa-investing-backend:<tag>
PA_BACKEND_IMAGE=pa-investing-backend:<tag>
```

### `/health` works inside container but not from Mac

The app is healthy; the problem is NAS port mapping.

Use `docker-compose.ugreen-lan.yml` and ensure the project maps:

```yaml
ports:
  - "${PA_NAS_HTTP_PORT:-8000}:8000"
```

Recreate the project after changing ports, then test:

```bash
curl -v http://192.168.1.137:8000/health
```

### `IBKR Flex request failed (1018): Too many requests`

IBKR is rate-limiting requests from the Flex token. Wait at least
`PA_IBKR_FLEX_REFRESH_COOLDOWN_SECONDS`, normally 900 seconds, before running the other IBKR query.
This is why the dashboard has separate `Refresh Positions` and `Refresh History` buttons.

### `IBKR history import returned no daily history rows`

Most likely causes:

- wrong `PA_IBKR_FLEX_HISTORY_QUERY_ID`;
- saved history query uses the wrong IBKR account;
- Flex query format is not XML;
- query period has no available report dates;
- the token is expired or recently recreated and not active yet.

Use the raw XML diagnostic above. The history query should include daily `FlexStatement`,
`ChangeInNAV`, and `MTMPerformanceSummaryUnderlying` rows.

## 13. Do not commit or sync these

Keep these out of Git and source folder sync:

```text
backend/.env
backend/*.tar
backend/*.db
backend/backups/
raw IBKR XML containing account data
```
