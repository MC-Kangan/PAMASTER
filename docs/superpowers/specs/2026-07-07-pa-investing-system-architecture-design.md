# PA Investing System Architecture Design

Date: 2026-07-07

## Purpose

Design a growing personal-account investing workflow for low-frequency PA investing. The system should help collect information, maintain investment theses, monitor portfolio risk, generate rule-based signals, summarize knowledge with LLMs, and support future analytics scripts without forcing a full custom app from day one.

The chosen architecture is agent-backend-first, with Notion as the first user interface:

- Notion is the initial command center and simple frontend.
- Python agents and services are the compute layer and long-term system core.
- PostgreSQL is the structured source of truth.
- A lightweight analytics app provides interactive charts and deeper analysis when Notion is insufficient.
- A future custom app can replace or reduce Notion when the workflow benefits from a more unified interface.
- Obsidian remains the durable long-form knowledge vault.

The system does not trade or place broker orders.

## Architecture Summary

```text
Frontend adapters
  Notion, future custom app, analytics cockpit, optional OpenClaw/chat interface
        |
        | API calls, webhooks, scheduled sync, deep links
        v
Python backend, agents, and deterministic tools
  Broker import, prices, portfolio metrics, risk rules, sizing, LLM workflows
        |
        v
PostgreSQL
  Accounts, positions, prices, snapshots, signals, audit logs
        |
        v
Knowledge sources
  Notion summaries, Obsidian vault, source URLs, broker/market data
        |
        v
Analytics app
  Interactive charts, portfolio drilldowns, signal details, backtests
```

Notion is the first human operating surface. Python and PostgreSQL own numerical truth, security-sensitive data, repeatable analytics, and agent orchestration. The analytics app is linked or embedded from Notion for richer charts. Obsidian is used for durable markdown knowledge that should remain portable and easy to version or re-index later.

The frontend can change over time. The core investment logic should not be trapped inside Notion, Lovable, Base44, Codex Sites, OpenClaw, or any other UI/runtime product.

## Why Not A Full Custom App First

A full React or mobile app would provide maximum UX control and richer interactive dashboards, but it would front-load frontend, authentication, deployment, and mobile support work. That effort would slow down the more valuable early work: broker import, price sync, risk logic, signal generation, LLM summarization, and thesis workflow.

The chosen architecture uses a known low-code-plus-backend pattern at the user-interface layer:

```text
Low-code workspace
        +
custom backend and agents
        +
real database
```

This is common with tools such as Notion, Airtable, Retool, internal dashboards, and automation platforms. The important boundary is that Notion is not treated as the analytical database, charting engine, or agent runtime. It is the first UI adapter.

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

The backend also owns the multi-agent orchestration layer. Specialist agents may be added over time, but they should call registered backend tools instead of reaching directly into broker APIs, databases, or the filesystem.

Recommended agent roles:

- `SupervisorAgent`: coordinates specialist outputs, resolves conflicts, and writes the final review.
- `TechnicalAnalysisAgent`: analyzes price history, indicators, trend state, and triggered technical rules.
- `PortfolioOptimisationAgent`: reviews holdings, risk budgets, exposures, covariance/volatility estimates, and sizing outputs.
- `MacroAgent`: summarizes macro context, rates/FX/commodity regimes, and macro-sensitive risks.
- `ThesisAgent`: compares new information against Notion theses and Obsidian knowledge.
- `RiskOfficerAgent`: checks stop rules, concentration, holding-period constraints, PA policy constraints, and audit requirements.

Agents must be treated as analysts, not traders. They can request deterministic tools, explain results, and write recommendations for review. They cannot place orders or invent sizing numbers without a sizing/risk tool result.

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

Possible implementations:

- Codex Sites or a custom app built in this repo, because this maximizes ownership and maintainability.
- Lovable, if fast polished app generation is more valuable than repo-first control for an early dashboard.
- Base44, if no-code workflow experiments, built-in app data, and automations are more valuable than code ownership.
- Streamlit or Plotly Dash, if Python-native speed matters more than product polish.

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

The analytics app should read from PostgreSQL or backend APIs so the UI implementation can change without disturbing analytics logic. The first version can be simple. Over time, this layer can become the all-in-one app if Notion becomes too fragmented.

Notion should link to or embed the analytics app rather than trying to become the charting platform.

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

## Agent Architecture

The long-term architecture should be backend-owned multi-agent orchestration with UI adapters.

```text
Frontend adapters
  Notion
  future custom app
  analytics dashboard
  optional OpenClaw/chat interface
        |
        v
Agent API
  run_daily_review()
  explain_signal()
  analyze_position()
  summarize_capture()
  challenge_thesis()
        |
        v
Agent orchestrator
  supervisor, specialist agents, permissions, run state, audit
        |
        v
Deterministic tools
  risk, sizing, backtest, optimization, market data, knowledge retrieval
        |
        v
PostgreSQL and knowledge index
```

This makes the frontend replaceable. Notion can be the first operating surface; a custom app can become the unified interface later; OpenClaw or another assistant can be added as a messaging interface without becoming the system of record.

OpenClaw is suitable as an optional command surface, not as the financial brain. A safe pattern is:

```text
OpenClaw/chat message
  "Run macro review for my PA portfolio"
        |
        v
Backend Agent API
  authenticated request with limited scope
        |
        v
Controlled backend workflow
  macro agent + risk officer + audit logs
        |
        v
Result written to Notion, analytics app, or chat
```

OpenClaw-style agents can have broad local access if misconfigured, so any integration must use narrow backend API endpoints, sandboxing, explicit permissions, and audit logs. The PA system should not expose broker credentials, database superuser access, or shell/filesystem access through an assistant interface.

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
10. Backend `Agent API` skeleton with one simple daily-review or signal-explanation workflow.
11. Minimal analytics link target for portfolio and signal pages.
12. Optional LLM summarization interface for notes, initially configurable or mockable.

## Phased Roadmap

The roadmap should keep the backend and data model ahead of the UI. Notion is the first frontend, not a permanent constraint.

### Phase 0: Architecture And Operating Principles

Deliver the design document, choose the first architecture, and define the non-negotiable boundaries:

- no order placement;
- read-only broker access;
- deterministic sizing and risk tools;
- agent outputs audited;
- Notion is a UI adapter;
- PostgreSQL is the source of truth;
- future app builders must call backend APIs instead of owning core logic.

### Phase 1: Notion Command Center And Backend Foundation

Build the first usable workflow:

- Notion databases for dashboard, accounts, holdings, watchlist, signals, theses, notes inbox, and daily review;
- Python backend skeleton;
- PostgreSQL schema and migrations;
- CSV/manual position import;
- free/delayed price provider;
- NAV, PnL, exposure, and basic risk metrics;
- simple rule-based signals;
- deterministic sizing interface with one conservative model;
- Notion sync for key metrics, holdings, signals, and daily review;
- LLM note summarization behind a provider interface.

Success criterion: the daily PA workflow can happen in Notion, with structured data and calculations owned by the backend.

### Phase 2: Agent Orchestration Foundation

Add the backend-owned agent layer:

- Agent API endpoints such as `run_daily_review`, `explain_signal`, `analyze_position`, and `summarize_capture`;
- supervisor workflow;
- tool permission model;
- audit logging for prompts, tool calls, retrieved context, and outputs;
- provider-swappable LLM interface;
- compact-summary retrieval to control token cost.

Success criterion: agents can explain and challenge signals using controlled tools without owning trade execution or sizing logic.

### Phase 3: Specialist Investment Agents

Add agents one by one:

- Technical Analysis Agent;
- Portfolio Optimisation Agent;
- Macro Agent;
- Thesis/Fundamental Agent;
- Risk Officer Agent.

Each agent must have a narrow tool list, test fixtures, and clear output schema. Numeric recommendations must cite deterministic tools.

Success criterion: multi-agent review produces a structured investment memo or signal explanation with disagreements and uncertainty visible.

### Phase 4: Interactive Analytics Cockpit

Add richer analysis pages linked from Notion:

- portfolio NAV and PnL charts;
- drawdown and risk charts;
- position drilldowns;
- signal-specific pages;
- price charts with entry/stop/reference levels;
- backtest result pages;
- scenario and sizing calculators.

Candidate implementation paths:

- Codex Sites or custom app for code ownership;
- Lovable for fast polished prototype;
- Base44 for no-code workflow experiments;
- Streamlit or Plotly Dash for Python-native speed.

Success criterion: Notion gives the overview, and one click opens deeper interactive analysis.

### Phase 5: Broker Connectors And Knowledge Expansion

Expand data inputs:

- Coinbase read-only connector;
- Interactive Brokers read-only connector;
- Obsidian indexing and retrieval;
- richer thesis challenge workflow;
- broader price/history provider support;
- optional notifications beyond Notion.

Success criterion: manual imports are no longer the only way to update portfolio state, and agents can cite both current data and durable knowledge.

### Phase 6: Optional Assistant And All-In-One App

Add convenience surfaces only after the backend is stable:

- OpenClaw or another assistant as a restricted messaging interface;
- n8n or another automation layer for glue workflows, if useful;
- custom all-in-one app if Notion plus linked analytics becomes too fragmented;
- React or another full frontend if app-builder prototypes become limiting.

Success criterion: the user can choose between Notion, app, and assistant surfaces without changing the core investment logic.

## Explicit Non-Goals

- No order placement.
- No day-trading or high-frequency workflows.
- No storing secrets in Notion.
- No treating Notion as the only source of portfolio truth.
- No full custom app in phase 1.
- No formal plugin system in phase 1; use explicit Python interfaces first.
- No letting an agent framework directly control broker credentials, shell access, or database admin access.

## Sources Checked

- Notion API overview: https://developers.notion.com/guides/get-started/overview
- Notion webhooks: https://developers.notion.com/reference/webhooks
- Notion API request limits: https://developers.notion.com/reference/request-limits
- Notion embeds: https://www.notion.com/help/embed-and-connect-other-apps
- Notion charts: https://www.notion.com/help/charts
- Coinbase Advanced Trade API: https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/rest-api
- Interactive Brokers Client Portal API: https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/
- IBKR market data pricing: https://www.interactivebrokers.com/en/pricing/market-data-pricing.php
- Lovable documentation: https://docs.lovable.dev/introduction/welcome
- Lovable integrations: https://docs.lovable.dev/integrations/introduction
- Base44 integrations: https://docs.base44.com/Integrations/Using-integrations
- Base44 custom integrations: https://docs.base44.com/documentation/integrations/using-custom-integrations
- Codex app documentation: https://developers.openai.com/codex/app
- Codex Sites: https://developers.openai.com/showcase/sites
- OpenClaw GitHub: https://github.com/openclaw/openclaw
