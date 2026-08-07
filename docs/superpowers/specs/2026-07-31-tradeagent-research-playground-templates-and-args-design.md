# Spec: Skill-Specific Research Reports and Configurable Skill Args

## Overview

Upgrade PAMASTER's Research Playground from raw metric tables into deterministic, skill-specific research reports with Plotly charts and narrative explanations. Start with `technical`, `worth-buy-stocks`, and `markov-method`; all other skills keep the current generic metrics/raw JSON template as a fallback.

## Architecture

- **TradeAgent** owns computation, sanitized report JSON, and typed skill parameter schemas.
- **PAMASTER** owns web/iPhone presentation templates, deterministic narratives, and Plotly charts.
- Browser/iPhone talks only to PAMASTER; PAMASTER proxies to TradeAgent.

### Repos

| Repo | Path |
|---|---|
| PAMASTER | `/Users/chenkangan/Documents/PAMASTER` |
| TradeAgent | `/Users/chenkangan/Documents/TradeAgent` |

### Implementation order

TradeAgent first (typed args), then PAMASTER (controls + templates).

---

## Part 1 — TradeAgent: Typed Skill Parameters

### 1.1 New file: `src/trade_research/skills/parameters.py`

Pydantic models for each skill's valid parameter set:

```python
from pydantic import BaseModel, Field, field_validator

class TechnicalSkillParameters(BaseModel):
    window: int = Field(default=20, ge=2, le=252)

class WorthBuyStocksParameters(BaseModel):
    # Accepts comma-separated string (UI-friendly); validated into a tuple for the dataclass field.
    benchmark_symbols: str = Field(default="AUTO", min_length=1)

    @field_validator("benchmark_symbols")
    @classmethod
    def _parse_to_tuple(cls, v: str) -> str:
        # Normalise and validate, but keep as str — configure_skill() splits into tuple.
        symbols = [s.strip().upper() for s in v.split(",") if s.strip()]
        if not symbols:
            raise ValueError("benchmark_symbols must contain at least one symbol")
        return ",".join(symbols)

    def as_tuple(self) -> tuple[str, ...]:
        return tuple(self.benchmark_symbols.split(","))

class MarkovMethodParameters(BaseModel):
    window: int = Field(default=20, ge=2, le=252)
    threshold: float = Field(default=0.05, gt=0, le=1.0)
    min_train: int = Field(default=252, ge=50, le=2520)
    run_walkforward: bool = False
```

### 1.2 Parameter schema lookup

A module-level constant mapping skill name to its JSON Schema (generated from the Pydantic model):

```python
SKILL_PARAMETER_SCHEMAS: dict[str, dict[str, object]] = {
    "technical": TechnicalSkillParameters.model_json_schema(),
    "worth-buy-stocks": WorthBuyStocksParameters.model_json_schema(),
    "markov-method": MarkovMethodParameters.model_json_schema(),
}
```

Used by `/skills` and `/skills/{name}` to advertise parameter contracts without instantiating models.

### 1.3 Configure skill helper

In `application.py`, a `configure_skill()` function that:

1. Looks up the skill by name from the frozen registry.
2. Validates parameters with the appropriate Pydantic model.
3. Returns a per-run copy via `dataclasses.replace()`.
4. Raises `ValueError` if a skill receives non-empty `params` but doesn't accept parameters.

```python
from dataclasses import replace
from trade_research.skills.parameters import (
    TechnicalSkillParameters,
    WorthBuyStocksParameters,
    MarkovMethodParameters,
)

def configure_skill(skill: ResearchSkill, params: dict[str, object]) -> ResearchSkill:
    if skill.name == "technical":
        validated = TechnicalSkillParameters.model_validate(params)
        return replace(skill, window=validated.window)

    if skill.name == "worth-buy-stocks":
        validated = WorthBuyStocksParameters.model_validate(params)
        return replace(skill, benchmark_symbols=validated.as_tuple())

    if skill.name == "markov-method":
        validated = MarkovMethodParameters.model_validate(params)
        return replace(
            skill,
            window=validated.window,
            threshold=validated.threshold,
            min_train=validated.min_train,
            run_walkforward=validated.run_walkforward,
        )

    if params:
        raise ValueError(f"Skill '{skill.name}' does not accept parameters")
    return skill
```

### 1.4 Changes to existing TradeAgent files

| File | Change |
|---|---|
| `domain/models.py` | Add `skill_parameters: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)` to `AnalysisRequest` |
| `application.py:describe_skill()` | Include `parameters` key from `SKILL_PARAMETER_SCHEMAS` in the returned dict (or `None` for skills without params) |
| `application.py:run_skill()` | Look up base skill, call `configure_skill()`, then execute the configured copy **directly through a new engine helper** (see Implementation Note below) |
| `engine.py` | **New** `run_configured_skill(skill, request)` method — runs a single pre-configured skill without rediscovering from the frozen registry. Or alternatively, modify `run_skill()` in `application.py` to bypass `self.research()` and directly instantiate/run the configured skill |
| `skills/__init__.py` | Export parameter models and schemas |

**Implementation Note — Engine bypass:** The current `ResearchApplication.run_skill()` delegates to `self.research(selected)`, which calls `engine.analyze()`, which rediscovers skills from the frozen registry. A naive call to `self.research()` would discard the configured copy and run the default skill. The implementation must either:

- (Recommended) Add a `run_configured_skill(skill: ResearchSkill, request: AnalysisRequest)` method to `ResearchEngine` that validates providers for the skill's capabilities, then runs `skill.analyze(instrument, providers)` directly — bypassing the registry lookup.
- (Alternative) Construct a temporary one-skill `SkillRegistry` containing only the configured copy, and add an `analyze_with_skills(request, skills)` overload to the engine.

Either approach keeps `ResearchSkill.analyze(instrument, providers)` stable.

### 1.5 TradeAgent tests

- `GET /skills` includes `parameters` field for `technical`, `worth-buy-stocks`, `markov-method`; `null`/absent for `fundamental` and `filings`.
- `GET /skills/technical` returns `parameters` with `window` schema.
- `POST /skills/technical/run` with `skill_parameters: {"technical": {"window": 10}}` succeeds; output method window labels reflect a 10-observation base.
- `POST /skills/markov-method/run` with all four custom parameters validates and runs.
- Invalid args (e.g., `window: 0`, `threshold: 2.0`) return `422` without stack traces.
- Non-parameterized skill receiving non-empty params returns `422`.
- Existing TradeAgent tests still pass.

---

## Part 2 — PAMASTER: Proxy Args + Dynamic Controls

### 2.1 Schema changes (`api/schemas.py`)

**`ResearchSkillResponse`** — add `parameters` field:
```python
class ResearchSkillResponse(BaseModel):
    name: str
    description: str
    immutable: bool = True
    parameters: dict | None = None
```

**`ResearchRunRequest`** — add `skill_parameters` field:
```python
class ResearchRunRequest(BaseModel):
    account_id: str | None = None
    instrument_id: str | None = None
    symbol: str | None = None
    market: str | None = None
    skills: list[str]
    skill_parameters: dict[str, dict[str, Any]] = {}
```

### 2.2 Route changes (`api/routes.py`)

**`GET /analysis/research/skills`:**
- Forward `parameters` from TradeAgent's skill descriptions into `ResearchSkillResponse.parameters`.
- TradeAgent-disabled path stays identical (no `parameters` to forward).

**`POST /analysis/research/run`:**
- Read `skill_parameters` from the request body.
- Pass it to `client.run_skill(skill, symbol, market, position, skill_parameters=...)`.

### 2.3 TradeAgent client (`research/trade_agent.py`)

**`run_skill()` method:**
- Add `skill_parameters: dict[str, dict[str, Any]] | None = None` parameter.
- When provided, include `"skill_parameters": skill_parameters` in the request body.

### 2.4 Dynamic controls UI (`analytics_app/pages.py`)

When a skill checkbox is checked, reveal its parameter inputs below it (indented). Control types:

| JSON Schema type | HTML input | Attributes |
|---|---|---|
| `integer` | `<input type="number" step="1">` | `min`, `max` from schema |
| `number` (float) | `<input type="number" step="0.01">` | `min`, `max` from schema |
| `boolean` | `<input type="checkbox">` | — |
| `string` | `<input type="text">` | — |

Default values pre-filled from the parameter schema. Controls are rendered client-side from the skill's `parameters.properties`.

### 2.5 Data flow

```
Browser                         PAMASTER                        TradeAgent
  │                                │                                │
  │ GET /analysis/research/skills  │                                │
  │───────────────────────────────>│ GET /skills                    │
  │                                │───────────────────────────────>│
  │                                │ skills[] with parameters defs  │
  │ skills[] with parameters defs  │<───────────────────────────────│
  │<───────────────────────────────│                                │
  │                                │                                │
  │ User checks "technical"        │                                │
  │ → window input [20] appears    │                                │
  │ User changes window to 10      │                                │
  │                                │                                │
  │ POST /analysis/research/run    │                                │
  │  skills: ["technical"]         │                                │
  │  skill_parameters: {           │                                │
  │    "technical": {"window": 10} │                                │
  │  }                             │                                │
  │───────────────────────────────>│ POST /skills/technical/run     │
  │                                │───────────────────────────────>│
  │                                │ report JSON                    │
  │                                │<───────────────────────────────│
  │ report JSON                    │                                │
  │<───────────────────────────────│                                │
```

---

## Part 3 — PAMASTER: Deterministic Report Templates

### 3.1 Layout

Tabbed mini-dashboard replacing the current single-results-area layout.

**Desktop/tablet (≥900px):**
```
Results area
├── Skill tabs: [Technical] [Worth Buy Stocks] [Markov Method]
├── Active panel header: skill name · status badge · signal chip
├── 2-column grid:
│   ├── Left (1.1fr): Narrative sections
│   └── Right (0.9fr, min 320px): Plotly charts + reference level cards
└── <details> Raw JSON
```

**Mobile (<900px):** Same tabs, single-column stacked (narrative first, charts below).

### 3.2 Template registry (client-side JS)

A JS object keyed by `analyst` name:

```javascript
const REPORT_TEMPLATES = {
    "technical": renderTechnicalReport,
    "worth-buy-stocks": renderWorthBuyReport,
    "markov-method": renderMarkovReport,
    "_fallback": renderGenericReport,
};
```

Choose template by `result.analyst`; fall back to `_fallback` for unknown analysts.

### 3.3 Chart constraints

- Charts consume sanitized TradeAgent report JSON only.
- Scalar observation charts should use `report.results[].observations[]`.
- Skills may optionally return a bounded `presentation` payload when the presentation needs richer
  deterministic evidence such as price bars, score components, risk checks, or benchmark coverage.
- The browser must not fetch prices, recalculate indicators, or infer missing metrics.
- Plotly chart types should stay compact and audit-friendly: bars, bounded candlesticks, gauges,
  probability bars, and reference-level cards.
- Plotly 2.35.2 loaded from CDN (same version as Position Chart page).

### 3.4 Technical template

**Narrative sections (left column):**
1. **Summary** — one to three sentences: analyst verdict, signal, completeness.
2. **Trend** — SMA, EMA, price return interpretation.
3. **Momentum** — RSI, MACD, momentum_10 interpretation.
4. **Risk Range** — ATR, Bollinger Bands, annualized volatility interpretation.
5. **Volume/Data Quality** — volume trend, missing metrics, limitations.

**Visuals (right column):**
- **Indicator bar chart** — horizontal bars for: return %, RSI (0-100), MACD histogram, volatility %, volume trend %. Each bar color-coded (green = constructive, red = caution, gray = neutral).
- **Mini-cards** — SMA value, ATR value, Bollinger width.

**Missing data handling:** If OHLCV is incomplete, ATR/Bollinger sections show "insufficient OHLCV data" rather than plotting zeros.

### 3.5 Worth-buy-stocks template

**Narrative sections (left column):**
1. **Setup Quality** — verdict translation using verdict language table from `EXPLANATION.md`.
2. **Composite Score** — composite trend-quality interpretation.
3. **Risk Veto** — risk penalty explanation.
4. **Entry Class** — translated from numeric code 0-5 using the entry class map.
5. **Reference Levels** — entry, stop, target with explicit disclaimer: "model reference levels, not order instructions."

**Visuals (right column):**
- **Price structure chart** — bounded candlestick/volume chart from
  `presentation.price_bars`, with entry/stop/target horizontal reference lines.
- **Evidence score bars** — momentum, relative strength, and trend-efficiency scores from
  `presentation.score_components`.
- **Reference level cards** — three compact cards: entry price, stop reference, target reference.
- **Benchmark coverage chips** — labels and resolved benchmark instruments from
  `presentation.benchmarks`.
- **Fallback** — if `presentation` is absent, use the older scalar composite/risk/reference
  template and show a restart/upgrade hint.

**Entry class translation table (JS):**
```javascript
const ENTRY_CLASS_LABELS = {
    0: "Trend Broken",
    1: "Overextended",
    2: "Pullback Without Trigger",
    3: "Trend Continuation",
    4: "Pullback Reversal",
    5: "Recovery Reversal",
};
```

### 3.6 Markov-method template

**Narrative sections (left column):**
1. **Regime Bias** — current regime code translated to Bear/Sideways/Bull.
2. **Signal** — `markov_signal` explained as bull-minus-bear next-step probability.
3. **Stationary Mix** — long-run regime distribution interpretation.
4. **Persistence** — regime stickiness from transition matrix.
5. **Data Quality** — partial status warnings, training bar sufficiency.

**Visuals (right column):**
- **Stationary probability bar chart** — three bars (Bull, Sideways, Bear) showing long-run probabilities, color-coded (green/yellow/red).
- **Persistence metric bars** — compact horizontal bars for each regime's persistence.
- **Signal gauge** — directional bias indicator centered at zero.

**Regime code translation table (JS):**
```javascript
const REGIME_LABELS = {
    0: "Bear",
    1: "Sideways",
    2: "Bull",
};
```

### 3.7 Fallback template

For `fundamental`, `filings`, and any future un-templated skills:
- Current metric table (Skill, Metric, Value, Source columns).
- Status, signal, limitations displayed prominently.
- Collapsible raw JSON.
- Same tab structure — no functional regression.

### 3.8 Plotly CDN

Add to the research page `<head>`:
```html
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
```
(Same version as Position Chart page at `pages.py:1058`.)

---

## Test Plan

### TradeAgent tests

| # | Test | Expected |
|---|---|---|
| 1 | `/skills` includes `parameters` for technical, worth-buy-stocks, markov-method | `parameters` is a JSON Schema dict with `properties` |
| 2 | `/skills/fundamental` returns `parameters: null` | No parameter schema |
| 3 | Run `technical` with `window=10` | Succeeds; method window labels reference 10-observation base |
| 4 | Run `markov-method` with custom `window`, `threshold`, `min_train`, `run_walkforward` | All params validated and applied |
| 5 | `window=0` → 422 | Validation error, no stack trace |
| 6 | `threshold=2.0` → 422 | Validation error |
| 7 | Non-param skill with non-empty params → 422 | ValueError mapped to 422 |
| 8 | Existing TradeAgent tests still pass | No regressions |

### PAMASTER tests

| # | Test | Expected |
|---|---|---|
| 1 | Skills endpoint returns `parameters` for proxied skills | Matches TradeAgent schema |
| 2 | Run endpoint sends `skill_parameters` in request body to TradeAgent | Body includes `skill_parameters` key |
| 3 | Research page includes Plotly CDN script tag | `<script src="...plotly-2.35.2...">` |
| 4 | Research page renders dynamic parameter controls per skill | Number input for `window`, checkbox for `run_walkforward`, etc. |
| 5 | Template renders `technical` result with narrative + charts | Narrative sections present; Plotly chart divs populated |
| 6 | Template renders `worth-buy-stocks` result with gauge + reference cards | Gauge chart, reference cards, entry class label |
| 7 | Template renders `markov-method` result with probability bars | Three-bar chart, persistence bars, regime label |
| 8 | Fallback template for `fundamental` renders generic table | Table with metric/value rows |
| 9 | Error state when TradeAgent disabled | "TradeAgent is not configured" message |
| 10 | Error state when TradeAgent unreachable | "TradeAgent is unreachable" message |
| 11 | Auth boundary: browser never receives TradeAgent token | No token in any HTML/JS payload |
| 12 | Manual research mode (no position) works with templates | Symbol/market inputs work; templates render without position context |

### Manual acceptance

- Refresh `/analysis/research`; skill checkboxes appear with configurable options.
- Run `technical` on AAPL and see narrative plus charted technical factors, not only metric rows.
- Run `worth-buy-stocks` and see verdict, composite, risk veto, entry class, and reference levels.
- Run `markov-method` and see regime explanation plus stationary/persistence visuals.
- Select "Manual research / no current position", enter a symbol/market, and run the same templates without portfolio context.

---

## Non-Goals (for this slice)

- Time-series charts (no `chart_data` arrays, no price-series fetching, no provenance reconstruction)
- Fundamental and filings templates (use fallback)
- Queued `/research` mode parameterization (synchronous only)
- TradeAgent `ConfigurableSkill` protocol (defer to v2)
- Multi-skill comparison view (one analyst per tab)

---

## Files Changed

### TradeAgent

| File | Action |
|---|---|
| `src/trade_research/skills/parameters.py` | **New** — Pydantic parameter models + schema lookup |
| `src/trade_research/domain/models.py` | Edit — add `skill_parameters` to `AnalysisRequest` |
| `src/trade_research/application.py` | Edit — `describe_skill()` includes params; `configure_skill()` helper; `run_skill()` uses configured copy via engine bypass |
| `src/trade_research/engine.py` | Edit — new `run_configured_skill()` method (see Implementation Note above) |
| `src/trade_research/http.py` | Edit — catch `ValueError` from `configure_skill()` (and `ValidationError` from Pydantic) in the `/skills/{name}/run` route, mapping both to HTTP 422 with a sanitized detail message. Currently the route only catches `ProviderConfigurationError` (503) and `KeyError` (404). |
| `src/trade_research/skills/__init__.py` | Edit — export parameter models |
| `tests/` (various) | **New** + Edit — parameter validation tests |

### PAMASTER

| File | Action |
|---|---|
| `backend/src/pa_investing/api/schemas.py` | Edit — add `parameters` to `ResearchSkillResponse`; add `skill_parameters` to `ResearchRunRequest` |
| `backend/src/pa_investing/api/routes.py` | Edit — forward parameters in skills endpoint; pass `skill_parameters` in run endpoint |
| `backend/src/pa_investing/research/trade_agent.py` | Edit — `run_skill()` accepts and forwards `skill_parameters` |
| `backend/src/pa_investing/analytics_app/pages.py` | Edit — Plotly CDN; dynamic parameter controls; template registry; tabbed mini-dashboard layout; technical, worth-buy-stocks, markov-method, and fallback renderers |
| `backend/tests/integration/test_api_routes.py` | Edit — research endpoint tests for parameters and templates |
| `backend/tests/unit/test_trade_agent.py` | Edit — client tests for `skill_parameters` forwarding |
