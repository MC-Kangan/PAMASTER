# PA Investing Demo Seed Portfolio Design

Date: 2026-07-10

## Purpose

Define the smallest repeatable data-loading path needed to make the first visible MVP easy to run.

The current backend can already:

- store accounts and positions in PostgreSQL;
- refresh prices;
- compute portfolio metrics and rule-based signals;
- sync `Signals` and `Daily Review` into Notion.

What is still missing for a reliable demo is a simple way to load a realistic starter portfolio without hand-editing the database. This design adds that path.

## Scope

This slice adds:

- one demo account for MVP use;
- one editable CSV fixture in the repo as the starter portfolio source;
- one CLI seed command that reads the CSV and upserts the account and positions into PostgreSQL;
- documentation for the seed-and-refresh demo flow.

This slice does not add:

- broker integrations;
- exchange-aware security master logic;
- an admin API route for seeding;
- multi-account portfolio grouping;
- a broader universe-management system.

## Recommended Approach

Three approaches were considered:

1. CSV fixture plus CLI seed command
2. Python-only hardcoded seed script
3. API-based seed route

The recommended approach is `CSV fixture plus CLI seed command`.

It is the best fit for the MVP because it is:

- easy to edit when symbols or sizes change;
- safe to rerun;
- aligned with the existing `CsvPositionImporter`;
- simpler and less risky than exposing admin seed behavior through the API.

## Demo Portfolio Model

The first MVP will use one account only:

- `pa-demo`

This keeps the demo understandable while leaving room for multiple accounts later.

The starter portfolio should span the target tradable universe categories already discussed:

- US equity: `SPGI`
- Europe equity: `ASML`
- Europe equity: `SAP`
- UK UCITS or LSE-listed product: `SGLN`
- UK UCITS or LSE-listed product: `SMH`

For the first MVP domain model:

- `SPGI`, `ASML`, and `SAP` are stored as `equity`
- `SGLN` and `SMH` are stored as `etf`

This is intentionally simple. The system does not need exchange-level classification or richer instrument metadata yet to support the first demo loop.

## Data Format

The CSV will reuse the existing importer schema:

- `account_id`
- `symbol`
- `name`
- `asset_class`
- `currency`
- `quantity`
- `average_cost`
- `latest_price`

The fixture should live in the test or demo fixture area so it is versioned and easy to inspect.

The CSV remains the editable source of truth for the demo portfolio definition, but not the runtime source of truth. After seeding, PostgreSQL remains the runtime source of truth.

## CLI Command

Add a small command that can be run manually, for example:

```bash
python -m pa_investing.scripts.seed_demo_portfolio
```

Behavior:

1. load application settings;
2. open a database session;
3. read the demo CSV through `CsvPositionImporter`;
4. upsert the demo account;
5. upsert each imported position into PostgreSQL;
6. print a short summary of what was loaded.

The command should be safe to rerun. Repeated runs should update existing rows instead of duplicating them.

## Idempotency And Data Boundaries

The seed command should rely on existing repository upsert behavior.

Expected idempotent behavior:

- rerunning the same seed command keeps one `pa-demo` account row;
- rerunning the same seed command keeps one row per account-and-symbol position;
- changed quantities, costs, or placeholder prices overwrite existing seeded values.

The seed command is only responsible for positions and account setup. It is not responsible for fetching current prices or generating signals. Those remain part of the existing refresh workflow.

## Price Handling

The CSV may include placeholder `latest_price` values so the rows are complete and readable.

However, these values should be treated only as starting values. The intended MVP flow is:

1. seed the demo portfolio;
2. run `POST /workflows/refresh-and-sync`;
3. let the live market data provider replace placeholder marks where available.

This keeps the responsibilities clear:

- seed command sets up demo holdings;
- refresh workflow produces current analytics state.

## Error Handling

The seed command should fail clearly when:

- the CSV is missing required columns;
- a row contains an invalid `asset_class`;
- numeric fields cannot be parsed;
- the database connection fails.

The command does not need partial-row recovery logic for the MVP. A failing run should exit with a clear error so the CSV can be corrected and rerun.

## Testing

Add focused coverage for:

- importing the new demo CSV fixture successfully;
- seeding the demo account and positions into a temporary database;
- rerunning the seed command without creating duplicates;
- updating an existing seeded position when CSV values change.

Tests should stay deterministic and should not depend on Notion or live price APIs.

## Documentation

Update the backend runbook to include the MVP demo flow:

1. run migrations;
2. run the demo seed command;
3. call `POST /workflows/refresh-and-sync`;
4. inspect Notion `Signals` and `Daily Review`.

This makes the first visible MVP easier to reproduce from a clean environment.

## Success Criteria

This slice is successful when:

- a single command loads the starter demo portfolio into PostgreSQL;
- the command can be rerun safely;
- the loaded portfolio includes the agreed starter symbols;
- the existing refresh workflow can run against the seeded positions;
- the user can move from empty database to Notion-visible MVP output with a short documented sequence.

## Future Extensions

This design intentionally leaves room for later additions without requiring rewrite:

- multiple demo accounts;
- more symbols across US, Europe, and UK UCITS ETFs;
- richer instrument metadata such as exchange, listing currency, or region;
- an authenticated admin trigger if a UI-based seed action becomes useful later.
