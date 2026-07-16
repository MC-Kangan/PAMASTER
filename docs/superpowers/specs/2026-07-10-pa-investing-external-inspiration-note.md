# PA Investing External Inspiration Note

Date: 2026-07-10

## Purpose

Capture a small set of external open-source references that are genuinely relevant to the long-term direction of this project.

This note is not a roadmap or implementation plan. It is a short reference so that future design work can reuse good ideas intentionally instead of reinventing everything from scratch.

## Most Relevant References

### 1. Ghostfolio

Repo:

- [ghostfolio/ghostfolio](https://github.com/ghostfolio/ghostfolio)

Why it matters:

- this is the closest public reference to the likely final product shape;
- it is focused on personal wealth and portfolio management;
- it supports stocks, ETFs, and crypto;
- it is self-hosted;
- it is designed for continuous use;
- it has a real web-app product surface rather than a notebook or toy dashboard.

What to learn from it:

- product shape for the eventual browser app;
- responsive mobile-and-desktop design expectations;
- authentication as a first-class application concern;
- portfolio-performance and charting UX;
- account and holdings workflow patterns;
- self-hosted deployment expectations.

How it should influence this project:

- the long-term browser app should feel closer to Ghostfolio than to a data science app;
- the system should continue moving toward a proper authenticated web app with responsive design;
- deeper analytics should live in the browser app, while Notion remains the quick summary surface.

#### Follow-up Review: 2026-07-16

Ghostfolio has continued to mature and now provides more concrete patterns worth considering. The
current repository uses a PostgreSQL-backed activity ledger, separate account-balance history,
asset profiles and overrides, multiple portfolio calculator strategies, modular static risk rules,
provider health checks, rate limiting, JWT/API-key authentication, and optional OIDC. It remains a
mobile-first PWA and supports stocks, ETFs, crypto, cash-like liquidity, liabilities, fees,
interest, and dividends.

Useful source references:

- [Ghostfolio repository and self-hosting guide](https://github.com/ghostfolio/ghostfolio)
- [Database schema](https://github.com/ghostfolio/ghostfolio/blob/main/prisma/schema.prisma)
- [Portfolio calculators](https://github.com/ghostfolio/ghostfolio/tree/main/apps/api/src/app/portfolio/calculator)
- [Static portfolio rules](https://github.com/ghostfolio/ghostfolio/tree/main/apps/api/src/models/rules)
- [Data-provider interface](https://github.com/ghostfolio/ghostfolio/blob/main/apps/api/src/services/data-provider/interfaces/data-provider.interface.ts)
- [Import workflow](https://github.com/ghostfolio/ghostfolio/blob/main/apps/api/src/app/import/import.service.ts)

Patterns to adopt:

| Pattern | PA Investing application |
| --- | --- |
| Transaction/activity ledger | Add normalized buys, sells, dividends, fees, interest, transfers, and cash adjustments. Use this as the durable accounting history while broker positions remain a reconciled current view. |
| Separate account-balance history | Keep broker-reported account NAV/cash snapshots separate from calculated holdings so discrepancies can be measured rather than hidden. |
| Multiple return calculators | Implement TWR and MWR as independent analytics strategies with fixture-heavy tests. Do not overload the current simple snapshot return. |
| Asset profile plus user overrides | Extend instrument metadata with optional sectors, countries, ETF look-through holdings, themes, and user overrides without making equity-specific identifiers mandatory. |
| Static modular risk rules | Keep each concentration, currency, account, drawdown, and stop/reference rule as a small deterministic module producing explainable signals. |
| Dry-run import and duplicate detection | Validate broker/transaction imports before persistence, show warnings, and make repeated imports idempotent. |
| Benchmark abstraction | Allow the user to choose portfolio benchmarks and compare returns over standard periods. |
| Provider health and freshness | Record last success, latency, stale-data status, and failure details for IBKR, Coinbase, market-data, FX, Notion, and future LLM providers. |
| Mobile-first PWA | When the custom frontend becomes the primary UI, make it installable and phone-first instead of creating separate desktop and mobile applications. |
| Layered authentication | Keep Tailscale plus HTTPS for the private MVP, then support OIDC/MFA, rotatable API tokens, login throttling, and correct reverse-proxy configuration if access expands. |

Patterns to defer:

- Redis and background queues until provider traffic or job duration makes them necessary;
- multi-user roles, portfolio sharing, subscriptions, and public portfolio links;
- a large frontend monorepo while Notion remains the main operating surface;
- broad asset discovery and watchlist functionality before the real-portfolio accounting loop is
  reliable.

Recommended order of adoption:

1. Transaction and cash-flow ledger.
2. Reconciliation between broker NAV, positions, cash, and calculated totals.
3. TWR/MWR and previous-day P&L adjusted for external cash flows.
4. Provider health/run-status dashboard.
5. Benchmark comparison and modular concentration-risk rules.
6. PWA frontend and OIDC only when the custom browser application becomes the primary interface.

Licensing note:

Ghostfolio is licensed under AGPLv3. Architecture and product ideas can inform this project, but
source code should not be copied into the repository unless an explicit licensing decision is made.
For now, reuse concepts and independently implement the small pieces that fit.

### 2. OpenBB

Repo:

- [OpenBB-finance/OpenBB](https://github.com/OpenBB-finance/OpenBB)

Why it matters:

- it is a strong reference for the backend and data-platform side of the system;
- it shows how a finance data layer can serve many consumers;
- it is relevant to the project’s future use of scripts, APIs, analytics, and agent-style workflows.

What to learn from it:

- provider-adapter design for market and research data;
- API-first and platform-style internal architecture;
- separation between data access, analytics logic, and end-user surface;
- reusability of backend outputs across multiple interfaces.

How it should influence this project:

- the backend should continue becoming the single internal finance data and analytics service;
- Notion, browser UI, scripts, and future agents should all consume the same backend truth;
- when useful, we can reuse ideas or implementation patterns from OpenBB’s adapter and platform approach.

## Lower-Priority References

### Rotki

Repo:

- [rotki/rotki](https://github.com/rotki/rotki)

Why it is less central:

- strong on privacy and self-hosting philosophy;
- more relevant to crypto-heavy portfolio/accounting workflows than to the current target product.

Still useful for:

- privacy-first design instincts;
- local-control and self-hosted operating model.

### FinGPT

Repo:

- [AI4Finance-Foundation/FinGPT](https://github.com/AI4Finance-Foundation/FinGPT)

Why it is less central:

- more relevant to future AI and research workflows than to the current MVP app shape;
- less relevant than Ghostfolio or OpenBB for the immediate product and platform architecture.

Still useful for:

- future agent and finance-LLM workflow ideas;
- data-centric thinking for later AI layers.

## Working Conclusion

The strongest external direction for this project is:

- Ghostfolio for the eventual product and UX direction;
- OpenBB for the backend data-platform direction.

This fits the current architecture well:

- PostgreSQL as source of truth;
- Python backend as analytics and workflow layer;
- Notion as summary surface;
- browser app as deeper analytics surface;
- future AI capabilities built on top of a stable data and analytics foundation.

## Reuse Principle

When future design work reaches areas that look similar to these projects, we should explicitly check whether we can reuse:

- architecture ideas;
- workflow patterns;
- interface patterns;
- data-adapter patterns;
- implementation approaches;
- or, where licenses and technical fit allow, parts of code structure or logic.

The goal is not to copy blindly. The goal is to learn from mature open-source work and selectively reuse what fits this project.
