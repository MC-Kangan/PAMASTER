# PA Investing System Architecture Design

Date: 2026-07-07

## Purpose

Design a growing personal-account investing workflow for low-frequency PA investing. The system should help collect information, maintain investment theses, monitor portfolio risk, generate rule-based signals, summarize knowledge with LLMs, and support future analytics scripts without forcing a full custom app from day one.

The chosen architecture is Notion-first:

- Notion is the command center and simple frontend.
- Python agents and services are the compute layer.
- PostgreSQL is the structured source of truth.
- A lightweight analytics app provides interactive charts and deeper analysis when Notion is insufficient.
- Obsidian remains the durable long-form knowledge vault.

The system does not trade or place broker orders.

## Architecture Summary

```text
Notion workspace
  Command center, mobile capture, watchlists, theses, signals, daily review
        |
        | Notion API, webhooks, scheduled sync
        v
Python backend and agents
  Broker import, prices, portfolio metrics, risk rules, sizing, LLM workflows
        |
        v
PostgreSQL
  Accounts, positions, prices, snapshots, signals, audit logs
        |
        v
Analytics app
  Streamlit or Plotly Dash pages for interactive charts and drilldowns
        |
        v
Obsidian vault
  Long-form evergreen knowledge, book notes, playbooks, technical guides
```

Notion is the human operating surface. Python and PostgreSQL own numerical truth, security-sensitive data, and repeatable analytics. The analytics app is linked or embedded from Notion for richer charts. Obsidian is used for durable markdown knowledge that should remain portable and easy to version or re-index later.

## Why Not A Full Custom App First

A full React or mobile app would provide maximum UX control and richer interactive dashboards, but it would front-load frontend, authentication, deployment, and mobile support work. That effort would slow down the more valuable early work: broker import, price sync, risk logic, signal generation, LLM summarization, and thesis workflow.

The Notion-first architecture is a known low-code-plus-backend pattern:

```text
Low-code workspace
        +
custom backend and agents
        +
real database
```

This is common with tools such as Notion, Airtable, Retool, internal dashboards, and automation platforms. The important boundary is that Notion is not treated as the analytical database or charting engine.

## Notion Responsibilities

Notion should stay simple, mobile-friendly, and glanceable.

Recommended databases:

- `PA Dashboard`: home page with linked views and key metric summaries.
- `Accounts`: broker/source, currency, latest NAV, cash, last sync, status.
- `Holdings`: account, symbol, asset class, quantity, average cost, market value, unrealized PnL, thesis link, risk bucket, holding-period metadata.
- `Watchlist`: symbol, asset class, sector/theme, target entry, stop/reference level, thesis status, alert rules, priority.
- `Signals`: symbol, signal type, trigger source, severity, status, deterministic recommendation, LLM explanation, analytics link, audit id.
- `Theses`: asset/company, business model, valuation, macro, technicals, risks, invalidation criteria, holding-period rules.
- `Notes Inbox`: pasted articles, social posts, quick comments, source URL, tags, linked symbols, processing status.
- `Daily Review`: generated summary, portfolio changes, triggered signals, reviewed actions, follow-up tasks.

Notion should display:

- key portfolio metrics;
- open signals;
- watchlist alerts;
- thesis status;
- daily review summaries;
- links to interactive analytics pages.

Notion should not store:

- broker secrets;
- LLM API keys;
- raw credential material;
- the only copy of portfolio history;
- large price-history tables;
- backtest result datasets.

## Python Backend Responsibilities

The backend should be a Python modular monolith. It can be deployed as several Docker Compose services while sharing one codebase.

```text
backend/
  core/              settings, logging, database, auth, time/calendar helpers
  notion/            Notion API client, database mappers, page writers
  portfolio/         accounts, positions, transactions, NAV snapshots, PnL
  market_data/       delayed/free prices, historical prices, provider interface
  brokers/           CSV importer first, Coinbase connector, IBKR connector later
  analytics/         risk metrics, Sharpe, drawdown, exposures, backtests
  signals/           entry, stop loss, rebalance, watchlist alerts
  sizing/            deterministic sizing models and risk-budget rules
  llm/               provider abstraction for OpenAI, Anthropic, DeepSeek, GLM, etc.
  knowledge/         Obsidian/Notion indexing, retrieval, source citations
  workflows/         daily review, signal generation, summaries, orchestration
  audit/             immutable logs of inputs, rules, prompts, model outputs
```

The backend exposes:

- a small FastAPI API for health checks, Notion webhooks, and analytics links;
- scheduled jobs for price sync, portfolio snapshots, signal generation, and Notion updates;
- background workers for LLM summarization and knowledge indexing;
- reusable Python modules for analytics and future research scripts.

## PostgreSQL Responsibilities

PostgreSQL is the structured source of truth for numerical and auditable data.

Core entities:

- accounts;
- instruments;
- positions;
- transactions or imported lots;
- portfolio snapshots;
- price observations;
- watchlist rules;
- generated signals;
- sizing recommendations;
- LLM summaries;
- audit events.

Notion records should contain references to database ids where needed. If Notion content is edited or deleted, historical portfolio and signal data remains preserved in PostgreSQL.

## Analytics App Responsibilities

Notion will not be forced to render complex analytics. For interactive charts and deeper analysis, use a linked analytics app.

Recommended first implementation:

- Streamlit or Plotly Dash, because both are Python-native and fast for analytics-heavy workflows.

Examples:

- portfolio NAV and PnL history;
- drawdowns;
- exposure by asset class, sector, theme, and currency;
- position drilldown;
- signal details;
- price chart with entry/stop levels;
- backtest result pages;
- scenario and sizing calculators.

Notion rows can link to pages such as:

```text
https://your-domain/analysis/signal/<signal_id>
https://your-domain/analysis/position/<position_id>
https://your-domain/analysis/portfolio
```

The analytics app can later be replaced by a custom React frontend if richer UX becomes necessary. It should read from PostgreSQL or backend APIs so the replacement does not disturb analytics logic.

## Broker And Market Data Strategy

First phase:

- CSV/manual portfolio import;
- free, delayed, or end-of-day price data;
- explicit provider interfaces for future replacement.

Later:

- Coinbase read-only connector;
- Interactive Brokers read-only connector;
- optional paid or broker-provided market data if required.

Design interfaces:

```text
BrokerConnector
  list_accounts()
  fetch_positions()
  fetch_transactions()
  fetch_balances()

MarketDataProvider
  get_latest_price(symbol)
  get_price_history(symbol, start, end)
```

The application must not request trading permissions or place trades.

## Signal And Sizing Policy

The system is signal-oriented.

Rules and analytics produce signals such as:

- entry level triggered;
- stop/reference level triggered;
- risk budget exceeded;
- concentration too high;
- stale thesis review needed;
- holding-period or PA compliance reminder;
- watchlist condition met.

Position sizing must be deterministic and auditable. The LLM may explain or challenge a recommendation, but it must not invent numeric sizing.

Allowed:

```text
Sizing engine recommends selling 10 shares because the position exceeds the configured 8% NAV risk bucket.
LLM explains the signal, cites thesis risks, and asks whether the original invalidation criterion still holds.
```

Not allowed:

```text
LLM independently decides to sell 10 shares without a sizing or risk method producing that number.
```

## Knowledge And LLM Flow

Captured information should be summarized before regular LLM use to control token cost.

```text
Raw note / URL / pasted text
        |
        v
Ingestion processor
  source, symbols, asset class, topic, date, author
        |
        v
Compact summary
  5-10 bullets, key claims, uncertainty, relevance
        |
        v
Linked knowledge
  Notion thesis links, watchlist links, optional Obsidian note/index
```

Store:

- raw source or excerpt, where useful for auditability and reprocessing;
- compact summary for normal LLM workflows;
- source URL or citation;
- linked symbols and topics;
- processing status.

LLM context strategy:

1. Include current portfolio and signal facts from PostgreSQL.
2. Include deterministic risk and sizing outputs.
3. Use compact summaries first.
4. Retrieve raw/full text only when explicitly needed.
5. Require citations to Notion, Obsidian, or original URLs.
6. Store prompt inputs, model, and output in audit logs.

LLM provider interface:

```text
LLMProvider
  summarize_note()
  classify_capture()
  explain_signal()
  challenge_thesis()
  generate_daily_review()
```

The provider should be configurable so OpenAI, Anthropic, DeepSeek, GLM, or later models can be swapped without rewriting workflows.

## Obsidian Role

Obsidian is the deeper knowledge library, not the daily command center.

Use Obsidian for:

- evergreen principles;
- value-investing notes;
- book summaries;
- technical trading guides;
- personal playbooks;
- post-trade lessons;
- durable markdown that should remain portable.

Notion can link to Obsidian-derived summaries or indexed knowledge. The Python knowledge layer can read Obsidian markdown and build a retrieval index for LLM workflows.

## Deployment

Initial deployment target is the uGREEN NAS using Docker Compose.

```text
docker-compose
  postgres
  backend-api
  worker
  analytics-app
```

Access model:

- Notion remains cloud-hosted.
- Backend runs privately on NAS.
- Analytics app starts as LAN/VPN-only.
- If Notion webhooks are needed, expose only the webhook endpoint via Cloudflare Tunnel, Tailscale Funnel, a reverse proxy, or a small cloud bridge.
- Secrets live in backend environment variables or secret files, not in Notion.

## Error Handling And Auditability

Failures should be visible at the right level:

- Notion shows user-facing status, such as `Sync failed: price provider unavailable`.
- Backend logs contain stack traces and detailed diagnostics.
- Audit records preserve input data, rule versions, sizing outputs, LLM prompt metadata, and generated summaries.

Every generated signal should have:

- timestamp;
- data snapshot id;
- rule or model that triggered it;
- deterministic sizing output, if any;
- LLM model and prompt references, if used;
- Notion page id;
- analytics link.

## Testing Strategy

Test coverage should focus on deterministic and boundary-sensitive behavior:

- unit tests for analytics, sizing, signal rules, and market data normalization;
- unit tests for Notion database mappers;
- integration tests with fake Notion and fake broker clients;
- regression fixtures for portfolio imports and generated signals;
- no tests requiring live broker credentials by default;
- optional live integration tests gated by environment variables.

## First Vertical Slice

The first implementation should prove the whole architecture without building everything.

Deliver:

1. Notion database schema specification.
2. Python backend skeleton.
3. PostgreSQL schema and migrations.
4. CSV/manual import for positions.
5. Free/delayed price provider.
6. Basic NAV, PnL, exposure, and risk metrics.
7. Rule-based signal generation.
8. Deterministic sizing interface with one simple model.
9. Notion sync for accounts, holdings, signals, and daily review.
10. Minimal analytics app with linked portfolio and signal pages.
11. Optional LLM summarization interface for notes, initially configurable or mockable.

## Later Phases

Potential growth path:

1. Coinbase read-only connector.
2. Interactive Brokers read-only connector.
3. Obsidian indexing and retrieval.
4. LLM thesis challenge workflow.
5. Backtesting module.
6. More advanced risk and sizing models.
7. Notification channels beyond Notion.
8. Richer analytics app or custom React frontend if Streamlit/Dash becomes limiting.
9. Optional self-hosted automation layer such as n8n for glue workflows.

## Explicit Non-Goals

- No order placement.
- No day-trading or high-frequency workflows.
- No storing secrets in Notion.
- No treating Notion as the only source of portfolio truth.
- No full custom app in phase 1.
- No formal plugin system in phase 1; use explicit Python interfaces first.

## Sources Checked

- Notion API overview: https://developers.notion.com/guides/get-started/overview
- Notion webhooks: https://developers.notion.com/reference/webhooks
- Notion API request limits: https://developers.notion.com/reference/request-limits
- Notion embeds: https://www.notion.com/help/embed-and-connect-other-apps
- Notion charts: https://www.notion.com/help/charts
- Coinbase Advanced Trade API: https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/rest-api
- Interactive Brokers Client Portal API: https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/
- IBKR market data pricing: https://www.interactivebrokers.com/en/pricing/market-data-pricing.php

