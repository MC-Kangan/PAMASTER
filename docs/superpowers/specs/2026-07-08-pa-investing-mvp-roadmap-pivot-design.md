# PA Investing MVP Roadmap Pivot Design

Date: 2026-07-08

## Purpose

Record a roadmap change without replacing the original architecture design.

The original design in [2026-07-07-pa-investing-system-architecture-design.md](/Users/chenkangan/Documents/PAMASTER/docs/superpowers/specs/2026-07-07-pa-investing-system-architecture-design.md) remains the long-term system direction. This addendum changes execution order so the next implementation focus is a visible end-to-end MVP: real Notion integration plus one live market price API.

The reason for the pivot is practical. The Phase 1 backend foundation is strong, but it is still hard to visualize the final workflow without seeing real data move through Notion and a live API connection. The next step should therefore optimize for a tangible operating loop before adding agent orchestration.

## What Stays The Same

The following architectural decisions are unchanged:

- Notion is the first UI adapter and mobile-friendly command center.
- PostgreSQL remains the structured source of truth.
- Python remains the long-term backend and analytics core.
- The system does not place trades or submit broker orders.
- Deterministic sizing and rule-based logic remain outside future LLM or agent discretion.
- The analytics app remains a linked deeper-analysis surface rather than the first priority.
- Agent workflows remain part of the long-term architecture.

This is a sequencing change, not a rewrite of the system vision.

## Why The Roadmap Changes

The original roadmap placed agent orchestration immediately after the Phase 1 foundation. That still makes sense technically, but it is not the best next move for product feedback.

The immediate uncertainty is not whether the system can support agents later. The immediate uncertainty is whether the daily workflow feels real and useful:

- can the backend push structured outputs into a real Notion workspace;
- can a live price provider refresh holdings and metrics without manual CSV-only steps;
- can the user open Notion and see current signals, metrics, and review outputs with minimal friction.

These questions should be answered before adding more abstraction around LLM or multi-agent behavior.

## New Near-Term Roadmap

### Phase 2A: Live Notion Integration MVP

Build the first real Notion-connected operating surface:

- replace fake-only Notion client usage with a live Notion client implementation behind the same interface;
- add settings for Notion database identifiers and integration toggles;
- define concrete database mapping for the first synced records, starting with `Signals`, `Daily Review`, and selected portfolio summary data;
- support idempotent upsert behavior so reruns update existing records rather than duplicating them;
- expose one or more backend-triggered sync flows that can write current results into the real Notion workspace;
- preserve fake Notion client support for tests.

Success criterion: a real Notion workspace can display backend-generated signals and daily review output from current persisted data.

### Phase 2B: Live Market Price API MVP

Add one live delayed/free market data provider through the existing market-data interface:

- provider-swappable market data client;
- credentials and configuration stored in backend settings, not in Notion;
- support common equity, ETF, and crypto spot price lookup where feasible for the chosen provider;
- graceful fallback and sync status when provider data is unavailable;
- persistence of refreshed prices through the existing price repository flow.

Success criterion: backend price refresh no longer depends only on manual CSV input, and updated prices flow into metrics and signals.

### Phase 2C: End-To-End Daily Operating Loop

Join the pieces into a workflow that is easy to understand and demo:

- import or load current positions;
- refresh latest prices from the live provider;
- compute updated portfolio metrics and rule-based signals;
- persist results;
- sync the user-facing results into Notion;
- keep analytics links available for deeper drilldown.

Success criterion: the user can refresh portfolio state and see the result reflected in Notion without manual editing inside Notion itself.

## Deferred Work

The following work is intentionally deferred, not removed:

- `explain_signal` agent endpoint;
- agent supervisor runtime;
- tool permission model for agents;
- prompt and tool-call audit trails for LLM workflows;
- compact retrieval for LLM cost control;
- specialist agents such as technical, macro, thesis, and risk agents.

These items move behind the MVP operating loop. They should be resumed once the system already has a visible, trusted, real-data workflow.

## MVP Boundaries

The MVP should stay intentionally narrow.

Included:

- real Notion sync for a limited set of databases and fields;
- one live market price provider;
- visible sync status and failure handling;
- end-to-end refresh flow using existing persisted portfolio and signal data.

Excluded:

- broker read-only live connectors;
- multi-provider market routing;
- Obsidian retrieval;
- LLM or agent explanations;
- interactive chart expansion beyond the Phase 1 analytics placeholders;
- notifications beyond Notion.

## Design Constraints For The Pivoted Phase

- Do not overwrite or invalidate the original architecture document.
- Do not force Notion to become the source of truth.
- Do not store provider secrets or raw credential material in Notion.
- Do not couple market data logic directly to Notion page-writing logic.
- Do not add trade execution features.
- Keep live integrations behind interfaces so fake/test providers remain available.
- Favor idempotent sync behavior and explicit sync status fields.

## Recommended Implementation Order

1. Build the live Notion client and database configuration layer.
2. Add a real price provider implementation through the existing market data interface.
3. Add one backend workflow that refreshes prices, recalculates outputs, and syncs Notion.
4. Add a small API or manual trigger surface to run the workflow on demand.
5. Return to agent-oriented Phase 2 work only after the MVP loop is visible and trusted.

## Success Criteria

This roadmap pivot is successful when:

- the user can connect a real Notion workspace;
- the backend can fetch live delayed/free prices from one provider;
- the daily portfolio state can be refreshed end to end;
- Notion reflects portfolio signals and review output generated by the backend;
- the codebase remains modular enough to add agents later without replacing the live integration work.

## Relationship To The Original Roadmap

The original roadmap remains historically correct as the first architecture pass.

This addendum changes only priority:

- old Phase 2 agent work becomes a later follow-on phase;
- the new immediate priority is a live integration MVP;
- later agent work should reuse the same backend truth, Notion sync surfaces, and market data interfaces built here.
