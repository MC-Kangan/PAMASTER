# PA Investing Extensible Schema Design

Date: 2026-07-13

## Purpose

The first Notion-connected MVP should stay flexible as the portfolio workflow grows.

The current implementation proves the operating loop:

- build portfolio snapshots;
- calculate signals and daily review outputs;
- persist results;
- sync selected fields into Notion;
- expose performance history through the browser app.

The next schema decision is how to avoid hard-coding every future Notion column, analytics field, and chart metric. The user wants to be able to add or remove optional Notion columns over time without breaking the backend, while still keeping enough structure for reliable portfolio calculations.

## Design Decision

Use a simple hybrid schema:

- stable core fields for financial identity, ordering, and required calculations;
- explicit MVP performance fields for the metrics already needed;
- schema-aware Notion syncing that writes only compatible properties that exist in the target database;
- browser charts driven by metric definitions rather than fixed field names.

This keeps the system flexible where flexibility is useful, while preserving strictness where financial calculations require it. For the first implementation, flexibility should focus on the Notion adapter and display mapping, not on building a full dynamic metrics storage system.

## Alternatives Considered

### Option 1: Simple Hybrid Core Plus Flexible Notion Mapping

This is the recommended approach.

The backend keeps explicit fields for the current portfolio and performance calculations. A small registry describes how those fields should be displayed and mapped to Notion. Notion receives only the fields that exist in the Notion database and match a supported type. Unknown Notion columns are left untouched.

Benefits:

- reliable calculations for NAV, time ordering, and portfolio identity;
- Notion columns can be added or removed without breaking sync;
- frontend charts can use a field registry for labels, formats, and chart eligibility;
- implementation remains small enough for the MVP.

Tradeoff:

- adding a genuinely new backend calculation still requires code;
- dynamic persisted metrics are deferred until there is a concrete use case.

### Option 2: Hybrid Core Plus Persisted Dynamic Metrics

The backend keeps stable core fields and stores expandable metrics as typed key-value data.

Benefits:

- optional metrics can be stored without a database migration every time;
- useful later for script-generated metrics and agent outputs;
- API consumers can discover metrics more generically.

Tradeoff:

- heavier than needed for the first MVP;
- requires metric typing, persistence, validation, migration, and presentation rules up front;
- increases the chance of building infrastructure before the workflow proves which metrics matter.

### Option 3: Fully Relational Hard-Coded Fields

Every snapshot field and Notion column becomes an explicit backend model field.

Benefits:

- easiest to query;
- strong database-level typing;
- simple to reason about for a small fixed product.

Tradeoff:

- poor fit for a growing personal analytics system;
- every new metric or optional display column needs code and often a migration;
- removing or renaming Notion columns is more likely to break the sync flow.

### Option 4: Fully Schemaless JSON

All snapshot and analytics fields are treated as free-form JSON.

Benefits:

- maximum flexibility;
- minimal schema migrations;
- easy to ingest arbitrary output from scripts or future agents.

Tradeoff:

- too weak for financial correctness;
- harder to validate required inputs;
- harder to build reliable charts, filters, and portfolio-level aggregations;
- mistakes in field names or units can silently corrupt outputs.

## Stable Core

Some fields should remain stable because other parts of the system depend on them.

For portfolio snapshots, the required core is:

- `snapshot_id`
- `observed_at`
- portfolio or account scope
- `reporting_currency`
- `nav`

For the current MVP, these existing fields should remain first-class persisted fields:

- `gross_exposure`
- `net_exposure`
- `unrealized_pnl`

They are common enough to deserve direct support, but they should also be exposed through the same field presentation layer used by the browser app and Notion sync.

For positions, the required core should stay focused on:

- source account or broker identifier;
- canonical instrument identifier;
- quantity;
- native currency;
- cost and price inputs where available.

Fields such as sector, region, asset class, strategy, and investment theme can be labels or metadata. They should be easy to extend later, but they should not replace canonical instrument identity.

## MVP Performance Fields

The first MVP should keep the performance fields explicit because they are already known and directly useful.

Examples:

```json
{
  "observed_at": "2026-07-04T12:00:00Z",
  "nav": "100000",
  "unrealized_pnl": "2000",
  "peak_nav": "100000",
  "drawdown": "0",
  "simple_return": "0"
}
```

These fields should be backed by a display registry rather than hard-coded throughout every UI and Notion path. The registry can define:

- backend key;
- display label;
- value type;
- display format;
- optional Notion property name;
- chart eligibility;
- default visibility;
- display order.

This avoids a large dynamic metric system while still avoiding scattered display logic.

## Future Dynamic Metrics

Dynamic metrics should be deferred until there is a real source of variable metrics, such as:

- user-added analytics scripts;
- custom factor or signal modules;
- broker-specific metrics;
- future agent-generated outputs.

When that need appears, optional analytics fields can be represented as typed metrics.

Future metric types should include:

- decimal;
- integer;
- text;
- boolean;
- date;
- url.

Each future metric should have a stable key, display label, value type, display format, optional unit, and provenance where useful. Provenance can later record the calculator module and version that produced the metric.

## Storage Direction

The MVP should keep the existing relational snapshot columns for the stable core.

No persisted dynamic metrics payload is required for the first implementation.

A JSON-compatible metrics payload can be added later. For local tests and the current app this can work with SQLite. For the NAS or production deployment this would map naturally to PostgreSQL `jsonb`.

A fully normalized metric table is not required until querying arbitrary metrics across long history becomes important.

## API Contract

The performance API should stay explicit for the first MVP while exposing enough metadata for flexible display.

Recommended response shape:

```json
{
  "summary": {
    "start_observed_at": "2026-07-04T00:00:00Z",
    "end_observed_at": "2026-07-04T12:00:00Z",
    "starting_nav": "98000",
    "ending_nav": "100000",
    "simple_return": "0.0204081633",
    "max_drawdown": "0"
  },
  "points": [
    {
      "observed_at": "2026-07-04T12:00:00Z",
      "nav": "100000",
      "unrealized_pnl": "2000",
      "peak_nav": "100000",
      "drawdown": "0",
      "simple_return": "0"
    }
  ]
}
```

The API may add a separate field metadata endpoint or embed a compact metadata block later. The first implementation does not need to move performance values into a nested `metrics` object.

## Notion Sync Behavior

Notion should be treated as a flexible presentation and operating surface, not the source of truth for calculations.

The Notion adapter should:

- inspect or cache the target database schema before writing;
- map backend field keys to Notion property names through configuration or a small registry;
- write only properties that exist in the target Notion database;
- skip missing optional properties with a structured warning;
- leave unknown Notion columns untouched;
- fail clearly if required identity fields are missing.

Required Notion sync fields for upsert behavior:

- title or name property;
- `External ID` or equivalent stable upsert key.

Optional fields such as `NAV`, `Unrealized PnL`, `Peak NAV`, `Drawdown`, and `Simple Return` should be written only when present and type-compatible.

If the user adds a manual Notion-only column, the backend should ignore it. If the user removes an optional backend-managed column, the sync should skip it. If the user renames a backend-managed column, the mapping must be updated unless the implementation uses stable Notion property IDs.

## Notion Metadata Boundary

For the first MVP, custom Notion columns should be Notion-only metadata unless explicitly mapped.

Examples:

- personal review status;
- manual notes;
- tags;
- workflow labels;
- ad hoc comments.

These should not be imported back into backend calculations yet. This avoids accidental use of manually edited fields as financial inputs.

A later phase can add bidirectional metadata import once there is a clear use case and validation model.

## Browser App Behavior

The browser app should not hard-code every field card and chart label.

It should consume field definitions that include:

- key;
- label;
- value type;
- display format;
- chart eligibility;
- default visibility;
- display order.

The first browser view can still show a curated default set:

- NAV;
- unrealized PnL;
- simple return;
- max drawdown;
- peak NAV;
- drawdown.

Unknown numeric metrics can later appear in a generic selector after dynamic metrics exist. Non-numeric fields should be displayed in tables or detail panels rather than charts.

## Validation Rules

Validation should be strict for core fields and tolerant for optional display fields.

Strict failures:

- missing `snapshot_id`;
- missing or invalid `observed_at`;
- missing `nav`;
- invalid currency code where a currency is required;
- missing Notion upsert identity field.

Tolerant warnings:

- optional display field missing;
- optional Notion property missing;
- optional Notion property type mismatch;
- unknown field key;
- unknown Notion column.

This distinction is important. The backend should not fail because the user experiments with extra Notion columns, but it should fail when core financial inputs are invalid.

## Error Handling And Audit

The Notion sync path should record skipped or mismatched fields in logs or audit records.

Recommended events:

- property skipped because it does not exist;
- property skipped because Notion type is incompatible;
- required property missing;
- unknown backend field ignored by the current Notion mapping.

For API responses, missing optional fields should appear as absent values rather than server errors.

## Testing

Add tests for:

- performance payload includes stable core fields and explicit MVP performance fields;
- Notion sync skips missing optional properties;
- Notion sync leaves unknown/manual Notion columns untouched;
- Notion sync fails clearly when the upsert identity property is missing;
- browser formatting handles decimal percentages without overflow on mobile-sized layouts;
- chart data builders are driven by the display registry rather than scattered hard-coded labels.

Tests should remain deterministic and should not depend on live Notion, live broker APIs, or live market data.

## Out Of Scope

This design does not add:

- broker read integration;
- agent orchestration;
- bidirectional import of arbitrary Notion metadata;
- user-defined formula execution;
- a normalized metrics warehouse;
- a full chart builder UI.

## Success Criteria

This design is successful when:

- the user can add or remove optional Notion columns without breaking sync;
- the backend keeps reliable core fields for calculations;
- performance points expose fields such as `peak_nav`, `drawdown`, and `simple_return` clearly;
- Notion flexibility is handled by schema-aware syncing rather than full dynamic storage;
- the browser app can render the current curated metrics and remain ready for additional metrics later;
- financial calculations stay rule-based and auditable.
