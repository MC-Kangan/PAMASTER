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
- a mobile-capable browser analytics view for performance history;
- a lightweight authentication layer for the browser app;
- scheduled portfolio snapshot creation at fixed times;
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

## Browser App Technology Direction

The browser analytics surface should support both desktop and smartphone usage.

Because of that requirement, this slice should not assume Streamlit as the primary app framework. I could not find current official Streamlit documentation that gives a strong mobile-first or built-in authentication direction, so the safer design assumption is:

- keep the backend/API as the stable core;
- keep Notion as the quick summary layer;
- evolve the browser analytics surface with a responsive web UI that is designed explicitly for phone and desktop layouts.

This does not rule Streamlit out forever, but it should not be the default assumption for the performance-history MVP.

## Output Surfaces

The output model for this slice is:

- Notion remains the summary surface;
- the browser analytics app becomes the deeper drilldown surface on both phone and desktop;
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

## Snapshot Cadence

The performance history should not depend only on ad hoc manual refreshes.

This slice should support a scheduled snapshot cadence at four fixed times per day:

- `00:00`
- `06:00`
- `12:00`
- `18:00`

For the MVP, these should be treated as local deployment times, with timezone configured at the application or host level. Since your environment is personal and likely anchored to one deployment location, this is a consistent and understandable starting rule.

The schedule exists to ensure there is dependable history even when the user is not manually running the app.

This does not require full job-orchestration sophistication yet. It only requires the architecture to treat scheduled snapshots as a first-class input into performance history.

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

The history API should work for both:

- manually triggered snapshots from the refresh workflow;
- scheduled snapshots created at the fixed cadence above.

## API Surface

Add a new analysis endpoint, likely:

- `GET /analysis/performance`

The backend may also need a small scheduled-snapshot trigger path later, but that is secondary to the performance read path for this MVP.

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

The page does not need a polished dashboard shell yet. It does need to be clearly usable on:

- desktop browser widths;
- smartphone browser widths.

That means the charts and summary cards should stack cleanly on small screens rather than assuming a desktop-only layout.

## Authentication

The browser analytics surface should include an authentication layer.

For the MVP, the auth requirement is primarily for the browser app, not for Notion itself.

Recommended auth stance:

- browser app: protected behind a simple login or session-based access control;
- Notion integration: continue using a trusted personal token or internal connection model for now;
- no public multi-user OAuth for the browser app in this slice.

This is the right boundary for a personal system:

- the browser app may be reachable over your NAS or another hosted surface and therefore should not be left open;
- Notion does not need a separate end-user auth flow when it is being written by your backend as a trusted personal integration.

If the system later becomes multi-user or shareable, the auth model can be expanded. For now, simple authenticated access is enough.

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

For auth:

- unauthenticated browser-app requests should be denied cleanly;
- backend-only scheduled snapshot jobs should not rely on an interactive login flow.

## Testing

Add focused coverage for:

- performance series calculation from multiple snapshots;
- correct running peak and drawdown behavior;
- correct simple return behavior;
- empty-history handling;
- API response shape for the performance endpoint;
- browser page route smoke coverage if the app page is added through the existing server-side HTML path;
- authentication gating for the browser surface;
- scheduled snapshot behavior at fixed cadence boundaries where scheduling logic is introduced.

Tests should remain deterministic and should not depend on live Notion or price APIs.

## Success Criteria

This slice is successful when:

- multiple refresh runs produce a visible history in the browser app;
- scheduled snapshots can produce consistent history points even without manual refreshes;
- the backend can return NAV, unrealized PnL, simple return, and max drawdown over a selected window;
- the browser analytics page can render a useful performance view from persisted snapshots on desktop and smartphone screens;
- the browser app is not publicly open without authentication;
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
