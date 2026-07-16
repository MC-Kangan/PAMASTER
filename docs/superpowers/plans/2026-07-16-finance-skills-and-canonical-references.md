# Finance Skills and Canonical References Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Bloomberg-style canonical instrument references and a reusable deterministic finance-skill runner backed by the existing historical-data library.

**Architecture:** Instrument references such as `ADBE US` are parsed through a small market-code registry and remain separate from provider symbols. Finance skills consume an accepted `HistoricalDataset`, return typed evidence, and are composed by a deterministic registry/orchestrator with failure isolation.

**Tech Stack:** Python 3.13, Pydantic, pandas, pytest, Ruff

## Global Constraints

- Support listed equities and ETFs only in v1.
- Canonical references use `SYMBOL MARKET`, such as `ADBE US` and `GLEN LN`.
- Yahoo remains the default historical provider; skills never fetch provider data directly.
- Use adjusted completed daily bars.
- Default lookback is 12 months and may be overridden by the request.
- Skills return evidence and review findings, never PA trading signals.
- Summaries are deterministic.
- New skills must be registerable without changing the orchestrator.
- One skill failure produces a partial run and does not stop other skills.

---

### Task 1: Canonical Instrument References

**Files:**
- Create: `backend/src/pa_investing/instruments/market_codes.py`
- Modify: `backend/src/pa_investing/instruments/resolution.py`
- Test: `backend/tests/unit/test_market_codes.py`
- Test: `backend/tests/unit/test_instrument_resolution.py`

**Interfaces:**
- Produces: `CanonicalInstrumentReference.parse(value: str)`
- Produces: `MarketCodeRegistry.market_for_exchange(exchange: str | None)`
- Produces: `InstrumentCandidate.canonical_reference`
- Consumes: existing provider search candidates

- [ ] Write tests that normalize `adbe u.s.` to `ADBE US`, reject unknown market codes, and render `GLEN LN`.
- [ ] Run the focused tests and confirm they fail because the parser does not exist.
- [ ] Implement the immutable market registry and canonical-reference parser.
- [ ] Update research resolution so `SYMBOL MARKET` filters candidates by canonical market while preserving existing exact-exchange input compatibility.
- [ ] Run focused instrument tests and commit.

### Task 2: Typed Finance Skill Contract and Registry

**Files:**
- Create: `backend/src/pa_investing/finance/__init__.py`
- Create: `backend/src/pa_investing/finance/models.py`
- Create: `backend/src/pa_investing/finance/registry.py`
- Create: `backend/src/pa_investing/finance/orchestrator.py`
- Test: `backend/tests/unit/test_finance_orchestrator.py`

**Interfaces:**
- Produces: `FinanceSkill.run(request, dataset) -> SkillResult`
- Produces: `SkillRegistry.register(skill)` and `SkillRegistry.register_bundle(name, skill_ids)`
- Produces: `FinanceOrchestrator.run(request, dataset) -> AnalysisResult`
- Consumes: `HistoricalDataset`

- [ ] Write tests for bundle expansion, duplicate registration, isolated exceptions, partial status, explicit skill selection, and deterministic summary output.
- [ ] Run the focused test and confirm imports fail.
- [ ] Implement the smallest typed result envelope, protocol, registry, and deterministic orchestrator.
- [ ] Run focused tests and commit.

### Task 3: Daily Market Review Skills

**Files:**
- Create: `backend/src/pa_investing/finance/indicators.py`
- Create: `backend/src/pa_investing/finance/skills/__init__.py`
- Create: `backend/src/pa_investing/finance/skills/technical.py`
- Create: `backend/src/pa_investing/finance/skills/candlestick.py`
- Create: `backend/src/pa_investing/finance/skills/market_risk.py`
- Create: `backend/src/pa_investing/finance/defaults.py`
- Test: `backend/tests/unit/test_finance_skills.py`

**Interfaces:**
- Produces: `technical_snapshot.v1`
- Produces: `candlestick_events.v1`
- Produces: `market_risk_snapshot.v1`
- Produces: `build_default_finance_registry()`
- Consumes: adjusted daily `HistoricalDataset.bars`

- [ ] Write synthetic-series tests for trend, RSI, candlestick events, drawdown, volatility, five-session candlestick surfacing, and insufficient-history partial results.
- [ ] Run focused tests and confirm the skills are absent.
- [ ] Implement pure indicator helpers and the three deterministic skills.
- [ ] Register `daily_market_review.v1`.
- [ ] Run focused tests and commit.

### Task 4: Verification and Documentation

**Files:**
- Modify: `README.md`

**Interfaces:**
- Documents: canonical references, finance-skill extension contract, and default bundle

- [ ] Add concise usage examples showing `ADBE US`, provider translation, explicit skills, and `daily_market_review.v1`.
- [ ] Run Ruff over source and tests.
- [ ] Run the complete pytest suite.
- [ ] Review the diff for accidental coupling to providers or PA signals.
- [ ] Commit the verified feature.

