# UGREEN NAS prebuilt Docker deployment guide

This guide records the deployment path that avoids relying on Git or source-code builds on the
UGREEN NAS:

```text
build backend image on Mac
→ export Docker image tar
→ copy tar to NAS
→ import image in UGREEN Docker
→ create/update Docker Project from Compose
→ run migrations and broker imports inside the backend container
```

Do not put credentials inside the Docker image. The image contains application code only. Keep
IBKR, Notion, database, and dashboard credentials in the NAS Docker project environment or NAS
`.env` file.

## 1. Build the backend image on Mac

Start Docker Desktop on the Mac first. Then:

```bash
cd /Users/chenkangan/Documents/PAMASTER/backend

docker build \
  --platform linux/amd64 \
  -t pa-investing-backend:f37701c .

docker save \
  pa-investing-backend:f37701c \
  -o pa-investing-backend-f37701c.tar
```

Use `linux/amd64` for the UGREEN DXP4800 Plus. If deploying a newer commit later, replace
`f37701c` with the new short commit hash and use the same tag consistently.

The output tar is a local deployment artifact:

```text
backend/pa-investing-backend-f37701c.tar
```

Do not commit this tar file.

## 2. Copy the image tar to NAS

Copy the tar file to a NAS folder visible from the UGREEN Docker app, for example:

```text
/volume1/docker/images/pa-investing-backend-f37701c.tar
```

SMB, UGREEN file manager, or NAS folder sync are fine for copying this tar file. This is a built
artifact, not a live source-code deployment folder.

## 3. Import the image in UGREEN Docker

In the UGREEN Docker app:

```text
镜像 → 本地镜像 → 添加镜像 → 从NAS导入
```

Select:

```text
pa-investing-backend-f37701c.tar
```

After import, local images should show:

```text
pa-investing-backend:f37701c
```

If the image appears as `<none>` or `镜像异常`, the import did not produce a usable tagged image.
Rebuild and re-export the tar from Docker Desktop, then import again.

## 4. Create or update the UGREEN Docker Project

Use Docker Project / Compose rather than manually creating a single container. The app needs both:

- `backend-api`
- `postgres`

Use the repo file:

```text
backend/docker-compose.prebuilt.yml
```

The important backend setting is:

```text
PA_BACKEND_IMAGE=pa-investing-backend:f37701c
```

For LAN testing, expose the backend with:

```yaml
ports:
  - "0.0.0.0:8000:8000"
```

If the Compose file uses:

```yaml
ports:
  - "${PA_BIND_ADDRESS:-127.0.0.1}:8000:8000"
```

then set:

```text
PA_BIND_ADDRESS=0.0.0.0
```

A simple restart may not apply port-binding changes. Recreate/redeploy the project after changing
ports or bind addresses.

## 5. Required NAS environment values

Set these in the UGREEN Docker Project environment or NAS `.env` file:

```text
PA_BACKEND_IMAGE=pa-investing-backend:f37701c
PA_POSTGRES_PASSWORD=<long unique password>

PA_IBKR_FLEX_TOKEN=<IBKR Flex token>
PA_IBKR_FLEX_QUERY_ID=<current positions Flex Query ID>
PA_IBKR_FLEX_HISTORY_QUERY_ID=1583705
PA_IBKR_FLEX_TIMEZONE=Europe/London
PA_MARKET_DATA_RECONCILIATION_TOLERANCE=0.01

PA_ANALYTICS_AUTH_ENABLED=true
PA_ANALYTICS_AUTH_USERNAME=<dashboard username>
PA_ANALYTICS_AUTH_PASSWORD=<dashboard password>
PA_WORKFLOW_API_TOKEN=<long unique token>

PA_DEFAULT_BASE_CURRENCY=USD
PA_BIND_ADDRESS=0.0.0.0
```

Optional Notion and market-data values, if using the existing Notion refresh stack:

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

## 6. Verify the backend is reachable

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
NAS port binding. Check the container/project port mapping. It should expose NAS port `8000` to
container port `8000`.

## 7. Run database migrations

Open a terminal/exec session in the `pa-investing-backend-api-1` container and run:

```bash
alembic upgrade head
```

Expected migration evidence for the broker P&L deployment:

```text
Running upgrade 0009_historical_market_data -> 0010_broker_daily_pnl
Running upgrade 0010_broker_daily_pnl -> 0011_broker_daily_nav
```

If the database is already migrated, Alembic may print no upgrade lines.

## 8. Import IBKR without manual downloads

The correct unattended path is IBKR Flex Web Service:

```text
PA_IBKR_FLEX_TOKEN
PA_IBKR_FLEX_QUERY_ID
PA_IBKR_FLEX_HISTORY_QUERY_ID
```

`PA_IBKR_FLEX_HISTORY_QUERY_ID` should point to the saved Activity Flex Query:

```text
PA History YTD Daily XML
Query ID: 1583705
Account: U24549379
Period: Year to Date
Format: XML
Breakout by Day: Yes
```

The query must include these sections for the dashboard:

- `Change in NAV`
- `Mark-to-Market Performance Summary in Base`
- `Month & Year to Date Performance Summary in Base`
- `Open Positions`
- `Trades`
- `Financial Instrument Information`

Run inside the backend container:

```bash
python -m pa_investing.scripts.import_ibkr_history
```

Expected healthy result:

```text
IBKR history import completed: accounts=1 snapshots=148 nav_points=148 pnl_points=1166
```

Counts will move over time. The important checks are:

- `accounts=1`
- `snapshots` and `nav_points` are non-zero
- `pnl_points` is much larger than `21`
- the account is `U24549379`

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

If the account is wrong, fix the saved Flex Query account selection in IBKR. The previous failure
case was caused by the Web Service query returning account `U24549380` while the useful data was in
`U24549379`.

## 9. Import current positions

Run inside the backend container:

```bash
python -m pa_investing.scripts.import_ibkr_positions --source flex
```

This uses:

```text
PA_IBKR_FLEX_QUERY_ID
```

Keep this separate from:

```text
PA_IBKR_FLEX_HISTORY_QUERY_ID
```

The first is for current positions. The second is for YTD daily broker NAV/P&L history.

## 10. Test dashboard URLs

From the Mac:

```text
http://192.168.1.137:8000/analysis/portfolio
http://192.168.1.137:8000/analysis/daily-pnl?days=220
```

If analytics auth is enabled, use:

```text
PA_ANALYTICS_AUTH_USERNAME
PA_ANALYTICS_AUTH_PASSWORD
```

## 11. Schedule unattended IBKR refresh

Use UGREEN scheduled task / task scheduler. Run as a NAS account that can operate Docker.

Recommended daily command after markets/data are available:

```bash
cd /volume1/docker/pa-investing/backend && docker compose -f docker-compose.prebuilt.yml exec -T backend-api python -m pa_investing.scripts.import_ibkr_positions --source flex && docker compose -f docker-compose.prebuilt.yml exec -T backend-api python -m pa_investing.scripts.import_ibkr_history && docker compose -f docker-compose.prebuilt.yml exec -T backend-api python -m pa_investing.scripts.run_scheduled_snapshot
```

The `&&` chaining is intentional. If IBKR import fails, the later refresh should not pretend the
full cycle succeeded.

For broker P&L only:

```bash
cd /volume1/docker/pa-investing/backend && docker compose -f docker-compose.prebuilt.yml exec -T backend-api python -m pa_investing.scripts.import_ibkr_history
```

No IBKR browser login or manual XML download is required for scheduled runs as long as:

- the Flex token is valid;
- the saved query IDs are correct;
- the saved history query account is `U24549379`;
- the query format is XML;
- the history query period includes available report dates.

## 12. Common failure modes

### `pull access denied for pa-investing-backend`

The NAS cannot find the local image tag and is trying to pull it from Docker Hub.

Fix:

```text
镜像 → 本地镜像 → 添加镜像 → 从NAS导入
```

Verify:

```text
pa-investing-backend:f37701c
```

matches:

```text
PA_BACKEND_IMAGE=pa-investing-backend:f37701c
```

### `/health` works inside container but not from Mac

The app is healthy; the problem is NAS port binding.

Use:

```yaml
ports:
  - "0.0.0.0:8000:8000"
```

Redeploy/recreate the project, then test:

```bash
curl -v http://192.168.1.137:8000/health
```

### `IBKR history import returned no daily history rows`

Check env inside the backend container:

```bash
python - <<'PY'
import os
for k in [
    "PA_IBKR_FLEX_TOKEN",
    "PA_IBKR_FLEX_QUERY_ID",
    "PA_IBKR_FLEX_HISTORY_QUERY_ID",
]:
    v = os.environ.get(k, "")
    print(k, "set" if v else "MISSING", v[:4] + "..." if v else "")
PY
```

Then save and inspect raw XML as shown above. Most issues are wrong/missing query ID, wrong saved
account, expired token, or a temporary empty IBKR Flex response.

### Do not commit or sync these

Keep these out of Git and source folder sync:

```text
backend/.env
backend/*.tar
backend/*.db
backend/backups/
raw IBKR XML containing account data
```
