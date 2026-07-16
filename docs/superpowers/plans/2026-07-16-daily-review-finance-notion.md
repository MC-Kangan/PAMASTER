# Daily Review Finance Evidence and Notion Rounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add portfolio finance evidence to the PA daily review and make every numeric value written to the Notion portfolio dashboard use deliberate display precision.

**Architecture:** `DailyReviewWorkflow` will optionally call the reusable `FinanceAnalysisService` once per unique supported portfolio instrument and attach evidence-only results to `DailyReviewResult`; failures remain visible but do not stop valuation, signals, or Notion sync. `NotionSync` will render a Market Analysis section and apply field-specific rounding at its serialization boundary, preserving full precision in domain calculations and persistence.

**Tech Stack:** Python 3.13, Pydantic, SQLAlchemy, pytest, Notion API payload models.

## Global Constraints

- Finance analysis remains evidence and must not create or modify PA signals.
- Default analysis bundle is `daily_market_review.v1` with a 365-day lookback.
- Only equity and ETF holdings with an `instrument_id` are analyzed.
- One failed instrument analysis must not prevent the daily review from completing.
- Backend calculation precision remains unchanged; rounding occurs only in Notion payloads and body formatting.
- Money and percentage displays use two decimal places; quantities and prices use four; FX rates use six.

---

### Task 1: Daily-review finance evidence

**Files:**
- Modify: `backend/src/pa_investing/workflows/agent_api.py`
- Modify: `backend/src/pa_investing/workflows/daily_review.py`
- Test: `backend/tests/integration/test_daily_review_workflow.py`

**Interfaces:**
- Consumes: `FinanceAnalysisService.analyze_portfolio(instrument_id, as_of=..., lookback_days=365, bundle="daily_market_review.v1")`.
- Produces: `DailyReviewResult.finance_evidence: list[FinanceEvidence]`, where each item records symbol, instrument ID, result or isolated error.

- [x] **Step 1: Write failing tests for supported-instrument analysis, deduplication, cash skipping, and failure isolation.**
- [x] **Step 2: Run the focused workflow tests and confirm the new assertions fail because finance evidence is absent.**
- [x] **Step 3: Add the evidence model, optional analyzer protocol, and deterministic per-instrument workflow pass.**
- [x] **Step 4: Run the focused workflow tests and confirm they pass.**
- [x] **Step 5: Commit the workflow integration.**

### Task 2: Clear Notion rendering and complete numeric rounding

**Files:**
- Modify: `backend/src/pa_investing/notion/sync.py`
- Test: `backend/tests/unit/test_notion_sync.py`

**Interfaces:**
- Consumes: `DailyReviewResult.finance_evidence`.
- Produces: rounded Notion number properties and a deterministic `Market Analysis` body section containing provenance, completion date, status, summaries, and per-instrument errors.

- [x] **Step 1: Write failing payload tests using deliberately over-precise account, holding, coverage, weight, price, FX, and daily-change values.**
- [x] **Step 2: Write a failing daily-review body test for successful and unavailable finance evidence.**
- [x] **Step 3: Run the focused Notion tests and confirm failures expose unrounded properties and the missing section.**
- [x] **Step 4: Add named field-precision helpers and apply them to every numeric Notion property and numeric portfolio body line.**
- [x] **Step 5: Add deterministic Market Analysis rendering without signal language.**
- [x] **Step 6: Run the focused Notion tests and confirm they pass.**
- [x] **Step 7: Commit the Notion presentation changes.**

### Task 3: Runtime composition and end-to-end verification

**Files:**
- Modify: `backend/src/pa_investing/core/dependencies.py`
- Test: `backend/tests/integration/test_refresh_and_sync_workflow.py`

**Interfaces:**
- Consumes: the existing instrument resolver, historical-data router, Yahoo and Twelve Data providers, and default finance registry.
- Produces: the production refresh-and-sync workflow with finance analysis injected into `DailyReviewWorkflow`.

- [x] **Step 1: Write a failing composition or refresh test proving finance evidence reaches the synced daily-review page.**
- [x] **Step 2: Run the focused test and confirm it fails before runtime wiring.**
- [x] **Step 3: Build and inject `FinanceAnalysisService` from the existing database session and provider stack.**
- [x] **Step 4: Run focused workflow and Notion tests.**
- [x] **Step 5: Run the complete pytest suite and Ruff.**
- [x] **Step 6: Review the diff for scope, secrets, and accidental changes, then commit.**
