# PA Investing Performance History MVP Design

Date: 2026-07-10

## Purpose

Define the next MVP slice after the Notion-connected refresh loop: a deeper analytics surface for portfolio performance and history.

The current system can already:

- persist portfolio snapshots in PostgreSQL;
- refresh prices and recompute portfolio state;
- expose a minimal analytics surface;
- sync summary outputs into Notion.

What is still missing is a useful historical view. The user needs to inspect how portfolio value and unrealized PnL evolve across refresh runs, with a deeper browser-based analysis surface while keeping Notion as the quick summary layer.

## Scope

This slice adds:

- snapshot-based performance history analytics;
- backend endpoints for chart-ready time-series data;
- a browser analytics view for performance history;
- a compact summary path that can later feed Notion.

This slice does not add:

- broker read integration;
- realized PnL accounting;
- benchmark comparison;
- transaction-aware return decomposition;
- sector or region exposure analysis;
- notifications or new agent behavior.

## Recommended Approach

Three approaches were considered:

1. snapshot-based performance history
2. dedicated performance ledger
3. compute-on-read only without a stable history model

The recommended approach is `snapshot-based performance history`.

It is the best fit for the MVP because:

- portfolio snapshots already exist in the data model;
- it avoids inventing a second historical storage system too early;
- it supports useful charts quickly;
- it stays aligned with the current refresh workflow.

## Output Surfaces

The output model for this slice is:

- Notion remains the summary surface;
- the browser analytics app becomes the deeper drilldown surface;
- backend/API becomes the single data contract for both.

This preserves the operating pattern already chosen for the overall product:

- glance in Notion;
- investigate in the browser app.

## Core MVP Capability

The primary capability of this slice is `portfolio performance and history`.

For the first MVP, that means:

- NAV history over time;
- unrealized PnL history over time;
- running peak NAV;
- drawdown from peak NAV;
- simple return over the selected window.

These metrics are enough to make the browser app meaningfully useful without requiring full portfolio accounting.

## Data Source

The historical source for this slice is the existing `portfolio_snapshots` table.

Each refresh run already persists:

- `observed_at`
- `nav`
- `gross_exposure`
- `net_exposure`
- `unrealized_pnl`

This slice will read ordered snapshots and build performance series from them.

No separate historical storage layer is needed for the MVP.

## Analytics Model

The backend should expose a small performance-history service that accepts an ordered list of snapshots and produces a chart-ready series.

Each point should include at minimum:

- timestamp
- nav
- unrealized_pnl
- peak_nav
- drawdown
- simple_return

Definitions for MVP:

- `peak_nav`: highest NAV observed from the start of the selected window through the current point
- `drawdown`: `(nav - peak_nav) / peak_nav`
- `simple_return`: `(nav / first_nav) - 1`

If fewer than two snapshots exist, the service should still return a valid series with zero drawdown at the first point and zero simple return at the base point.

## Time Window And Query Model

The MVP should support a simple windowing model from the API layer, for example:

- default: full available history
- optional filters such as `days=30`, `days=90`, `days=365`

This keeps the API compact while giving enough control for charts.

The first version does not need pagination, benchmark overlays, or highly customized interval aggregation.

## API Surface

Add a new analysis endpoint, likely:

- `GET /analysis/performance`

Recommended response shape:

- summary block
- ordered points array

Example fields:

- `start_observed_at`
- `end_observed_at`
- `starting_nav`
- `ending_nav`
- `simple_return`
- `max_drawdown`
- `points`

Each point should be JSON-safe and chart-ready, with decimal values serialized consistently as strings or numbers using the project’s established approach.

## Browser Analytics View

The browser app should gain a deeper portfolio performance page driven by the new endpoint.

The first version should display:

- a NAV history chart;
- an unrealized PnL history chart or series;
- summary figures for ending NAV, window return, and max drawdown.

The page does not need a polished dashboard shell yet. It only needs to be clearly usable and consistent with the current lightweight analytics app.

## Relationship To Notion

Notion should not attempt to become the charting surface.

For this slice:

- the browser app is responsible for interactive history inspection;
- Notion can remain focused on compact, high-signal summaries;
- any later Notion summary should consume the same backend-calculated performance summary values rather than reimplementing logic.

This keeps charts where charts belong and avoids forcing rich time-series exploration into a document database UI.

## Error Handling

The performance endpoint should fail gracefully when:

- there are no snapshots yet;
- the window filter returns no matching rows;
- malformed query values are provided.

Recommended MVP behavior:

- return an empty series plus a clear summary state when no history exists;
- return validation errors for malformed query values;
- avoid treating missing history as a server error.

## Testing

Add focused coverage for:

- performance series calculation from multiple snapshots;
- correct running peak and drawdown behavior;
- correct simple return behavior;
- empty-history handling;
- API response shape for the performance endpoint;
- browser page route smoke coverage if the app page is added through the existing server-side HTML path.

Tests should remain deterministic and should not depend on live Notion or price APIs.

## Success Criteria

This slice is successful when:

- multiple refresh runs produce a visible history in the browser app;
- the backend can return NAV, unrealized PnL, simple return, and max drawdown over a selected window;
- the browser analytics page can render a useful performance view from persisted snapshots;
- Notion remains the lightweight summary surface while the browser app becomes the deeper inspection surface.

## Future Extensions

This design leaves room for later additions without requiring a new foundation:

- benchmark-relative performance;
- realized and total return accounting;
- contribution by position;
- rolling volatility and Sharpe-style statistics;
- richer time-window controls;
- compact Notion summary fields sourced from the same performance service;
- broker-fed real account history once live broker reads are added.
