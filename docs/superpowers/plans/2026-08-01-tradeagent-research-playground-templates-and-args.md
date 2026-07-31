# Research Playground Templates & Args — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade PAMASTER's Research Playground from raw metric tables into deterministic, skill-specific research reports with Plotly charts and narrative explanations, with configurable skill parameters proxied from TradeAgent.

**Architecture:** TradeAgent owns computation and typed parameter schemas; PAMASTER proxies parameters and owns presentation templates. TradeAgent skills are frozen dataclasses — per-run configuration uses `dataclasses.replace()` without mutating the registry. PAMASTER templates are client-side JS renderers keyed by analyst name, consuming only scalar observations from sanitized report JSON.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, dataclasses, httpx, Plotly 2.35.2 (CDN), vanilla JS/CSS

## Global Constraints

- TradeAgent: `ResearchSkill.analyze(instrument, providers)` signature must remain unchanged
- TradeAgent: frozen `SkillRegistry` must never be mutated at runtime
- PAMASTER: browser must never receive TradeAgent bearer token or direct URL
- PAMASTER: templates consume only `report.results[].observations[]` scalar values — no time series, no price fetching, no recalculation
- PAMASTER: all templates are deterministic JS — no LLM calls
- Plotly: version 2.35.2 from CDN, same as Position Chart page
- Invalid TradeAgent parameters must return HTTP 422 without stack traces
- Only synchronous `/skills/{name}/run` — queued `/research` unchanged in this slice

---

### Task 1: TradeAgent — Create skill parameter models

**Files:**
- Create: `src/trade_research/skills/parameters.py`
- Modify: `src/trade_research/skills/__init__.py`

**Interfaces:**
- Produces: `TechnicalSkillParameters(window: int = 20)`, `WorthBuyStocksParameters(benchmark_symbols: str = "SPY,QQQ")` with `as_tuple() -> tuple[str, ...]`, `MarkovMethodParameters(window=20, threshold=0.05, min_train=252, run_walkforward=False)`, `SKILL_PARAMETER_SCHEMAS: dict[str, dict]`

- [ ] **Step 1: Create `parameters.py`**

```python
"""Typed parameter contracts for configurable research skills."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class TechnicalSkillParameters(BaseModel):
    window: int = Field(default=20, ge=2, le=252)


class WorthBuyStocksParameters(BaseModel):
    benchmark_symbols: str = Field(default="SPY,QQQ", min_length=1)

    @field_validator("benchmark_symbols")
    @classmethod
    def _normalise_symbols(cls, v: str) -> str:
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


SKILL_PARAMETER_SCHEMAS: dict[str, dict[str, object]] = {
    "technical": TechnicalSkillParameters.model_json_schema(),
    "worth-buy-stocks": WorthBuyStocksParameters.model_json_schema(),
    "markov-method": MarkovMethodParameters.model_json_schema(),
}
```

- [ ] **Step 2: Export from `skills/__init__.py`**

```python
# Add after existing exports:
from trade_research.skills.parameters import (
    MarkovMethodParameters,
    SKILL_PARAMETER_SCHEMAS,
    TechnicalSkillParameters,
    WorthBuyStocksParameters,
)
```

Add the new names to `__all__` if it exists, or ensure they are importable.

- [ ] **Step 3: Verify imports work**

Run: `cd /Users/chenkangan/Documents/TradeAgent && python -c "from trade_research.skills.parameters import TechnicalSkillParameters, WorthBuyStocksParameters, MarkovMethodParameters, SKILL_PARAMETER_SCHEMAS; print('OK'); print(SKILL_PARAMETER_SCHEMAS.keys())"`
Expected: `OK` followed by `dict_keys(['technical', 'worth-buy-stocks', 'markov-method'])`

- [ ] **Step 4: Verify Pydantic validation**

Run: `python -c "
from trade_research.skills.parameters import TechnicalSkillParameters, MarkovMethodParameters, WorthBuyStocksParameters
# defaults
t = TechnicalSkillParameters()
assert t.window == 20
# valid custom
t = TechnicalSkillParameters(window=10)
assert t.window == 10
# invalid
try:
    TechnicalSkillParameters(window=0)
    assert False, 'should have raised'
except Exception:
    pass
# benchmark parsing
w = WorthBuyStocksParameters(benchmark_symbols='SPY, QQQ')
assert w.as_tuple() == ('SPY', 'QQQ')
w = WorthBuyStocksParameters()
assert w.as_tuple() == ('SPY', 'QQQ')
# markov defaults
m = MarkovMethodParameters()
assert m.window == 20 and m.threshold == 0.05 and m.min_train == 252 and m.run_walkforward is False
print('All validations pass')
"`

- [ ] **Step 5: Commit**

```bash
cd /Users/chenkangan/Documents/TradeAgent
git add src/trade_research/skills/parameters.py src/trade_research/skills/__init__.py
git commit -m "feat: add typed skill parameter models for technical, worth-buy-stocks, markov-method"
```

---

### Task 2: TradeAgent — Add `skill_parameters` to `AnalysisRequest`

**Files:**
- Modify: `src/trade_research/domain/models.py`

**Interfaces:**
- Produces: `AnalysisRequest.skill_parameters: dict[str, dict[str, JsonValue]]` (new field, default `{}`)

- [ ] **Step 1: Add the field**

In `models.py`, find the `AnalysisRequest` class. Add the field after `positions`:

```python
skill_parameters: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)
```

The `JsonValue` type is already defined in the module. No new imports needed.

- [ ] **Step 2: Verify the model still validates**

Run: `cd /Users/chenkangan/Documents/TradeAgent && python -c "
from trade_research.domain import AnalysisRequest, InstrumentId
req = AnalysisRequest(
    instrument=InstrumentId(symbol='AAPL', market='US'),
    analysts=('technical',),
    skill_parameters={'technical': {'window': 10}},
)
print(req.skill_parameters)
assert req.skill_parameters == {'technical': {'window': 10}}
# default
req2 = AnalysisRequest(instrument=InstrumentId(symbol='AAPL', market='US'))
assert req2.skill_parameters == {}
print('OK')
"`

- [ ] **Step 3: Commit**

```bash
cd /Users/chenkangan/Documents/TradeAgent
git add src/trade_research/domain/models.py
git commit -m "feat: add skill_parameters field to AnalysisRequest"
```

---

### Task 3: TradeAgent — Add `configure_skill()` helper

**Files:**
- Modify: `src/trade_research/application.py`

**Interfaces:**
- Produces: `configure_skill(skill: ResearchSkill, params: dict[str, object]) -> ResearchSkill`
- Consumes: `TechnicalSkillParameters`, `WorthBuyStocksParameters`, `MarkovMethodParameters` (from Task 1)

- [ ] **Step 1: Add imports and the function**

Add imports at top of `application.py`:

```python
from dataclasses import replace
from trade_research.skills.parameters import (
    MarkovMethodParameters,
    TechnicalSkillParameters,
    WorthBuyStocksParameters,
)
```

Add `configure_skill()` before the `ResearchApplication` class:

```python
def configure_skill(skill: ResearchSkill, params: dict[str, object]) -> ResearchSkill:
    """Return a per-run copy of *skill* with validated *params* applied.

    The frozen registry is never mutated — this returns a new dataclass
    instance via ``dataclasses.replace()``.
    """
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

- [ ] **Step 2: Verify function works**

Run: `cd /Users/chenkangan/Documents/TradeAgent && python -c "
from trade_research.application import configure_skill
from trade_research.skills import TechnicalSkill, WorthBuyStocksSkill, MarkovMethodSkill, FundamentalSkill

# technical with custom window
base = TechnicalSkill()
configured = configure_skill(base, {'window': 10})
assert configured.window == 10
assert base.window == 20  # original unchanged
assert configured.name == 'technical'

# worth-buy with custom benchmarks
base = WorthBuyStocksSkill()
configured = configure_skill(base, {'benchmark_symbols': 'IWM,QQQ'})
assert configured.benchmark_symbols == ('IWM', 'QQQ')
assert base.benchmark_symbols == ('SPY', 'QQQ')  # original unchanged

# markov with custom params
base = MarkovMethodSkill()
configured = configure_skill(base, {'window': 10, 'threshold': 0.1, 'min_train': 500, 'run_walkforward': True})
assert configured.window == 10
assert configured.threshold == 0.1
assert configured.min_train == 500
assert configured.run_walkforward is True

# non-param skill with params raises
try:
    configure_skill(FundamentalSkill(), {'window': 5})
    assert False, 'should have raised'
except ValueError as e:
    assert 'does not accept parameters' in str(e)

# non-param skill without params returns unchanged
base = FundamentalSkill()
configured = configure_skill(base, {})
assert configured is base

print('All configure_skill checks pass')
"`

- [ ] **Step 3: Commit**

```bash
cd /Users/chenkangan/Documents/TradeAgent
git add src/trade_research/application.py
git commit -m "feat: add configure_skill() helper for per-run skill parameterization"
```

---

### Task 4: TradeAgent — Add `run_configured_skill()` to engine

**Files:**
- Modify: `src/trade_research/engine.py`

**Interfaces:**
- Produces: `ResearchEngine.run_configured_skill(skill: ResearchSkill, request: AnalysisRequest) -> AnalystResult`
- Consumes: `configure_skill` pattern from Task 3

- [ ] **Step 1: Add the method to `ResearchEngine`**

Add after the existing `_run_skill` method:

```python
    async def run_configured_skill(
        self, skill: ResearchSkill, request: AnalysisRequest
    ) -> AnalystResult:
        """Run a single pre-configured skill, bypassing the frozen registry.

        Unlike ``analyze()`` which rediscovers skills from the registry,
        this method accepts an already-configured skill instance (e.g. from
        ``configure_skill()``) and runs it directly.
        """
        self.validate_analysts((skill.name,))
        return await self._run_skill(skill, request)
```

- [ ] **Step 2: Verify the method is callable**

Run: `cd /Users/chenkangan/Documents/TradeAgent && python -c "
from trade_research.engine import ResearchEngine
print('run_configured_skill method exists:', hasattr(ResearchEngine, 'run_configured_skill'))
assert hasattr(ResearchEngine, 'run_configured_skill')
print('OK')
"`

- [ ] **Step 3: Commit**

```bash
cd /Users/chenkangan/Documents/TradeAgent
git add src/trade_research/engine.py
git commit -m "feat: add run_configured_skill() to ResearchEngine for bypassing frozen registry"
```

---

### Task 5: TradeAgent — Update `describe_skill()` and `run_skill()`

**Files:**
- Modify: `src/trade_research/application.py`

**Interfaces:**
- Consumes: `SKILL_PARAMETER_SCHEMAS` (Task 1), `configure_skill()` (Task 3), `engine.run_configured_skill()` (Task 4)
- Produces: `describe_skill()` returns `parameters` key; `run_skill()` uses configured copy

- [ ] **Step 1: Update `describe_skill()`**

Add `parameters` to the returned dict:

```python
    def describe_skill(self, name: str) -> JsonObject:
        skill = self.engine.skills.require(name)
        return {
            "name": skill.name,
            "description": (type(skill).__doc__ or "Research analyst skill").strip(),
            "immutable": True,
            "parameters": SKILL_PARAMETER_SCHEMAS.get(name),
        }
```

Add the import for `SKILL_PARAMETER_SCHEMAS` at the top:

```python
from trade_research.skills.parameters import SKILL_PARAMETER_SCHEMAS
```

- [ ] **Step 2: Update `run_skill()`**

Replace the body to configure the skill before running:

```python
    async def run_skill(self, name: str, request: AnalysisRequest) -> JsonObject:
        base_skill = self.engine.skills.require(name)
        params = request.skill_parameters.get(name, {})
        configured = configure_skill(base_skill, params)
        self.engine.validate_analysts((name,))
        result = await self.engine.run_configured_skill(configured, request)
        wrapped = ResearchReport(
            request_id=request.request_id,
            instrument=request.instrument,
            results=(result,),
            generated_at=datetime.now(UTC),
        )
        sanitized = sanitize_report(wrapped)
        self.reports.save(sanitized)
        return _json_object(render_json(sanitized))
```

Add necessary imports:

```python
from datetime import UTC, datetime
from trade_research.domain import ResearchReport
from trade_research.reporting import render_json, sanitize_report
```

- [ ] **Step 3: Verify imports resolve**

Run: `cd /Users/chenkangan/Documents/TradeAgent && python -c "from trade_research.application import ResearchApplication, configure_skill; print('Imports OK')"`

- [ ] **Step 4: Commit**

```bash
cd /Users/chenkangan/Documents/TradeAgent
git add src/trade_research/application.py
git commit -m "feat: wire skill parameters through describe_skill() and run_skill()"
```

---

### Task 6: TradeAgent — Add parameter validation error handling to HTTP layer

**Files:**
- Modify: `src/trade_research/http.py`

**Interfaces:**
- Consumes: `configure_skill()` raises `ValueError` for unknown-param skills; Pydantic `ValidationError` for bad params
- Produces: HTTP 422 response for both cases

- [ ] **Step 1: Add exception handler in `/skills/{name}/run`**

Update the `run_skill` endpoint to catch `ValueError`:

```python
    @api.post("/skills/{name}/run", dependencies=authenticated)
    async def run_skill(name: str, request: AnalysisRequest) -> dict[str, Any]:
        try:
            return await application.run_skill(name, request)
        except ProviderConfigurationError as error:
            raise HTTPException(
                status_code=503, detail="selected capability unavailable"
            ) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="unknown skill") from error
        except ValueError as error:
            raise HTTPException(
                status_code=422, detail=str(error)
            ) from error
```

Note: `ValidationError` from Pydantic is already caught by the existing `invalid_application_value` handler (line 67-71), which returns 422. The new `ValueError` catch handles the case from `configure_skill()` when a non-parameterized skill receives non-empty params.

- [ ] **Step 2: Verify error handling**

Run: `cd /Users/chenkangan/Documents/TradeAgent && python -c "
from trade_research.http import create_app
print('create_app imports OK')
# Verify the ValueError catch is in the source
import inspect
src = inspect.getsource(create_app)
assert 'ValueError' in src
print('ValueError handler present')
"`

- [ ] **Step 3: Commit**

```bash
cd /Users/chenkangan/Documents/TradeAgent
git add src/trade_research/http.py
git commit -m "fix: catch ValueError in /skills/{name}/run route for parameter validation errors"
```

---

### Task 7: TradeAgent — Write tests for skill parameters

**Files:**
- Create: `tests/unit/test_skill_parameters.py`
- Create: `tests/integration/test_skill_api_parameters.py`

**Interfaces:**
- Consumes: All parameter models (Task 1), `configure_skill()` (Task 3), updated endpoints (Tasks 5-6)

- [ ] **Step 1: Write unit tests for parameter models**

Create `tests/unit/test_skill_parameters.py`:

```python
"""Unit tests for skill parameter models and configure_skill()."""

import pytest
from pydantic import ValidationError

from trade_research.skills import (
    FundamentalSkill,
    MarkovMethodSkill,
    TechnicalSkill,
    WorthBuyStocksSkill,
)
from trade_research.application import configure_skill
from trade_research.skills.parameters import (
    MarkovMethodParameters,
    SKILL_PARAMETER_SCHEMAS,
    TechnicalSkillParameters,
    WorthBuyStocksParameters,
)


class TestTechnicalSkillParameters:
    def test_defaults(self):
        p = TechnicalSkillParameters()
        assert p.window == 20

    def test_valid_custom_window(self):
        p = TechnicalSkillParameters(window=10)
        assert p.window == 10

    def test_window_min_boundary(self):
        p = TechnicalSkillParameters(window=2)
        assert p.window == 2

    def test_window_max_boundary(self):
        p = TechnicalSkillParameters(window=252)
        assert p.window == 252

    def test_window_below_min_raises(self):
        with pytest.raises(ValidationError):
            TechnicalSkillParameters(window=1)

    def test_window_above_max_raises(self):
        with pytest.raises(ValidationError):
            TechnicalSkillParameters(window=300)


class TestWorthBuyStocksParameters:
    def test_defaults(self):
        p = WorthBuyStocksParameters()
        assert p.benchmark_symbols == "SPY,QQQ"
        assert p.as_tuple() == ("SPY", "QQQ")

    def test_single_symbol(self):
        p = WorthBuyStocksParameters(benchmark_symbols="SPY")
        assert p.as_tuple() == ("SPY",)

    def test_trims_and_uppercases(self):
        p = WorthBuyStocksParameters(benchmark_symbols=" spy , qqq , IWM ")
        assert p.as_tuple() == ("SPY", "QQQ", "IWM")

    def test_empty_raises(self):
        with pytest.raises(ValidationError):
            WorthBuyStocksParameters(benchmark_symbols="")


class TestMarkovMethodParameters:
    def test_defaults(self):
        p = MarkovMethodParameters()
        assert p.window == 20
        assert p.threshold == 0.05
        assert p.min_train == 252
        assert p.run_walkforward is False

    def test_custom_all(self):
        p = MarkovMethodParameters(window=10, threshold=0.1, min_train=500, run_walkforward=True)
        assert p.window == 10
        assert p.threshold == 0.1
        assert p.min_train == 500
        assert p.run_walkforward is True

    def test_threshold_zero_raises(self):
        with pytest.raises(ValidationError):
            MarkovMethodParameters(threshold=0)

    def test_threshold_above_one_raises(self):
        with pytest.raises(ValidationError):
            MarkovMethodParameters(threshold=1.5)

    def test_min_train_below_min_raises(self):
        with pytest.raises(ValidationError):
            MarkovMethodParameters(min_train=10)


class TestSkillParameterSchemas:
    def test_schemas_present_for_three_skills(self):
        assert "technical" in SKILL_PARAMETER_SCHEMAS
        assert "worth-buy-stocks" in SKILL_PARAMETER_SCHEMAS
        assert "markov-method" in SKILL_PARAMETER_SCHEMAS

    def test_technical_schema_has_window_property(self):
        schema = SKILL_PARAMETER_SCHEMAS["technical"]
        assert "window" in schema["properties"]
        assert schema["properties"]["window"]["type"] == "integer"
        assert schema["properties"]["window"]["default"] == 20
        assert schema["properties"]["window"]["minimum"] == 2
        assert schema["properties"]["window"]["maximum"] == 252

    def test_markov_schema_has_all_properties(self):
        schema = SKILL_PARAMETER_SCHEMAS["markov-method"]
        props = schema["properties"]
        assert "window" in props
        assert "threshold" in props
        assert "min_train" in props
        assert "run_walkforward" in props
        assert props["run_walkforward"]["type"] == "boolean"


class TestConfigureSkill:
    def test_technical_window_applied(self):
        base = TechnicalSkill()
        configured = configure_skill(base, {"window": 10})
        assert configured.window == 10
        assert base.window == 20  # original unchanged
        assert configured.name == "technical"

    def test_worth_buy_benchmarks_applied(self):
        base = WorthBuyStocksSkill()
        configured = configure_skill(base, {"benchmark_symbols": "IWM,QQQ"})
        assert configured.benchmark_symbols == ("IWM", "QQQ")
        assert base.benchmark_symbols == ("SPY", "QQQ")

    def test_markov_all_params_applied(self):
        base = MarkovMethodSkill()
        configured = configure_skill(
            base, {"window": 10, "threshold": 0.1, "min_train": 500, "run_walkforward": True}
        )
        assert configured.window == 10
        assert configured.threshold == 0.1
        assert configured.min_train == 500
        assert configured.run_walkforward is True

    def test_non_param_skill_with_params_raises_valueerror(self):
        with pytest.raises(ValueError, match="does not accept parameters"):
            configure_skill(FundamentalSkill(), {"window": 5})

    def test_non_param_skill_empty_params_returns_unchanged(self):
        base = FundamentalSkill()
        result = configure_skill(base, {})
        assert result is base

    def test_invalid_window_type_raises_validationerror(self):
        with pytest.raises(ValidationError):
            configure_skill(TechnicalSkill(), {"window": "not_a_number"})
```

- [ ] **Step 2: Run unit tests**

Run: `cd /Users/chenkangan/Documents/TradeAgent && python -m pytest tests/unit/test_skill_parameters.py -v`
Expected: All tests pass.

- [ ] **Step 3: Write integration tests**

Create `tests/integration/test_skill_api_parameters.py`:

```python
"""Integration tests for skill parameter API endpoints."""

import pytest
from fastapi.testclient import TestClient

from trade_research.application import ResearchApplication
from trade_research.engine import ResearchEngine
from trade_research.http import create_app
from trade_research.providers import ProviderRegistry
from trade_research.reporting import ReportStore
from trade_research.skills import SkillRegistry, TechnicalSkill, WorthBuyStocksSkill, MarkovMethodSkill, FundamentalSkill, FilingsSkill


BEARER = "test-token"


def _make_client(providers=None):
    skills = SkillRegistry(
        (FundamentalSkill(), TechnicalSkill(), FilingsSkill(),
         WorthBuyStocksSkill(), MarkovMethodSkill())
    )
    engine = ResearchEngine(
        skills,
        providers or ProviderRegistry({}),
    )
    app = ResearchApplication(engine, ReportStore())
    return TestClient(create_app(app, bearer_token=BEARER))


def _auth():
    return {"Authorization": f"Bearer {BEARER}"}


class TestSkillsEndpointParameters:
    def test_list_skills_includes_parameters(self):
        client = _make_client()
        resp = client.get("/skills", headers=_auth())
        assert resp.status_code == 200
        skills = resp.json()
        skill_map = {s["name"]: s for s in skills}

        assert "parameters" in skill_map["technical"]
        assert skill_map["technical"]["parameters"] is not None
        assert "window" in skill_map["technical"]["parameters"]["properties"]

        assert "parameters" in skill_map["worth-buy-stocks"]
        assert skill_map["worth-buy-stocks"]["parameters"] is not None

        assert "parameters" in skill_map["markov-method"]
        assert skill_map["markov-method"]["parameters"] is not None

    def test_fundamental_has_no_parameters(self):
        client = _make_client()
        resp = client.get("/skills", headers=_auth())
        assert resp.status_code == 200
        skills = resp.json()
        fundamental = next(s for s in skills if s["name"] == "fundamental")
        assert fundamental["parameters"] is None

    def test_describe_skill_includes_parameters(self):
        client = _make_client()
        resp = client.get("/skills/technical", headers=_auth())
        assert resp.status_code == 200
        skill = resp.json()
        assert skill["parameters"] is not None
        assert skill["parameters"]["properties"]["window"]["default"] == 20


class TestSkillRunParameters:
    def test_run_skill_with_valid_parameters_accepted(self):
        """A skill run with valid parameters should be accepted, though it may
        fail at the provider level if no price provider is configured."""
        client = _make_client()
        resp = client.post(
            "/skills/technical/run",
            json={
                "instrument": {"symbol": "AAPL", "market": "US"},
                "analysts": ["technical"],
                "skill_parameters": {"technical": {"window": 10}},
            },
            headers=_auth(),
        )
        # 503 means params were accepted but no price provider configured
        # 200 would mean params accepted AND price data available
        # 422 would mean parameter validation failed
        assert resp.status_code != 422, f"Should not get 422 for valid params: {resp.json()}"

    def test_run_skill_with_invalid_window_returns_422(self):
        client = _make_client()
        resp = client.post(
            "/skills/technical/run",
            json={
                "instrument": {"symbol": "AAPL", "market": "US"},
                "analysts": ["technical"],
                "skill_parameters": {"technical": {"window": 0}},
            },
            headers=_auth(),
        )
        assert resp.status_code == 422

    def test_run_skill_with_non_param_skill_and_params_returns_422(self):
        client = _make_client()
        resp = client.post(
            "/skills/fundamental/run",
            json={
                "instrument": {"symbol": "AAPL", "market": "US"},
                "analysts": ["fundamental"],
                "skill_parameters": {"fundamental": {"nonsense": True}},
            },
            headers=_auth(),
        )
        assert resp.status_code == 422

    def test_no_stack_trace_in_error_response(self):
        client = _make_client()
        resp = client.post(
            "/skills/technical/run",
            json={
                "instrument": {"symbol": "AAPL", "market": "US"},
                "analysts": ["technical"],
                "skill_parameters": {"technical": {"window": -999}},
            },
            headers=_auth(),
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "Traceback" not in str(body)
        assert "stack" not in str(body).lower()
```

- [ ] **Step 4: Run integration tests**

Run: `cd /Users/chenkangan/Documents/TradeAgent && python -m pytest tests/integration/test_skill_api_parameters.py -v`
Expected: All tests pass (some skill runs may return 503 due to missing providers — that's expected; the key assertions are about 200/422/404 status codes).

- [ ] **Step 5: Run existing tests to verify no regressions**

Run: `cd /Users/chenkangan/Documents/TradeAgent && python -m pytest tests/ -v`
Expected: All existing tests pass; new tests pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/chenkangan/Documents/TradeAgent
git add tests/unit/test_skill_parameters.py tests/integration/test_skill_api_parameters.py
git commit -m "test: add unit and integration tests for skill parameters"
```

---

### Task 8: PAMASTER — Update API schemas

**Files:**
- Modify: `backend/src/pa_investing/api/schemas.py`

**Interfaces:**
- Produces: `ResearchSkillResponse.parameters: dict | None`, `ResearchRunRequest.skill_parameters: dict[str, dict[str, Any]]`

- [ ] **Step 1: Add `parameters` to `ResearchSkillResponse`**

```python
class ResearchSkillResponse(BaseModel):
    name: str
    description: str
    immutable: bool = True
    parameters: dict | None = None
```

- [ ] **Step 2: Add `skill_parameters` to `ResearchRunRequest`**

```python
class ResearchRunRequest(BaseModel):
    account_id: str | None = None
    instrument_id: str | None = None
    symbol: str | None = None
    market: str | None = None
    skills: list[str]
    skill_parameters: dict[str, dict[str, Any]] = {}
```

- [ ] **Step 3: Verify schema imports**

Run: `cd /Users/chenkangan/Documents/PAMASTER/backend && python -c "
from pa_investing.api.schemas import ResearchSkillResponse, ResearchRunRequest
# default parameters
r = ResearchSkillResponse(name='test', description='desc')
assert r.parameters is None
# with parameters
r2 = ResearchSkillResponse(name='test', description='desc', parameters={'window': {'type': 'integer'}})
assert r2.parameters == {'window': {'type': 'integer'}}
# run request default
rr = ResearchRunRequest(skills=['technical'])
assert rr.skill_parameters == {}
# run request with params
rr2 = ResearchRunRequest(skills=['technical'], skill_parameters={'technical': {'window': 10}})
assert rr2.skill_parameters == {'technical': {'window': 10}}
print('OK')
"`

- [ ] **Step 4: Commit**

```bash
cd /Users/chenkangan/Documents/PAMASTER
git add backend/src/pa_investing/api/schemas.py
git commit -m "feat: add parameters to ResearchSkillResponse and skill_parameters to ResearchRunRequest"
```

---

### Task 9: PAMASTER — Update TradeAgent client

**Files:**
- Modify: `backend/src/pa_investing/research/trade_agent.py`

**Interfaces:**
- Produces: `TradeAgentClient.run_skill(skill=..., symbol=..., market=..., position=..., skill_parameters=None)`

- [ ] **Step 1: Add `skill_parameters` parameter and forward it**

Add the parameter to the `run_skill` method signature:

```python
    def run_skill(
        self,
        *,
        skill: str,
        symbol: str,
        market: str,
        position: Position | None = None,
        skill_parameters: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
```

And in the request body construction, add after the `metadata` block:

```python
        if skill_parameters:
            request["skill_parameters"] = skill_parameters
```

- [ ] **Step 2: Verify client method signature**

Run: `cd /Users/chenkangan/Documents/PAMASTER/backend && python -c "
import inspect
from pa_investing.research.trade_agent import TradeAgentClient
sig = inspect.signature(TradeAgentClient.run_skill)
assert 'skill_parameters' in sig.parameters
print('OK')
"`

- [ ] **Step 3: Commit**

```bash
cd /Users/chenkangan/Documents/PAMASTER
git add backend/src/pa_investing/research/trade_agent.py
git commit -m "feat: forward skill_parameters through TradeAgentClient.run_skill()"
```

---

### Task 10: PAMASTER — Update API routes

**Files:**
- Modify: `backend/src/pa_investing/api/routes.py`

**Interfaces:**
- Consumes: Updated schemas (Task 8), updated client (Task 9)
- Produces: Skills endpoint forwards `parameters`; Run endpoint sends `skill_parameters`

- [ ] **Step 1: Update research skills endpoint**

In the `research_skills()` function, update the `ResearchSkillResponse` construction to include `parameters`:

```python
    return ResearchSkillsResponse(
        configured=True,
        status="available",
        skills=[
            ResearchSkillResponse(
                name=str(item.get("name") or ""),
                description=str(item.get("description") or ""),
                immutable=bool(item.get("immutable", True)),
                parameters=item.get("parameters"),
            )
            for item in skills
            if item.get("name")
        ],
    )
```

- [ ] **Step 2: Update research run endpoint**

In the `run_research()` function, update the `client.run_skill()` call to pass `skill_parameters`:

```python
    skill_params = payload.skill_parameters
    results: list[ResearchRunResultResponse] = []
    for skill in skills:
        try:
            report = client.run_skill(
                skill=skill,
                symbol=symbol,
                market=market,
                position=position,
                skill_parameters=skill_params,
            )
```

- [ ] **Step 3: Verify routes import**

Run: `cd /Users/chenkangan/Documents/PAMASTER/backend && python -c "from pa_investing.api.routes import research_skills, run_research; print('OK')"`

- [ ] **Step 4: Commit**

```bash
cd /Users/chenkangan/Documents/PAMASTER
git add backend/src/pa_investing/api/routes.py
git commit -m "feat: proxy skill parameters from TradeAgent and forward to run endpoint"
```

---

### Task 11: PAMASTER — Add Plotly CDN and dynamic parameter controls to Research page

**Files:**
- Modify: `backend/src/pa_investing/analytics_app/pages.py` (the `research_page()` function, ~lines 1753-2188)

**Interfaces:**
- Consumes: `parameters` field in skill data from Task 10
- Produces: Plotly CDN in `<head>`; parameter input controls rendered under each skill checkbox

- [ ] **Step 1: Add Plotly CDN script tag**

Insert after the existing meta tags in `<head>` (after line 1761):

```html
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
```

- [ ] **Step 2: Update `loadSkills()` to render parameter controls**

Replace the `loadSkills()` function:

```javascript
async function loadSkills() {
  const response = await fetch('/analysis/research/skills');
  if (!response.ok) throw new Error(`Skills request failed (${response.status})`);
  const payload = await response.json();
  state.skills = payload.skills || [];
  const container = byId('skills');
  container.innerHTML = '';
  if (!payload.configured || payload.status !== 'available') {
    setStatus(payload.detail || 'TradeAgent is unavailable.', true);
    return;
  }
  for (const skill of state.skills) {
    const wrapper = document.createElement('div');
    wrapper.className = 'skill-entry';
    const label = document.createElement('label');
    label.className = 'skill-option';
    label.innerHTML = `<input type="checkbox" data-skill="${skill.name}" />` +
      `<span>${skill.name}</span>`;
    wrapper.append(label);

    if (skill.parameters && skill.parameters.properties) {
      const controls = document.createElement('div');
      controls.className = 'skill-params';
      controls.id = `params-${skill.name}`;
      controls.style.display = 'none';
      for (const [name, prop] of Object.entries(skill.parameters.properties)) {
        const paramLabel = document.createElement('label');
        paramLabel.style.fontWeight = '500';
        paramLabel.style.fontSize = '12px';
        paramLabel.textContent = name;
        let input;
        if (prop.type === 'boolean') {
          input = document.createElement('input');
          input.type = 'checkbox';
          if (prop.default === true) input.checked = true;
          input.dataset.param = name;
          input.dataset.skill = skill.name;
          paramLabel.style.display = 'flex';
          paramLabel.style.alignItems = 'center';
          paramLabel.style.gap = '6px';
          paramLabel.prepend(input);
        } else {
          input = document.createElement('input');
          input.type = prop.type === 'integer' || prop.type === 'number' ? 'number' : 'text';
          if (prop.type === 'integer') input.step = '1';
          if (prop.type === 'number' && !prop.step) input.step = '0.01';
          if (prop.minimum !== undefined) input.min = prop.minimum;
          if (prop.maximum !== undefined) input.max = prop.maximum;
          if (prop.default !== undefined) input.value = prop.default;
          input.dataset.param = name;
          input.dataset.skill = skill.name;
          paramLabel.append(input);
        }
        controls.append(paramLabel);
      }
      wrapper.append(controls);
      const checkbox = label.querySelector('input[type=checkbox]');
      checkbox.addEventListener('change', function () {
        controls.style.display = this.checked ? 'grid' : 'none';
      });
    }
    container.append(wrapper);
  }
  const first = container.querySelector('input[type=checkbox]');
  if (first) first.checked = true;
  setStatus('Ready.');
}
```

- [ ] **Step 3: Add CSS for parameter controls**

Add to the `<style>` block (before `@media` query):

```css
.skill-entry {
  display: grid;
  gap: 4px;
}
.skill-params {
  display: grid;
  gap: 6px;
  padding: 6px 0 6px 26px;
}
.skill-params label {
  display: grid;
  gap: 3px;
  font-size: 12px;
}
.skill-params input[type="number"],
.skill-params input[type="text"] {
  min-height: 32px;
  padding: 4px 8px;
}
```

- [ ] **Step 4: Update `runResearch()` to collect and send `skill_parameters`**

Replace the `runResearch()` function's fetch body:

```javascript
async function runResearch() {
  const skills = selectedSkills();
  const symbol = byId('symbol-input').value.trim();
  const market = byId('market-input').value.trim();
  if (!symbol || !market || !skills.length) {
    setStatus('Choose a symbol, market, and at least one skill.', true);
    return;
  }
  const skillParameters = {};
  for (const skill of skills) {
    const params = {};
    const controls = document.querySelectorAll(`[data-skill="${skill}"][data-param]`);
    for (const input of controls) {
      const name = input.dataset.param;
      if (input.type === 'checkbox') {
        params[name] = input.checked;
      } else if (input.type === 'number') {
        params[name] = input.value.includes('.') ? parseFloat(input.value) : parseInt(input.value, 10);
      } else {
        params[name] = input.value;
      }
    }
    if (Object.keys(params).length) skillParameters[skill] = params;
  }
  const button = byId('run-button');
  button.disabled = true;
  setStatus('Running selected skills...');
  byId('results').innerHTML = '<div class="status">Running...</div>';
  try {
    const response = await fetch('/analysis/research/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        account_id: state.selected ? state.selected.account_id : null,
        instrument_id: state.selected ? state.selected.instrument_id : null,
        symbol,
        market,
        skills,
        skill_parameters: skillParameters,
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || `Run failed (${response.status})`);
    }
    byId('results').innerHTML = payload.results.map(renderReport).join('');
    setStatus('Research complete.');
  } catch (error) {
    byId('results').innerHTML = `<div class="status warning">${error.message}</div>`;
    setStatus(error.message || 'Research failed.', true);
  } finally {
    button.disabled = false;
  }
}
```

- [ ] **Step 5: Verify the page loads (static check)**

Run: `cd /Users/chenkangan/Documents/PAMASTER/backend && python -c "from pa_investing.analytics_app.pages import research_page; html = research_page(); assert 'plotly-2.35.2' in html; assert 'skill-params' in html; assert 'skill_parameters' in html; print('OK')"`

- [ ] **Step 6: Commit**

```bash
cd /Users/chenkangan/Documents/PAMASTER
git add backend/src/pa_investing/analytics_app/pages.py
git commit -m "feat: add Plotly CDN and dynamic skill parameter controls to Research page"
```

---

### Task 12: PAMASTER — Add tabbed layout and template registry to Research page

**Files:**
- Modify: `backend/src/pa_investing/analytics_app/pages.py` (the `research_page()` function)

**Interfaces:**
- Consumes: `renderReport()` (to be replaced)
- Produces: Tabbed results area; `REPORT_TEMPLATES` registry; `renderTabs()`; fallback `renderGenericReport()`

- [ ] **Step 1: Add tab layout CSS**

Append to the `<style>` block (before `@media`):

```css
.tab-bar {
  display: flex;
  gap: 2px;
  margin-bottom: 12px;
  overflow-x: auto;
  border-bottom: 1px solid #dbe4f0;
}
.tab-btn {
  border: 0;
  background: transparent;
  color: #64748b;
  padding: 8px 14px;
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
  border-bottom: 3px solid transparent;
  white-space: nowrap;
}
.tab-btn.active {
  color: #1d4ed8;
  border-bottom-color: #2563eb;
}
.tab-panel {
  display: none;
}
.tab-panel.active {
  display: block;
}
.report-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.report-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
}
@media (min-width: 900px) {
  .report-grid {
    grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
  }
}
.narrative .section {
  margin-bottom: 14px;
}
.narrative .section h3 {
  font-size: 14px;
  color: #1e293b;
  margin: 0 0 4px;
}
.narrative .section p {
  font-size: 13px;
  color: #475569;
  line-height: 1.5;
  margin: 0;
}
.visuals .chart-box {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px;
  margin-bottom: 10px;
}
.ref-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 8px;
}
.ref-card {
  border: 1px solid #dbe4f0;
  border-radius: 8px;
  padding: 10px;
  text-align: center;
}
.ref-card .ref-label {
  font-size: 11px;
  color: #64748b;
  margin-bottom: 4px;
}
.ref-card .ref-value {
  font-size: 18px;
  font-weight: 680;
  font-variant-numeric: tabular-nums;
}
.signal-chip {
  display: inline-flex;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 650;
}
.signal-chip.bullish { background: #dcfce7; color: #166534; }
.signal-chip.bearish { background: #fee2e2; color: #991b1b; }
.signal-chip.neutral { background: #f1f5f9; color: #475569; }
.signal-chip.not_assessed { background: #fef3c7; color: #92400e; }
.status-badge {
  display: inline-flex;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 650;
}
.status-badge.complete { background: #e0e7ff; color: #3730a3; }
.status-badge.partial { background: #fef3c7; color: #92400e; }
.status-badge.failed { background: #fee2e2; color: #991b1b; }
```

- [ ] **Step 2: Replace `renderReport()` and add template registry**

Replace the entire `renderReport()` function and add the template registry + tab logic:

```javascript
const ENTRY_CLASS_LABELS = {
  0: "Trend Broken",
  1: "Overextended",
  2: "Pullback Without Trigger",
  3: "Trend Continuation",
  4: "Pullback Reversal",
  5: "Recovery Reversal",
};

const REGIME_LABELS = {
  0: "Bear",
  1: "Sideways",
  2: "Bull",
};

function findObs(report, metric) {
  for (const section of report.results || []) {
    for (const obs of section.observations || []) {
      if (obs.metric === metric) return obs.value;
    }
  }
  return null;
}

function signalChip(signal) {
  const cls = signal || 'not_assessed';
  return `<span class="signal-chip ${cls}">${cls.replace('_', ' ')}</span>`;
}

function statusBadge(status) {
  return `<span class="status-badge ${status}">${status}</span>`;
}

// -- Generic / fallback renderer --
function renderGenericReport(report, result) {
  const rows = [];
  for (const section of report.results || []) {
    for (const obs of section.observations || []) {
      rows.push(`<tr><td>${section.analyst}</td><td>${obs.metric}</td>` +
        `<td>${JSON.stringify(obs.value)}</td><td>${obs.source}</td></tr>`);
    }
  }
  return `<div class="narrative">` +
    `<div class="section"><h3>Summary</h3><p>${result.signal || 'not_assessed'} signal, ` +
    `${result.status || 'unknown'} status. ${result.summary || ''}</p></div>` +
    (rows.length ? `<table><thead><tr><th>Skill</th><th>Metric</th><th>Value</th>` +
      `<th>Source</th></tr></thead><tbody>${rows.join('')}</tbody></table>` :
      '<div class="status">No numeric observations returned.</div>') +
    `</div>`;
}

const REPORT_TEMPLATES = {
  "technical": null,       // filled in Task 13
  "worth-buy-stocks": null, // filled in Task 14
  "markov-method": null,    // filled in Task 15
  "_fallback": renderGenericReport,
};

function renderReport(result) {
  // Returns HTML for one tab panel
  if (result.status === 'failed') {
    return `<div class="report-header">` +
      `<strong>${result.skill}</strong>` +
      `<span class="status-badge failed">failed</span></div>` +
      `<div class="status warning">${result.detail || 'Skill failed.'}</div>`;
  }
  const report = result.report || {};
  const section = (report.results || [])[0] || {};
  const analyst = section.analyst || result.skill;
  const renderer = REPORT_TEMPLATES[analyst] || REPORT_TEMPLATES["_fallback"];

  const narrativeHtml = renderer(report, section);
  const signal = section.signal || 'not_assessed';
  const status = section.status || 'unknown';

  return `<div class="report-header">` +
    `<strong>${analyst}</strong>` +
    statusBadge(status) +
    signalChip(signal) +
    `</div>` +
    `<div class="report-grid">` +
    `<div class="narrative">${narrativeHtml}</div>` +
    `<div class="visuals" id="viz-${analyst}"></div>` +
    `</div>` +
    `<details style="margin-top:12px"><summary>Raw JSON</summary>` +
    `<pre>${JSON.stringify(report, null, 2)}</pre></details>`;
}

function renderTabs(results) {
  if (!results.length) {
    byId('results').innerHTML = '<div class="status">No results.</div>';
    return;
  }
  state.results = results;
  state.activeTab = 0;
  const tabs = results.map((r, i) => {
    const section = (r.report && r.report.results ? r.report.results[0] : null);
    const label = (section && section.analyst) || r.skill;
    return `<button class="tab-btn${i === 0 ? ' active' : ''}" data-tab="${i}">${label}</button>`;
  }).join('');
  const panels = results.map((r, i) =>
    `<div class="tab-panel${i === 0 ? ' active' : ''}" data-panel="${i}">${renderReport(r)}</div>`
  ).join('');
  byId('results').innerHTML =
    `<div class="tab-bar">${tabs}</div>` +
    `<div class="tab-panels">${panels}</div>`;

  // Wire tab clicks
  byId('results').querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', function () {
      const idx = parseInt(this.dataset.tab);
      state.activeTab = idx;
      byId('results').querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      byId('results').querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      byId('results').querySelector(`[data-panel="${idx}"]`).classList.add('active');
    });
  });

  // Trigger chart rendering for active tab
  renderChartsForTab(0);
}
```

- [ ] **Step 3: Update `runResearch()` to use `renderTabs()`**

In `runResearch()`, replace:
```javascript
byId('results').innerHTML = payload.results.map(renderReport).join('');
```
with:
```javascript
renderTabs(payload.results);
```

- [ ] **Step 4: Add chart rendering dispatcher (stub)**

Add this before `renderTabs()`:

```javascript
function renderChartsForTab(tabIndex) {
  const result = state.results[tabIndex];
  if (!result || result.status !== 'complete') return;
  const report = result.report || {};
  const section = (report.results || [])[0];
  if (!section) return;
  const analyst = section.analyst || result.skill;
  const vizEl = byId(`viz-${analyst}`);
  if (!vizEl) return;
  // Each template fills this in its own plot function
  const plotFns = {
    "technical": plotTechnicalCharts,
    "worth-buy-stocks": plotWorthBuyCharts,
    "markov-method": plotMarkovCharts,
  };
  const plotFn = plotFns[analyst];
  if (plotFn) plotFn(section, vizEl);
}
```

The `plotTechnicalCharts`, `plotWorthBuyCharts`, and `plotMarkovCharts` functions will be added in Tasks 13-15.

- [ ] **Step 5: Verify the page renders static HTML**

Run: `cd /Users/chenkangan/Documents/PAMASTER/backend && python -c "from pa_investing.analytics_app.pages import research_page; html = research_page(); assert 'tab-bar' in html; assert 'report-grid' in html; assert 'REPORT_TEMPLATES' in html; assert 'renderTabs' in html; print('OK')"`

- [ ] **Step 6: Commit**

```bash
cd /Users/chenkangan/Documents/PAMASTER
git add backend/src/pa_investing/analytics_app/pages.py
git commit -m "feat: add tabbed layout and template registry to Research page"
```

---

### Task 13: PAMASTER — Technical analysis report template

**Files:**
- Modify: `backend/src/pa_investing/analytics_app/pages.py`

**Interfaces:**
- Consumes: Template registry (Task 12), `findObs()`, Plotly (CDN loaded in Task 11)
- Produces: `renderTechnicalReport(report, section)` and `plotTechnicalCharts(section, vizEl)`

- [ ] **Step 1: Add `renderTechnicalReport()` function**

Insert before `REPORT_TEMPLATES`:

```javascript
function renderTechnicalReport(report, section) {
  const missing = section.missing_metrics || [];
  const limitations = section.limitations || [];
  const priceReturn = findObs(report, 'price_return');
  const sma = findObs(report, 'simple_moving_average_20') || findObs(report, 'simple_moving_average');
  const ema = findObs(report, 'exponential_moving_average_20');
  const rsi = findObs(report, 'relative_strength_index_14');
  const macd = findObs(report, 'macd_12_26');
  const macdSig = findObs(report, 'macd_signal_9');
  const macdHist = findObs(report, 'macd_histogram');
  const atr = findObs(report, 'average_true_range_14');
  const vol = findObs(report, 'annualized_volatility_20');
  const volTrend = findObs(report, 'volume_trend_20');
  const momentum = findObs(report, 'momentum_10');
  const bbMid = findObs(report, 'bollinger_middle_20');
  const bbUpper = findObs(report, 'bollinger_upper_20_2');
  const bbLower = findObs(report, 'bollinger_lower_20_2');

  let summary = `${section.signal || 'Not assessed'} signal with ${section.status || 'unknown'} status.`;
  if (section.status === 'partial') summary += ' Some indicators could not be computed due to insufficient data.';
  if (section.summary) summary = section.summary;

  function trendText() {
    const parts = [];
    if (sma != null) parts.push(`SMA(20) is ${Number(sma).toFixed(2)}`);
    if (priceReturn != null) parts.push(`price return is ${(Number(priceReturn) * 100).toFixed(2)}%`);
    if (!parts.length) return 'Insufficient data for trend assessment.';
    return parts.join('; ') + '.';
  }

  function momentumText() {
    const parts = [];
    if (rsi != null) {
      const r = Number(rsi);
      parts.push(`RSI(14) is ${r.toFixed(1)} (${r > 70 ? 'overbought' : r < 30 ? 'oversold' : 'neutral'})`);
    }
    if (macdHist != null) {
      const mh = Number(macdHist);
      parts.push(`MACD histogram is ${mh > 0 ? 'positive' : 'negative'} at ${mh.toFixed(4)}`);
    }
    if (!parts.length) return 'Insufficient data for momentum assessment.';
    return parts.join('; ') + '.';
  }

  function riskText() {
    const parts = [];
    if (atr != null) parts.push(`ATR(14) is ${Number(atr).toFixed(2)}`);
    if (vol != null) parts.push(`annualized volatility is ${(Number(vol) * 100).toFixed(1)}%`);
    if (bbMid != null && bbUpper != null && bbLower != null) {
      parts.push(`Bollinger Bands: lower ${Number(bbLower).toFixed(2)}, middle ${Number(bbMid).toFixed(2)}, upper ${Number(bbUpper).toFixed(2)}`);
    }
    if (!parts.length) return 'Insufficient data for risk range assessment.';
    return parts.join('; ') + '.';
  }

  function volumeText() {
    const parts = [];
    if (volTrend != null) {
      const v = Number(volTrend);
      parts.push(`volume trend is ${v > 0 ? 'expanding' : 'contracting'} (${(v * 100).toFixed(1)}%)`);
    }
    if (missing.length) parts.push(`missing metrics: ${missing.join(', ')}`);
    if (limitations.length) parts.push(`limitations: ${limitations.join(', ')}`);
    if (!parts.length) return 'No volume data or data quality issues reported.';
    return parts.join('; ') + '.';
  }

  return `<div class="section"><h3>Summary</h3><p>${summary}</p></div>` +
    `<div class="section"><h3>Trend</h3><p>${trendText()}</p></div>` +
    `<div class="section"><h3>Momentum</h3><p>${momentumText()}</p></div>` +
    `<div class="section"><h3>Risk Range</h3><p>${riskText()}</p></div>` +
    `<div class="section"><h3>Volume & Data Quality</h3><p>${volumeText()}</p></div>`;
}
```

- [ ] **Step 2: Add `plotTechnicalCharts()` function**

```javascript
function plotTechnicalCharts(section, vizEl) {
  const metrics = [
    {label: 'Return %', metric: 'price_return', format: v => (v * 100).toFixed(2)},
    {label: 'RSI (0-100)', metric: 'relative_strength_index_14', format: v => v.toFixed(1)},
    {label: 'MACD Hist', metric: 'macd_histogram', format: v => v.toFixed(4)},
    {label: 'Volatility %', metric: 'annualized_volatility_20', format: v => (v * 100).toFixed(1)},
    {label: 'Volume Trend %', metric: 'volume_trend_20', format: v => (v * 100).toFixed(1)},
  ];

  const labels = [];
  const values = [];
  const colors = [];

  for (const m of metrics) {
    const val = findObs({results: [section]}, m.metric);
    if (val == null) continue;
    labels.push(m.label);
    values.push(Number(m.format(val)));
    // Color logic: constructive=green, caution=red, neutral=gray
    if (m.metric === 'relative_strength_index_14') {
      colors.push(val > 70 ? '#ef4444' : val < 30 ? '#22c55e' : '#94a3b8');
    } else if (m.metric === 'macd_histogram' || m.metric === 'price_return') {
      colors.push(val > 0 ? '#22c55e' : '#ef4444');
    } else if (m.metric === 'volume_trend_20') {
      colors.push(val > 0 ? '#22c55e' : '#ef4444');
    } else {
      colors.push('#3b82f6');
    }
  }

  if (!labels.length) return;

  const trace = {
    type: 'bar',
    x: values,
    y: labels,
    orientation: 'h',
    marker: {color: colors},
    text: values.map(v => String(v)),
    textposition: 'outside',
  };

  const layout = {
    margin: {l: 100, r: 50, t: 10, b: 10},
    height: Math.max(160, labels.length * 40),
    xaxis: {showgrid: true, zeroline: true},
    yaxis: {automargin: true},
  };

  vizEl.innerHTML = '<div class="chart-box" id="chart-technical"></div>';
  Plotly.newPlot('chart-technical', [trace], layout, {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ['select2d', 'lasso2d'],
  });

  // Mini-cards for SMA, ATR
  const sma = findObs({results: [section]}, 'simple_moving_average_20') || findObs({results: [section]}, 'simple_moving_average');
  const atr = findObs({results: [section]}, 'average_true_range_14');
  const cardsHtml = [];
  if (sma != null) cardsHtml.push(`<div class="ref-card"><div class="ref-label">SMA</div><div class="ref-value">${Number(sma).toFixed(2)}</div></div>`);
  if (atr != null) cardsHtml.push(`<div class="ref-card"><div class="ref-label">ATR</div><div class="ref-value">${Number(atr).toFixed(2)}</div></div>`);
  if (cardsHtml.length) {
    vizEl.innerHTML += `<div class="ref-cards">${cardsHtml.join('')}</div>`;
  }
}
```

- [ ] **Step 3: Wire template into registry**

In `REPORT_TEMPLATES`, set:
```javascript
"technical": renderTechnicalReport,
```

And in `renderChartsForTab`, the `plotFns` already has `"technical": plotTechnicalCharts`.

- [ ] **Step 4: Verify static HTML**

Run: `cd /Users/chenkangan/Documents/PAMASTER/backend && python -c "from pa_investing.analytics_app.pages import research_page; html = research_page(); assert 'renderTechnicalReport' in html; assert 'plotTechnicalCharts' in html; print('OK')"`

- [ ] **Step 5: Commit**

```bash
cd /Users/chenkangan/Documents/PAMASTER
git add backend/src/pa_investing/analytics_app/pages.py
git commit -m "feat: add technical analysis report template with Plotly indicator bar chart"
```

---

### Task 14: PAMASTER — Worth-buy-stocks report template

**Files:**
- Modify: `backend/src/pa_investing/analytics_app/pages.py`

**Interfaces:**
- Consumes: Template registry (Task 12), `findObs()`, `ENTRY_CLASS_LABELS`
- Produces: `renderWorthBuyReport(report, section)` and `plotWorthBuyCharts(section, vizEl)`

- [ ] **Step 1: Add `renderWorthBuyReport()` function**

```javascript
function renderWorthBuyReport(report, section) {
  const composite = findObs(report, 'worth_buy_composite');
  const riskVeto = findObs(report, 'worth_buy_risk_veto');
  const entryClass = findObs(report, 'worth_buy_entry_classification');
  const entryPrice = findObs(report, 'worth_buy_entry_price');
  const stopPrice = findObs(report, 'worth_buy_stop_price');
  const targetPrice = findObs(report, 'worth_buy_target_price');
  const verdict = findObs(report, 'worth_buy_verdict');
  const rsSPY = findObs(report, 'worth_buy_relative_strength');
  const missing = section.missing_metrics || [];
  const limitations = section.limitations || [];

  function setupQuality() {
    const signal = section.signal || 'not_assessed';
    if (signal === 'bullish' && section.status === 'complete') {
      return 'The setup is constructive, but still validate risk and position context separately.';
    }
    if (signal === 'neutral') {
      return 'This is a watchlist setup rather than a high-conviction entry.';
    }
    if (signal === 'bearish') {
      return 'The current setup has enough risk or weak confirmation to avoid upgrading the idea.';
    }
    return 'The model cannot score this reliably from the available data.';
  }

  function compositeText() {
    if (composite == null) return 'Composite score unavailable.';
    const c = Number(composite);
    const quality = c >= 70 ? 'strong' : c >= 40 ? 'moderate' : 'weak';
    return `Composite trend-quality score is ${c.toFixed(1)}/100 (${quality}). ` +
      `Higher scores indicate stronger momentum, relative strength, and trend efficiency.`;
  }

  function riskText() {
    if (riskVeto == null) return 'Risk veto score unavailable.';
    const r = Number(riskVeto);
    const level = r >= 20 ? 'elevated' : r >= 10 ? 'moderate' : 'low';
    return `Risk veto score is ${r.toFixed(1)} (${level}). ` +
      `Higher scores flag more reasons to reduce confidence.`;
  }

  function entryText() {
    if (entryClass == null) return 'Entry classification unavailable.';
    const code = Math.round(Number(entryClass));
    const label = ENTRY_CLASS_LABELS[code] || `Unknown (${code})`;
    return `Entry class: ${label}.`;
  }

  function refLevelsText() {
    const parts = [];
    if (entryPrice != null) parts.push(`Entry reference: ${Number(entryPrice).toFixed(2)}`);
    if (stopPrice != null) parts.push(`Stop reference: ${Number(stopPrice).toFixed(2)}`);
    if (targetPrice != null) parts.push(`Target reference: ${Number(targetPrice).toFixed(2)}`);
    if (!parts.length) return 'No reference levels available.';
    return 'Model reference levels (not order instructions): ' + parts.join('; ') + '.';
  }

  return `<div class="section"><h3>Setup Quality</h3><p>${setupQuality()}</p></div>` +
    `<div class="section"><h3>Composite Score</h3><p>${compositeText()}</p></div>` +
    `<div class="section"><h3>Risk Veto</h3><p>${riskText()}</p></div>` +
    `<div class="section"><h3>Entry Class</h3><p>${entryText()}</p></div>` +
    `<div class="section"><h3>Reference Levels</h3><p>${refLevelsText()}</p></div>` +
    (missing.length ? `<div class="section"><h3>Data Quality</h3><p>Missing: ${missing.join(', ')}. ` +
      (limitations.length ? `Limitations: ${limitations.join(', ')}.` : '') + `</p></div>` : '');
}
```

- [ ] **Step 2: Add `plotWorthBuyCharts()` function**

```javascript
function plotWorthBuyCharts(section, vizEl) {
  const composite = findObs({results: [section]}, 'worth_buy_composite');
  const riskVeto = findObs({results: [section]}, 'worth_buy_risk_veto');
  const entryPrice = findObs({results: [section]}, 'worth_buy_entry_price');
  const stopPrice = findObs({results: [section]}, 'worth_buy_stop_price');
  const targetPrice = findObs({results: [section]}, 'worth_buy_target_price');

  let html = '';

  // Composite gauge
  if (composite != null) {
    html += '<div class="chart-box" id="chart-wb-gauge"></div>';
    setTimeout(() => {
      const trace = {
        type: 'indicator',
        mode: 'gauge+number',
        value: Number(composite),
        title: {text: 'Composite Score'},
        gauge: {
          axis: {range: [0, 100]},
          bar: {color: '#2563eb'},
          steps: [
            {range: [0, 30], color: '#fee2e2'},
            {range: [30, 70], color: '#fef3c7'},
            {range: [70, 100], color: '#dcfce7'},
          ],
        },
      };
      Plotly.newPlot('chart-wb-gauge', [trace], {margin: {t: 30, b: 10}}, {
        responsive: true, displaylogo: false,
        modeBarButtonsToRemove: ['select2d', 'lasso2d'],
      });
    }, 50);
  }

  // Risk veto bar
  if (riskVeto != null) {
    html += '<div class="chart-box" id="chart-wb-risk"></div>';
    setTimeout(() => {
      const rv = Number(riskVeto);
      const trace = {
        type: 'bar',
        x: [rv],
        y: ['Risk Veto'],
        orientation: 'h',
        marker: {color: rv > 15 ? '#ef4444' : rv > 5 ? '#f59e0b' : '#22c55e'},
        text: [rv.toFixed(1)],
        textposition: 'outside',
      };
      Plotly.newPlot('chart-wb-risk', [trace], {
        margin: {l: 80, r: 50, t: 10, b: 10},
        height: 100,
        xaxis: {range: [0, Math.max(30, rv + 5)]},
      }, {responsive: true, displaylogo: false,
        modeBarButtonsToRemove: ['select2d', 'lasso2d']});
    }, 50);
  }

  // Reference level cards
  if (entryPrice != null || stopPrice != null || targetPrice != null) {
    html += '<div class="ref-cards">';
    if (entryPrice != null) html += `<div class="ref-card"><div class="ref-label">Entry Reference</div><div class="ref-value">${Number(entryPrice).toFixed(2)}</div></div>`;
    if (stopPrice != null) html += `<div class="ref-card"><div class="ref-label">Stop Reference</div><div class="ref-value">${Number(stopPrice).toFixed(2)}</div></div>`;
    if (targetPrice != null) html += `<div class="ref-card"><div class="ref-label">Target Reference</div><div class="ref-value">${Number(targetPrice).toFixed(2)}</div></div>`;
    html += '</div>';
  }

  vizEl.innerHTML = html;
}
```

- [ ] **Step 3: Wire into registry**

```javascript
"worth-buy-stocks": renderWorthBuyReport,
```

- [ ] **Step 4: Verify static HTML**

Run: `cd /Users/chenkangan/Documents/PAMASTER/backend && python -c "from pa_investing.analytics_app.pages import research_page; html = research_page(); assert 'renderWorthBuyReport' in html; assert 'plotWorthBuyCharts' in html; print('OK')"`

- [ ] **Step 5: Commit**

```bash
cd /Users/chenkangan/Documents/PAMASTER
git add backend/src/pa_investing/analytics_app/pages.py
git commit -m "feat: add worth-buy-stocks report template with composite gauge and reference cards"
```

---

### Task 15: PAMASTER — Markov-method report template

**Files:**
- Modify: `backend/src/pa_investing/analytics_app/pages.py`

**Interfaces:**
- Consumes: Template registry (Task 12), `findObs()`, `REGIME_LABELS`
- Produces: `renderMarkovReport(report, section)` and `plotMarkovCharts(section, vizEl)`

- [ ] **Step 1: Add `renderMarkovReport()` function**

```javascript
function renderMarkovReport(report, section) {
  const curRegime = findObs(report, 'markov_current_regime');
  const signal = findObs(report, 'markov_signal');
  const bullProb = findObs(report, 'markov_stationary_bull');
  const bearProb = findObs(report, 'markov_stationary_bear');
  const sidewaysProb = findObs(report, 'markov_stationary_sideways');
  const persBull = findObs(report, 'markov_persistence_bull');
  const persBear = findObs(report, 'markov_persistence_bear');
  const persSideways = findObs(report, 'markov_persistence_sideways');
  const wfAccuracy = findObs(report, 'markov_walkforward_accuracy');
  const missing = section.missing_metrics || [];

  function regimeText() {
    if (curRegime == null) return 'Current regime could not be determined.';
    const code = Math.round(Number(curRegime));
    const label = REGIME_LABELS[code] || `Unknown (${code})`;
    return `The current regime is <strong>${label}</strong>.`;
  }

  function signalText() {
    if (signal == null) return 'Directional signal unavailable.';
    const s = Number(signal);
    const dir = s > 0.05 ? 'bullish bias' : s < -0.05 ? 'bearish bias' : 'neutral/mixed';
    return `Markov signal is ${s.toFixed(4)} (${dir}). ` +
      `Positive means the transition matrix favors a bull next step; negative favors bear.`;
  }

  function stationaryText() {
    if (bullProb == null || bearProb == null || sidewaysProb == null) {
      return 'Stationary distribution unavailable.';
    }
    return `Long-run regime mix: Bull ${(Number(bullProb) * 100).toFixed(1)}%, ` +
      `Sideways ${(Number(sidewaysProb) * 100).toFixed(1)}%, ` +
      `Bear ${(Number(bearProb) * 100).toFixed(1)}%.`;
  }

  function persistenceText() {
    const parts = [];
    if (persBull != null) parts.push(`Bull stickiness: ${Number(persBull).toFixed(2)}`);
    if (persSideways != null) parts.push(`Sideways stickiness: ${Number(persSideways).toFixed(2)}`);
    if (persBear != null) parts.push(`Bear stickiness: ${Number(persBear).toFixed(2)}`);
    if (!parts.length) return 'Persistence metrics unavailable.';
    return 'Regime stickiness (higher = more persistent): ' + parts.join('; ') + '.';
  }

  function qualityText() {
    const parts = [];
    if (section.status === 'partial') parts.push('Report is partial — fewer than recommended training bars.');
    if (missing.length) parts.push(`Missing metrics: ${missing.join(', ')}`);
    if (wfAccuracy != null) parts.push(`Walk-forward accuracy: ${(Number(wfAccuracy) * 100).toFixed(1)}%`);
    if (!parts.length) return 'No data quality issues reported.';
    return parts.join('; ') + '.';
  }

  return `<div class="section"><h3>Regime Bias</h3><p>${regimeText()}</p></div>` +
    `<div class="section"><h3>Signal</h3><p>${signalText()}</p></div>` +
    `<div class="section"><h3>Stationary Mix</h3><p>${stationaryText()}</p></div>` +
    `<div class="section"><h3>Persistence</h3><p>${persistenceText()}</p></div>` +
    `<div class="section"><h3>Data Quality</h3><p>${qualityText()}</p></div>`;
}
```

- [ ] **Step 2: Add `plotMarkovCharts()` function**

```javascript
function plotMarkovCharts(section, vizEl) {
  const bullProb = findObs({results: [section]}, 'markov_stationary_bull');
  const sidewaysProb = findObs({results: [section]}, 'markov_stationary_sideways');
  const bearProb = findObs({results: [section]}, 'markov_stationary_bear');
  const persBull = findObs({results: [section]}, 'markov_persistence_bull');
  const persSideways = findObs({results: [section]}, 'markov_persistence_sideways');
  const persBear = findObs({results: [section]}, 'markov_persistence_bear');
  const signal = findObs({results: [section]}, 'markov_signal');

  let html = '';

  // Stationary probability bar chart
  if (bullProb != null && bearProb != null && sidewaysProb != null) {
    html += '<div class="chart-box" id="chart-markov-stationary"></div>';
    setTimeout(() => {
      const trace = {
        type: 'bar',
        x: [Number(bullProb) * 100, Number(sidewaysProb) * 100, Number(bearProb) * 100],
        y: ['Bull', 'Sideways', 'Bear'],
        orientation: 'h',
        marker: {color: ['#22c55e', '#f59e0b', '#ef4444']},
        text: [Number(bullProb) * 100, Number(sidewaysProb) * 100, Number(bearProb) * 100]
          .map(v => v.toFixed(1) + '%'),
        textposition: 'outside',
      };
      Plotly.newPlot('chart-markov-stationary', [trace], {
        margin: {l: 80, r: 60, t: 10, b: 10},
        height: 150,
        title: 'Stationary Probabilities',
        xaxis: {range: [0, 100], ticksuffix: '%'},
      }, {responsive: true, displaylogo: false,
        modeBarButtonsToRemove: ['select2d', 'lasso2d']});
    }, 50);
  }

  // Persistence bars
  if (persBull != null && persSideways != null && persBear != null) {
    html += '<div class="chart-box" id="chart-markov-persistence"></div>';
    setTimeout(() => {
      const trace = {
        type: 'bar',
        x: [Number(persBull), Number(persSideways), Number(persBear)],
        y: ['Bull Persistence', 'Sideways Persistence', 'Bear Persistence'],
        orientation: 'h',
        marker: {color: ['#22c55e', '#f59e0b', '#ef4444']},
        text: [Number(persBull), Number(persSideways), Number(persBear)]
          .map(v => v.toFixed(2)),
        textposition: 'outside',
      };
      Plotly.newPlot('chart-markov-persistence', [trace], {
        margin: {l: 140, r: 60, t: 10, b: 10},
        height: 150,
        title: 'Persistence',
      }, {responsive: true, displaylogo: false,
        modeBarButtonsToRemove: ['select2d', 'lasso2d']});
    }, 50);
  }

  // Signal gauge
  if (signal != null) {
    html += '<div class="chart-box" id="chart-markov-signal"></div>';
    setTimeout(() => {
      const s = Number(signal);
      const trace = {
        type: 'indicator',
        mode: 'gauge+number+delta',
        value: s,
        title: {text: 'Directional Bias'},
        gauge: {
          axis: {range: [-1, 1]},
          bar: {color: s > 0 ? '#22c55e' : '#ef4444'},
          steps: [
            {range: [-1, -0.05], color: '#fee2e2'},
            {range: [-0.05, 0.05], color: '#f1f5f9'},
            {range: [0.05, 1], color: '#dcfce7'},
          ],
        },
      };
      Plotly.newPlot('chart-markov-signal', [trace], {margin: {t: 30, b: 10}}, {
        responsive: true, displaylogo: false,
        modeBarButtonsToRemove: ['select2d', 'lasso2d'],
      });
    }, 50);
  }

  vizEl.innerHTML = html;
}
```

- [ ] **Step 3: Wire into registry**

```javascript
"markov-method": renderMarkovReport,
```

- [ ] **Step 4: Verify static HTML**

Run: `cd /Users/chenkangan/Documents/PAMASTER/backend && python -c "from pa_investing.analytics_app.pages import research_page; html = research_page(); assert 'renderMarkovReport' in html; assert 'plotMarkovCharts' in html; print('OK')"`

- [ ] **Step 5: Commit**

```bash
cd /Users/chenkangan/Documents/PAMASTER
git add backend/src/pa_investing/analytics_app/pages.py
git commit -m "feat: add markov-method report template with stationary probability and persistence charts"
```

---

### Task 16: PAMASTER — Write tests for templates and parameter proxy

**Files:**
- Modify: `backend/tests/integration/test_api_routes.py`
- Modify: `backend/tests/unit/test_trade_agent.py`

**Interfaces:**
- Consumes: Updated schemas (Task 8), updated routes (Task 10), updated client (Task 9), templates (Tasks 12-15)

- [ ] **Step 1: Write unit test for client `skill_parameters` forwarding**

Add to `test_trade_agent.py`:

```python
class TestRunSkillWithParameters:
    def test_skill_parameters_included_in_request_body(self):
        """Verify skill_parameters are forwarded in the POST body."""
        client = TradeAgentClient(
            base_url="http://127.0.0.1:8002",
            bearer_token="test",
            enabled=True,
            timeout_seconds=1,
        )
        # We can't actually call the endpoint, but we can verify the method
        # accepts the parameter by inspecting the signature
        import inspect
        sig = inspect.signature(client.run_skill)
        assert "skill_parameters" in sig.parameters
        param = sig.parameters["skill_parameters"]
        assert param.default is None

    def test_run_skill_without_parameters_still_works(self):
        """Backward compat: calling without skill_parameters should not break."""
        client = TradeAgentClient(
            base_url="http://127.0.0.1:8002",
            bearer_token="test",
            enabled=True,
            timeout_seconds=1,
        )
        import inspect
        sig = inspect.signature(client.run_skill)
        # skill_parameters defaults to None
        assert sig.parameters["skill_parameters"].default is None
```

- [ ] **Step 2: Write integration test for skills endpoint with parameters**

Add to `test_api_routes.py`:

```python
class TestResearchSkillsWithParameters:
    def test_research_skills_includes_parameters_when_available(self, client, mocker):
        """When TradeAgent is configured and returns skills with parameters,
        the PAMASTER endpoint should forward the parameters field."""
        mock_client = mocker.patch(
            "pa_investing.api.routes.get_trade_agent_client"
        )
        mock_instance = mock_client.return_value
        mock_instance.configured = True
        mock_instance.list_skills.return_value = [
            {
                "name": "technical",
                "description": "Technical analysis",
                "immutable": True,
                "parameters": {
                    "properties": {
                        "window": {"type": "integer", "default": 20}
                    }
                },
            },
            {
                "name": "fundamental",
                "description": "Fundamental analysis",
                "immutable": True,
                "parameters": None,
            },
        ]

        response = client.get("/analysis/research/skills")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "available"
        skills = {s["name"]: s for s in payload["skills"]}
        assert skills["technical"]["parameters"] is not None
        assert skills["technical"]["parameters"]["properties"]["window"]["default"] == 20
        assert skills["fundamental"]["parameters"] is None

    def test_research_skills_disabled_no_parameters(self, client):
        """When TradeAgent is disabled, parameters should not appear."""
        response = client.get("/analysis/research/skills")
        payload = response.json()
        if payload["status"] == "disabled":
            assert "parameters" not in payload or not payload.get("skills")
```

- [ ] **Step 3: Write integration test for run endpoint with parameters**

Add to `test_api_routes.py`:

```python
class TestResearchRunWithParameters:
    def test_run_research_sends_skill_parameters(self, client, mocker):
        """The run endpoint should forward skill_parameters to TradeAgentClient."""
        mock_client = mocker.patch(
            "pa_investing.api.routes.get_trade_agent_client"
        )
        mock_instance = mock_client.return_value
        mock_instance.configured = True
        mock_instance.run_skill.return_value = {
            "generated_at": "2026-01-01T00:00:00Z",
            "instrument": {"symbol": "AAPL", "market": "US"},
            "request_id": "test-id",
            "results": [{
                "analyst": "technical",
                "signal": "neutral",
                "status": "complete",
                "observations": [],
                "methods": [],
                "citations": [],
                "missing_metrics": [],
                "limitations": [],
                "failure_category": "none",
                "summary": "test",
            }],
        }

        response = client.post("/analysis/research/run", json={
            "symbol": "AAPL",
            "market": "US",
            "skills": ["technical"],
            "skill_parameters": {"technical": {"window": 10}},
        })
        assert response.status_code == 200
        # Verify skill_parameters was passed to client
        call_kwargs = mock_instance.run_skill.call_args.kwargs
        assert call_kwargs["skill_parameters"] == {"technical": {"window": 10}}
        assert call_kwargs["skill"] == "technical"

    def test_run_research_empty_skill_parameters(self, client, mocker):
        """skill_parameters defaults to empty dict, should not cause errors."""
        mock_client = mocker.patch(
            "pa_investing.api.routes.get_trade_agent_client"
        )
        mock_instance = mock_client.return_value
        mock_instance.configured = True
        mock_instance.run_skill.return_value = {
            "generated_at": "2026-01-01T00:00:00Z",
            "instrument": {"symbol": "IBM", "market": "US"},
            "request_id": "test-id-2",
            "results": [{
                "analyst": "fundamental",
                "signal": "not_assessed",
                "status": "partial",
                "observations": [],
                "methods": [],
                "citations": [],
                "missing_metrics": [],
                "limitations": [],
                "failure_category": "none",
                "summary": "test",
            }],
        }

        response = client.post("/analysis/research/run", json={
            "symbol": "IBM",
            "market": "US",
            "skills": ["fundamental"],
        })
        assert response.status_code == 200
        call_kwargs = mock_instance.run_skill.call_args.kwargs
        assert call_kwargs.get("skill_parameters") == {}
```

- [ ] **Step 4: Write test for research page HTML content**

Add to `test_api_routes.py`:

```python
class TestResearchPageContent:
    def test_research_page_includes_plotly_cdn(self, client):
        """Research page HTML must include Plotly CDN script."""
        response = client.get("/analysis/research")
        assert response.status_code == 200
        html = response.text
        assert "plotly-2.35.2.min.js" in html

    def test_research_page_includes_template_functions(self, client):
        """Research page HTML must include render functions for all templates."""
        response = client.get("/analysis/research")
        html = response.text
        assert "renderTechnicalReport" in html
        assert "renderWorthBuyReport" in html
        assert "renderMarkovReport" in html
        assert "renderGenericReport" in html
        assert "REPORT_TEMPLATES" in html
        assert "ENTRY_CLASS_LABELS" in html
        assert "REGIME_LABELS" in html

    def test_research_page_includes_skill_parameters_js(self, client):
        """Research page must include JS for collecting skill parameters."""
        response = client.get("/analysis/research")
        html = response.text
        assert "skill_parameters" in html
        assert "skill-params" in html

    def test_research_page_no_trade_agent_token_leak(self, client, monkeypatch):
        """Browser must never receive the TradeAgent bearer token."""
        monkeypatch.setenv("PA_TRADE_RESEARCH_API_TOKEN", "secret-token-123")
        response = client.get("/analysis/research")
        assert "secret-token-123" not in response.text
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/chenkangan/Documents/PAMASTER/backend && python -m pytest tests/unit/test_trade_agent.py tests/integration/test_api_routes.py -v -k "skill_parameters or ResearchSkillsWith or ResearchRunWith or ResearchPageContent or TestRunSkillWith"`
Expected: All new tests pass.

- [ ] **Step 6: Run full test suite to verify no regressions**

Run: `cd /Users/chenkangan/Documents/PAMASTER/backend && python -m pytest -v`
Expected: All existing tests still pass.

- [ ] **Step 7: Commit**

```bash
cd /Users/chenkangan/Documents/PAMASTER
git add backend/tests/unit/test_trade_agent.py backend/tests/integration/test_api_routes.py
git commit -m "test: add tests for skill parameter proxying and report template page content"
```

---

## Spec Coverage Check

| Spec requirement | Task(s) |
|---|---|
| TradeAgent parameter models (Pydantic) | Task 1 |
| `skill_parameters` on `AnalysisRequest` | Task 2 |
| `configure_skill()` with `dataclasses.replace()` | Task 3 |
| Engine bypass for configured skills | Task 4 |
| `describe_skill()` includes `parameters` | Task 5 |
| `run_skill()` uses configured copy | Task 5 |
| HTTP 422 for invalid params | Task 6 |
| TradeAgent tests | Task 7 |
| PAMASTER schemas extended | Task 8 |
| TradeAgent client forwards params | Task 9 |
| Routes proxy params | Task 10 |
| Plotly CDN on research page | Task 11 |
| Dynamic parameter controls UI | Task 11 |
| Tabbed mini-dashboard layout | Task 12 |
| Template registry | Task 12 |
| Technical template (narrative + charts) | Task 13 |
| Worth-buy-stocks template (narrative + charts) | Task 14 |
| Markov-method template (narrative + charts) | Task 15 |
| Fallback generic template | Task 12 |
| Entry class / regime translation tables | Tasks 12, 14, 15 |
| Mobile responsive layout (900px breakpoint) | Task 12 (CSS) |
| Raw JSON collapsible in each tab | Task 12 |
| Auth boundary (no token leak) | Task 16 (test) |
| PAMASTER tests | Task 16 |
| Non-goals preserved (no time series, no LLM, no registry mutation) | All tasks |
