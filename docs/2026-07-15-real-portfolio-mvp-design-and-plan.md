# Real Portfolio MVP: Data Correctness and Notion Sync

**Status:** Approved for implementation on 2026-07-15

**Progress:** Slice 1 implemented on 2026-07-15; Slice 2 is next.

## Objective

Build the next real-portfolio MVP around two outcomes:

1. portfolio calculations remain honest when cost basis, prices, FX, or broker data are stale or missing;
2. Notion displays real accounts and positions while allowing the user to maintain selected overrides.

The MVP uses T-1 IBKR Flex positions. External delayed quotes and FX may refresh during the day.
TWS/IB Gateway and Coinbase are planned extensions, not dependencies of this delivery.

## Architectural Boundaries

- PostgreSQL is the calculation and normalized-data source of truth.
- Notion is the operating surface and owns only explicitly editable fields.
- Broker and market-data payloads retain their source and observation time.
- Reconciled broker state and current operational state are separate concepts.
- No connector exposes order, trade, transfer, or withdrawal operations.
- Missing data produces a warning or incomplete result, never a silently fabricated value.

## Generalized Domain Model

### Accounts

An account has an internal identity, source provider, provider account identifier, display name,
base currency, and observation timestamps. The model must support IBKR securities accounts and
future Coinbase accounts without broker-specific fields in the core account record.

### Instruments

Each instrument has an internal `instrument_id`. Symbols are display attributes and are not
primary keys. Optional provider identifiers are stored separately:

| Provider | Identifier type | Example |
|---|---|---|
| IBKR | `conid` | `123456789` |
| IBKR | `local_symbol` | `SGLN` |
| Twelve Data | `symbol` | `SGLN:LSE` |
| Coinbase | `product_id` | `BTC-USD` |

The core instrument keeps only generalized attributes such as asset type, display symbol, name,
and trading currency. ISIN, exchange, conid, and crypto product IDs remain optional identifiers.

### Position State

Positions are unique by account and internal instrument. A position stores:

- quantity;
- broker-reported average cost, when available;
- nullable manual average-cost override;
- effective average cost and its status;
- reconciled observation time and source;
- latest selected quote and quote metadata.

Cost precedence is:

1. manual override, including an explicit zero;
2. valid broker-reported cost;
3. cost reconstructed from matching trades;
4. zero with status `unavailable`.

Supported effective statuses are `manual`, `broker`, `trade_reconstructed`, and `unavailable`.
An IBKR import updates broker cost but never clears a manual override. Clearing the Notion override
sets it to null and recalculates effective cost from broker data.

### Price and FX Observations

Quotes and FX rates are timestamped observations, not mutable instrument attributes. Each record
contains provider, observed time, retrieval time, value, currency pair where applicable, and data
quality such as current, delayed, EOD, or stale.

The current MVP will test Twelve Data against representative US, European, and LSE instruments.
IBKR report-date marks remain the fallback. A provider quote is accepted only when its configured
mapping and returned listing currency agree with the normalized instrument.

### Future Reconciled and Current Views

Flex supplies reconciled T-1 positions, costs, transactions, and account values. A future TWS or
IB Gateway adapter may supply current positions and delayed/live marks. It will overlay rather than
rewrite reconciled history. A future Coinbase adapter will produce the same account, balance,
position, and quote observations using view-only credentials.

## Reporting Currency

Notion contains one `Settings` row named `Portfolio` with a `Base Currency` value of `USD` or
`GBP`. The backend validates and persists the selection before calculation. If Notion is
temporarily unavailable, the last persisted value is retained.

Every position value is converted from its trading currency into the reporting currency using a
timestamped FX observation. A stale persisted rate may be used only with a visible warning. If no
rate is available, the position remains visible but is excluded from reporting-currency totals.

Until cash balances are imported, percentage fields are labelled `% of Invested Portfolio`, not
`% of NAV`. IBKR EOD NAV, current invested value, and cash must not be presented as the same metric.

## Notion Data Ownership

### Settings

User-owned fields:

- `Name` title, with one `Portfolio` row;
- `Base Currency` select: `USD` or `GBP`.

### Accounts

Backend-owned fields:

- `Name`;
- `External ID`;
- `Provider`;
- `Base Currency`;
- `Invested Value`;
- `% of Invested Portfolio`;
- `Position Count`;
- `Reconciled As Of`;
- `Last Refresh`;
- `Data Status`.

### Positions

Backend-owned fields in the compact view:

- `Name`;
- `External ID`;
- `Account`;
- `Asset Class`;
- `Quantity`;
- `Price`;
- `Market Value`;
- `% of Invested Portfolio`;
- `Unrealized PnL`;
- `Cost Status`;
- `Price As Of`;
- `Price Source`.

User-owned fields:

- `Cost Override` as nullable average cost per unit;
- `Theme`;
- `Notes`;
- user review labels added later.

Secondary backend fields such as internal instrument ID, trading currency, and provider identifiers
may be present but hidden from the default mobile view. Flexible Notion sync writes only compatible
properties that exist and never overwrites user-owned fields.

### Daily Review

Daily Review adds account allocation, asset-class allocation, top holdings, data freshness, cost
basis coverage, FX coverage, and warnings. Unavailable cost basis is excluded from reliable P&L.

## Refresh Workflow

1. Start an ingestion run and retrieve the complete Flex report.
2. Validate report completeness before closing any previously open position.
3. Normalize accounts, instruments, provider identifiers, and reconciled positions.
4. Upsert broker fields while preserving manual overrides.
5. Read the persisted setting and existing Notion settings/overrides.
6. Apply valid override changes and cost precedence.
7. Fetch mapped delayed quotes and FX rates where configured.
8. Select the best valid quote, falling back to the timestamped IBKR EOD mark.
9. Calculate local-currency values, reporting-currency values, allocations, and reliable P&L.
10. Persist observations and the portfolio snapshot.
11. Sync Accounts, Positions, Signals, and Daily Review to Notion.
12. Record completion status, warnings, and counts for operational review.

Notion failure after database persistence does not roll back broker data. The next idempotent run
retries the presentation sync.

## Failure Rules

- Explicit manual zero is valid and has status `manual`.
- An invalid Notion override retains the previous valid override and emits a warning.
- An empty Notion override clears the manual value only when the field was read successfully.
- A Notion outage does not clear settings or overrides.
- A missing quote uses the IBKR EOD mark and displays `EOD*`.
- A stale FX rate is timestamped and marked stale.
- Missing FX excludes the affected value from aggregate reporting-currency totals.
- A quote with mismatched listing currency is rejected.
- An incomplete Flex response cannot close positions absent from that response.
- Raw broker responses are never written to Notion.

## Security

- IBKR Flex token, Twelve Data key, Notion token, and future Coinbase keys remain environment or
  secret-store values.
- Coinbase will use `View` permission only.
- A future TWS adapter will expose query methods only, use the API Read-Only setting where verified,
  and restrict its socket to the application network.
- The application contains no order, trade, transfer, or withdrawal interface.
- Raw broker payloads may contain sensitive account data and will use protected NAS storage when
  raw-payload retention is implemented.

## Implementation Sequence

### Slice 1: Manual Cost Basis and Honest P&L

1. Add `manual` cost status and separate broker/manual average-cost persistence.
2. Make effective average cost a single tested domain rule.
3. Preserve manual overrides through repeated broker imports.
4. Exclude unavailable cost basis from snapshots, Daily Review P&L, and reliable totals.
5. Add migration and repository regression coverage, including explicit manual zero and clearing.

Deliverable: imported positions have auditable cost provenance and never display fabricated P&L.

### Slice 2: Notion Settings, Accounts, and Positions

1. Extend Notion configuration for Settings, Accounts, and Positions database IDs.
2. Add schema-aware reads for Base Currency and Cost Override.
3. Add backend-owned payload builders that omit user-owned properties.
4. Add idempotent account and position upserts using stable external IDs.
5. Add account allocation, invested weight, freshness, and warning fields.
6. Verify compact mobile views manually in Notion.

Deliverable: real IBKR accounts and positions appear in Notion, and a user-entered cost override is
stored and reflected in the next calculation.

Implementation status (2026-07-15): backend implementation complete. Generic schema-aware Notion
reads preserve the difference between zero, empty, and missing values. Base currency is persisted,
manual cost overrides are applied or cleared safely, and read failures retain prior values.
Settings, Accounts, and Positions use stable external IDs and schema-flexible writes; user-owned
Base Currency, Cost Override, Theme, and Notes fields are never written by the backend. Account
summaries show currency-separated values until Slice 4 provides FX conversion. Real Notion setup
and phone/computer visual review remain manual verification steps.

### Slice 3: General Instrument Identity

1. Replace symbol primary keys with internal instrument IDs.
2. Add optional provider identifier records and uniqueness constraints.
3. Migrate legacy instruments deterministically without losing positions or price history.
4. Parse IBKR conid/local-symbol metadata when present without making it mandatory.
5. Refactor position and price repositories to use internal IDs.

Deliverable: multiple listings with similar symbols and future crypto instruments can coexist.

Implementation status (2026-07-15): backend implementation complete. Instruments now have stable
internal IDs, optional venue metadata, and generic provider identifier records. Positions and
prices reference internal IDs, while symbol remains a display and legacy market-data lookup field.
IBKR Flex parses conid, ISIN, local symbol, and venue when present; Client Portal parses conid and
venue. Legacy instruments, positions, manual costs, and prices migrate deterministically. Duplicate
symbols on different venues coexist, and symbol-only quote refresh is skipped when ambiguous rather
than applying an unsafe mark. Slice 4 will add explicit provider mappings for those listings.

### Slice 4: Quotes, FX, and Reporting Currency

1. Introduce timestamped quote and FX observation models.
2. Replace symbol-only quote requests with provider mapping requests.
3. Add a mocked and configurable Twelve Data adapter.
4. Test representative symbols with the user's key before enabling live refresh.
5. Add persisted fallback selection and listing/currency validation.
6. Calculate USD/GBP reporting values and incomplete-data coverage.

Deliverable: the same T-1 position inventory can receive safer delayed marks and coherent USD or
GBP reporting values.

### Slice 5: Unified Operational Workflow

1. Compose import, Notion reads, quote/FX refresh, calculation, persistence, and Notion writes.
2. Add ingestion-run status, warning counts, and last-success timestamps.
3. Pass broker and market-data settings through Docker Compose.
4. Add one NAS command with a non-zero exit code on failed broker or database stages.
5. Keep presentation-sync failure retryable without corrupting persisted portfolio state.

Deliverable: one scheduled command refreshes the real portfolio safely and observably.

## Deferred Extensions

- TWS/IB Gateway current-position overlay and reconciliation;
- Coinbase view-only account adapter;
- protected raw-payload retention;
- cash balances and true NAV weights;
- transaction-aware time-weighted and money-weighted returns;
- Sharpe ratio and attribution;
- interactive browser charts;
- LLM and specialist agents.

## Verification Gate

Before calling the MVP complete:

- all automated tests and Ruff checks pass;
- Alembic upgrades a clean database and a database containing legacy positions;
- an unavailable cost displays zero with a marker and no reliable P&L;
- a manual zero override survives a subsequent Flex import;
- clearing an override restores broker or reconstructed cost;
- USD and GBP selections produce traceable converted values;
- unsupported external quotes fall back to timestamped IBKR EOD marks;
- real IBKR accounts and positions sync idempotently into Notion;
- user-owned Notion fields survive repeated refreshes;
- the compact Notion view is checked on both phone and computer.
