# IBKR Connectivity Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retain IBKR Flex as the reconciled daily source while adding an optional read-only TWS/IB Gateway overlay for current account state and historical daily bars.

**Architecture:** Split shared TWS connectivity from its two consumers. `IbkrTwsBrokerConnector` reads current account and position observations without overwriting Flex reconciliation; `IbkrTwsHistoricalDataProvider` implements the historical-provider contract from the market-routing plan. Both depend on one optional `ib_async` client boundary and remain unavailable without breaking the NAS workflow.

**Tech Stack:** Python 3.12, Pydantic 2, SQLAlchemy 2, Alembic, `ib_async>=2,<3` optional dependency, pytest, Ruff.

## Global Constraints

- IBKR Flex remains the preferred daily account, transaction, cash, and reconciliation source.
- TWS/IB Gateway is optional and requires an authenticated desktop or gateway session.
- Core NAS workflows must continue when TWS/IB Gateway is offline.
- IBKR does not officially support headless TWS/IB Gateway operation; do not describe it as a reliable unattended NAS dependency.
- No IBKR username or password is stored by this application.
- The connector defaults to `readonly=True`, and deployment instructions require TWS/IB Gateway's Read Only API setting.
- The application exposes no order-placement, cancellation, modification, transfer, or withdrawal method.
- Current TWS observations never rewrite or erase reconciled Flex history.
- Historical requests use explicit conid/listing identity, bounded request sizes, and pacing.
- `TRADES` is split-adjusted but not dividend-adjusted; `ADJUSTED_LAST` is split-and-dividend-adjusted. Persist these exact modes.
- Market-data subscriptions and entitlements belong to the authenticated IBKR username; missing entitlement is a typed diagnostic.

---

## Target File Structure

```text
backend/src/pa_investing/
  integrations/
    ibkr_tws/
      __init__.py
      config.py        # endpoint and read-only configuration
      client.py        # optional ib_async lifecycle and typed errors
      contracts.py     # conid-first contract creation and qualification
  brokers/
    ibkr_tws.py        # current account/position observation adapter
  market_data/
    history/
      providers/
        ibkr.py        # daily historical adapter
```

### Task 1: Add the Optional Shared IBKR Client Boundary

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/src/pa_investing/integrations/__init__.py`
- Create: `backend/src/pa_investing/integrations/ibkr_tws/__init__.py`
- Create: `backend/src/pa_investing/integrations/ibkr_tws/config.py`
- Create: `backend/src/pa_investing/integrations/ibkr_tws/client.py`
- Test: `backend/tests/unit/test_ibkr_tws_client.py`

**Interfaces:**
- Produces: `IbkrTwsConfig`, `IbkrTwsClient`, and typed diagnostic errors.

- [ ] **Step 1: Write client tests**

Cover:

- paper defaults to port 7497 and live read-only defaults to 7496;
- Gateway port overrides 4002/4001 are accepted;
- `readonly` cannot be configured false;
- missing `ib_async` returns `dependency_missing`;
- closed socket returns `offline`;
- connect always passes `readonly=True`;
- paper profile rejects non-`DU` accounts;
- public diagnostics contain no secrets.

- [ ] **Step 2: Run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_ibkr_tws_client.py -q
```

Expected: failure because the integration package does not exist.

- [ ] **Step 3: Add optional dependency**

Add:

```toml
[project.optional-dependencies]
ibkr = [
  "ib_async>=2.0,<3.0",
]
```

Keep the import inside the client factory so base application startup does not require the extra.

- [ ] **Step 4: Implement connection lifecycle**

Expose a context manager:

```python
class IbkrTwsClient:
    def connect(self) -> ContextManager[IBSession]:
        raise NotImplementedError

    def diagnose(self) -> ProviderDiagnostic:
        raise NotImplementedError
```

Use unique configurable `client_id`, bounded connect timeout, guaranteed disconnect, and typed mapping for dependency, socket, authentication, and profile mismatch failures.

- [ ] **Step 5: Run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_ibkr_tws_client.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/src/pa_investing/integrations backend/tests/unit/test_ibkr_tws_client.py
git commit -m "feat: add optional read-only IBKR client"
```

### Task 2: Resolve IBKR Contracts by Stable Identity

**Files:**
- Create: `backend/src/pa_investing/integrations/ibkr_tws/contracts.py`
- Test: `backend/tests/unit/test_ibkr_tws_contracts.py`

**Interfaces:**
- Produces: `build_contract(ref) -> Contract` and `qualify_contract(session, contract) -> QualifiedContract`.

- [ ] **Step 1: Write conid-first tests**

Cover:

- conid produces a contract whose `conId` equals the requested integer;
- absent conid requires symbol, security type, currency, and exchange;
- ambiguous qualification raises `contract_ambiguous`;
- primary exchange is preserved;
- provider response identity is checked against the requested listing;
- qualification failure is not swallowed.

- [ ] **Step 2: Run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_ibkr_tws_contracts.py -q
```

Expected: failure because the contract helper does not exist.

- [ ] **Step 3: Implement strict qualification**

Unlike Vibe-Trading's prototype, do not ignore qualification errors. Return exactly one qualified contract or raise a typed error carrying conid, symbol, exchange, and currency without credentials.

- [ ] **Step 4: Run tests and commit**

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_ibkr_tws_contracts.py -q
git add backend/src/pa_investing/integrations/ibkr_tws/contracts.py backend/tests/unit/test_ibkr_tws_contracts.py
git commit -m "feat: resolve IBKR contracts safely"
```

### Task 3: Persist Current-State Observations Separately from Flex

**Files:**
- Create: `backend/alembic/versions/0010_add_current_broker_observations.py`
- Modify: `backend/src/pa_investing/domain/models.py`
- Modify: `backend/src/pa_investing/db/models.py`
- Modify: `backend/src/pa_investing/db/repositories.py`
- Test: `backend/tests/integration/test_current_broker_observations.py`

**Interfaces:**
- Produces: `CurrentAccountObservation`, `CurrentPositionObservation`, and repositories.

- [ ] **Step 1: Write persistence tests**

Assert:

- a TWS current observation and a Flex reconciled position coexist;
- importing a current quantity does not change the reconciled position row;
- observations retain source, observed time, conid, price, quantity, and currency;
- latest current observations can be queried by account and instrument;
- stale observations remain historical rather than being deleted.

- [ ] **Step 2: Run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/integration/test_current_broker_observations.py -q
```

Expected: failure because the observation models are missing.

- [ ] **Step 3: Add tables**

Create:

```text
current_account_observations
  id
  account_id
  provider
  observed_at
  base_currency
  net_liquidation        nullable
  cash                   nullable
  buying_power           nullable

current_position_observations
  id
  account_id
  instrument_id          nullable FK
  provider
  observed_at
  conid                  nullable
  symbol
  exchange               nullable
  currency
  quantity
  average_cost           nullable
  market_price           nullable
  market_value           nullable
```

Add uniqueness for a provider/account/instrument/observed-time observation, but retain historical rows.

- [ ] **Step 4: Implement repositories and tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/integration/test_current_broker_observations.py tests/integration/test_repositories.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/0010_add_current_broker_observations.py backend/src/pa_investing/domain/models.py backend/src/pa_investing/db/models.py backend/src/pa_investing/db/repositories.py backend/tests/integration/test_current_broker_observations.py
git commit -m "feat: store current broker observations"
```

### Task 4: Add the Read-Only TWS Broker Adapter

**Files:**
- Create: `backend/src/pa_investing/brokers/ibkr_tws.py`
- Test: `backend/tests/unit/test_ibkr_tws_connector.py`
- Test: `backend/tests/integration/test_ibkr_tws_observation_workflow.py`

**Interfaces:**
- Produces: `IbkrTwsBrokerConnector.fetch_current_snapshot()`.
- Does not implement the reconciled `BrokerConnector` import contract, preventing accidental position replacement.

- [ ] **Step 1: Write adapter tests**

Cover:

- managed accounts and account summary mapping;
- position mapping with conid, local symbol, security type, exchange, currency, quantity, and average cost;
- optional portfolio market price/value fields;
- unsupported assets are recorded as warnings;
- no order or open-order API is called or exposed;
- disconnect occurs on success and failure.

- [ ] **Step 2: Run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_ibkr_tws_connector.py -q
```

Expected: failure because the adapter does not exist.

- [ ] **Step 3: Implement current snapshot workflow**

Create a dedicated workflow that:

1. starts an `ibkr-tws/current_snapshot` provider run;
2. fetches the complete current account and position snapshot;
3. validates account profile and instrument identity;
4. persists observations;
5. records warnings and counts;
6. leaves Flex positions and reconciliations untouched.

- [ ] **Step 4: Run unit and integration tests**

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_ibkr_tws_connector.py tests/integration/test_ibkr_tws_observation_workflow.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/brokers/ibkr_tws.py backend/tests/unit/test_ibkr_tws_connector.py backend/tests/integration/test_ibkr_tws_observation_workflow.py
git commit -m "feat: add current IBKR observation overlay"
```

### Task 5: Implement IBKR Daily Historical Bars

**Files:**
- Create: `backend/src/pa_investing/market_data/history/providers/ibkr.py`
- Test: `backend/tests/unit/test_ibkr_historical_provider.py`

**Interfaces:**
- Implements `HistoricalDataProvider` from the historical-routing plan.

- [ ] **Step 1: Write provider tests**

Cover:

- `TRADES` maps to `AdjustmentMode.SPLITS`;
- `ADJUSTED_LAST` maps to `AdjustmentMode.ALL`;
- two request results must align by trading date;
- missing `ADJUSTED_LAST` entitlement rejects an adjusted request;
- provider timestamps are normalized from the configured TWS timezone;
- each request uses `1 day`, bounded duration chunks, `keepUpToDate=False`;
- pacing retries are bounded;
- contract ambiguity fails before requesting bars;
- provider diagnostics distinguish offline, dependency missing, entitlement missing, timeout, and pacing errors.

- [ ] **Step 2: Run tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_ibkr_historical_provider.py -q
```

Expected: failure because the provider does not exist.

- [ ] **Step 3: Implement historical fetching**

Request complete daily chunks with explicit end times. Keep substantially fewer than 50 simultaneous historical requests and serialize the initial implementation. Cancel a request that exceeds its deadline.

Do not claim a truly unadjusted series: official IBKR behavior defines `TRADES` as split-adjusted and `ADJUSTED_LAST` as split-and-dividend-adjusted.

- [ ] **Step 4: Run tests**

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_ibkr_historical_provider.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/market_data/history/providers/ibkr.py backend/tests/unit/test_ibkr_historical_provider.py
git commit -m "feat: add optional IBKR historical provider"
```

### Task 6: Add Diagnostics and Deployment Boundaries

**Files:**
- Modify: `backend/src/pa_investing/core/config.py`
- Modify: `backend/src/pa_investing/core/dependencies.py`
- Modify: `backend/src/pa_investing/api/routes.py`
- Modify: `backend/src/pa_investing/api/schemas.py`
- Test: `backend/tests/unit/test_config.py`
- Test: `backend/tests/unit/test_dependencies.py`
- Test: `backend/tests/integration/test_api_routes.py`

**Interfaces:**
- Produces:
  - `GET /analysis/connectors/ibkr-tws/status`
  - optional current-snapshot trigger protected by the workflow token.

- [ ] **Step 1: Add settings tests**

Add settings:

```text
PA_IBKR_TWS_ENABLED=false
PA_IBKR_TWS_HOST=127.0.0.1
PA_IBKR_TWS_PORT=7496
PA_IBKR_TWS_CLIENT_ID=77
PA_IBKR_TWS_ACCOUNT=
PA_IBKR_TWS_PROFILE=live-readonly
PA_IBKR_TWS_TIMEZONE=UTC
```

Reject an enabled non-local bind by default unless an explicit trusted-network flag is introduced in a later reviewed change.

- [ ] **Step 2: Add API tests**

Assert:

- disabled returns a clear unavailable diagnostic;
- offline returns diagnostic data without a 500;
- status never exposes account values unless analytics authentication passes;
- snapshot trigger requires the workflow bearer token;
- no route accepts order-like input.

- [ ] **Step 3: Implement dependency wiring**

When disabled or `ib_async` is absent, omit the IBKR historical provider from active routing or register it as unavailable according to the historical router's dependency convention. Do not fail application startup.

- [ ] **Step 4: Run tests**

```bash
cd backend
.venv/bin/python -m pytest tests/unit/test_config.py tests/unit/test_dependencies.py tests/integration/test_api_routes.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pa_investing/core backend/src/pa_investing/api backend/tests/unit/test_config.py backend/tests/unit/test_dependencies.py backend/tests/integration/test_api_routes.py
git commit -m "feat: expose IBKR connectivity diagnostics"
```

### Task 7: Document and Verify IBKR Operating Modes

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `backend/.env.example`
- Modify: `backend/THIRD_PARTY_NOTICES.md`

- [ ] **Step 1: Document the three separate IBKR roles**

Document:

1. Flex: reconciled prior-day account, positions, transactions, cash, and NAV.
2. TWS current overlay: optional current account and position observations.
3. TWS market data: optional final historical fallback when online and entitled.

State explicitly that none of these roles places trades.

- [ ] **Step 2: Document operating limitations**

Include:

- authenticated TWS/IB Gateway must already be running;
- official headless operation is unsupported;
- read-only API mode must be enabled;
- market-data subscriptions may be required;
- delayed data behavior differs from historical-data entitlement;
- historical pacing and request-size limits;
- TWS time zone affects returned daily bars;
- the NAS remains functional without TWS.

- [ ] **Step 3: Add attribution**

If the Vibe-Trading `ibkr/local.py` implementation is substantially copied, retain its MIT notice. Prefer independent implementation against the small contract in this plan and use upstream only as a behavioral reference.

- [ ] **Step 4: Run complete verification**

```bash
cd backend
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
```

Expected: all tests pass and Ruff reports no errors.

- [ ] **Step 5: Run migration verification**

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/alembic downgrade 0009_add_historical_market_data
.venv/bin/alembic upgrade head
```

Expected: migration round trip succeeds.

- [ ] **Step 6: Commit**

```bash
git add README.md backend/README.md backend/.env.example backend/THIRD_PARTY_NOTICES.md
git commit -m "docs: document IBKR connectivity modes"
```

## Completion Criteria

- Flex imports remain the reconciled source of truth.
- Current TWS data is a separate observation overlay.
- IBKR historical data implements the same public contract as Yahoo and Twelve Data.
- IBKR is the final optional fallback, not the primary provider.
- Application startup and daily workflows succeed while IBKR is disabled or offline.
- No IBKR order interface exists anywhere in the application service or HTTP surface.
- Every IBKR failure is diagnosable without exposing credentials or raw sensitive payloads.
