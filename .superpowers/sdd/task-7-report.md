## What you implemented

- Added deterministic sizing package at `backend/src/pa_investing/sizing/` with:
  - `SizingRecommendation`
  - `MaxNavWeightSizingModel.recommend_reduction(position, portfolio_nav)`
- Added signal package at `backend/src/pa_investing/signals/` with:
  - `StopReferenceRule.evaluate(position, stop_price, portfolio_nav)`
  - `SignalService.evaluate_stop_rules(positions, stop_prices, portfolio_nav)`
- Added unit tests covering:
  - NAV-weight reduction recommendation text and quantity
  - Stop/reference breach signal creation and deterministic recommendation wiring

## What you tested and test results

- `./.venv/bin/pytest tests/unit/test_sizing.py tests/unit/test_signals.py -v`
  - Result: `2 passed`
- `./.venv/bin/ruff check .`
  - Result: `All checks passed!`

## TDD Evidence

### RED command

```bash
cd backend
./.venv/bin/pytest tests/unit/test_sizing.py tests/unit/test_signals.py -v
```

### Relevant failing output before implementation

```text
E   ModuleNotFoundError: No module named 'pa_investing.sizing'
E   ModuleNotFoundError: No module named 'pa_investing.signals'
```

This was the expected RED state because Task 7 required new sizing and signal modules that did not exist yet.

### GREEN command

```bash
cd backend
./.venv/bin/pytest tests/unit/test_sizing.py tests/unit/test_signals.py -v
./.venv/bin/ruff check .
```

### Relevant passing output after implementation

```text
tests/unit/test_sizing.py::test_max_nav_weight_model_recommends_share_reduction PASSED
tests/unit/test_signals.py::test_stop_reference_rule_creates_signal_when_price_breaches_stop PASSED

============================== 2 passed in 0.08s ===============================
All checks passed!
```

## Files changed

- `backend/src/pa_investing/sizing/__init__.py`
- `backend/src/pa_investing/sizing/models.py`
- `backend/src/pa_investing/signals/__init__.py`
- `backend/src/pa_investing/signals/rules.py`
- `backend/src/pa_investing/signals/service.py`
- `backend/tests/unit/test_sizing.py`
- `backend/tests/unit/test_signals.py`
- `.superpowers/sdd/task-7-report.md`

## Self-review findings

- Implementation matches the Task 7 brief and stays scoped to deterministic sizing, signal rules, and the service wrapper.
- No later-phase integrations were added.
- Verification is limited to the task-required focused tests plus repo linting; no broader backend test sweep was requested or run.

## Any issues or concerns

- No functional concerns with the scoped Task 7 work.
- Running pytest created untracked `__pycache__` directories in the workspace; they were not staged or modified further.

---

## Task 7 Review Fix: ignore invalid prices in stop signals

### What changed

- Updated `StopReferenceRule.evaluate()` to return `None` when `position.latest_price` is `None`, `0`, or negative.
- Kept the existing stop-breach signal behavior unchanged for positive prices at or below the stop price.
- Added a regression test covering `None`, zero, and negative latest prices.

### TDD Evidence

#### RED command

```bash
cd backend
./.venv/bin/pytest tests/unit/test_signals.py -v
```

#### Relevant RED output

```text
tests/unit/test_signals.py::test_stop_reference_rule_ignores_invalid_latest_prices FAILED

E           AssertionError: assert Signal(... message='AAPL price 0 breached stop/reference level 95.' ...) is None
```

The new regression test failed against the pre-fix implementation because `latest_price=0` still produced a HIGH stop-breach signal.

#### GREEN commands

```bash
cd backend
./.venv/bin/pytest tests/unit/test_signals.py -v
./.venv/bin/pytest tests/unit/test_sizing.py tests/unit/test_signals.py -v
./.venv/bin/ruff check .
```

#### Relevant GREEN output

```text
tests/unit/test_signals.py::test_stop_reference_rule_creates_signal_when_price_breaches_stop PASSED
tests/unit/test_signals.py::test_stop_reference_rule_ignores_invalid_latest_prices PASSED
tests/unit/test_signal_service_returns_signals_only_for_matching_breached_stops PASSED

============================== 3 passed in 0.06s ===============================

tests/unit/test_sizing.py::test_max_nav_weight_model_validates_weight_range PASSED
tests/unit/test_sizing.py::test_max_nav_weight_model_recommends_share_reduction PASSED
tests/unit/test_sizing.py::test_max_nav_weight_model_returns_zero_reduction_for_missing_or_non_positive_price[None] PASSED
tests/unit/test_sizing.py::test_max_nav_weight_model_returns_zero_reduction_for_missing_or_non_positive_price[latest_price1] PASSED
tests/unit/test_sizing.py::test_max_nav_weight_model_returns_zero_reduction_for_missing_or_non_positive_price[latest_price2] PASSED
tests/unit/test_signals.py::test_stop_reference_rule_creates_signal_when_price_breaches_stop PASSED
tests/unit/test_signals.py::test_stop_reference_rule_ignores_invalid_latest_prices PASSED
tests/unit/test_signal_service_returns_signals_only_for_matching_breached_stops PASSED

============================== 8 passed in 0.08s ===============================
All checks passed!
```

---

## Task 7 Fix Pass: deterministic sizing review fixes

### What changed

- Added input validation to `MaxNavWeightSizingModel` so `max_weight` must be `> 0` and `<= 1`, raising `ValueError` otherwise.
- Hardened `recommend_reduction()` to return a zero-reduction recommendation for missing, zero, or negative `latest_price` values instead of dividing by an invalid price.
- Added service-level coverage proving `SignalService.evaluate_stop_rules()` only emits signals for positions whose symbols have stop prices and whose latest price breaches the configured stop.

### TDD Evidence

#### RED command

```bash
cd backend
./.venv/bin/pytest tests/unit/test_sizing.py tests/unit/test_signals.py -v
```

#### Relevant RED output

```text
tests/unit/test_sizing.py::test_max_nav_weight_model_validates_weight_range FAILED
tests/unit/test_sizing.py::test_max_nav_weight_model_returns_zero_reduction_for_missing_or_non_positive_price[None] FAILED
tests/unit/test_sizing.py::test_max_nav_weight_model_returns_zero_reduction_for_missing_or_non_positive_price[latest_price1] FAILED
tests/unit/test_sizing.py::test_max_nav_weight_model_returns_zero_reduction_for_missing_or_non_positive_price[latest_price2] FAILED

E   AssertionError: Expected ValueError for max_weight=-0.01
E   AssertionError: assert 'No reduction for AAPL; missing price or NAV.' == 'No reduction for AAPL; missing, zero, or negative latest price.'
E   decimal.InvalidOperation: [<class 'decimal.DivisionUndefined'>]
E   AssertionError: assert 'Reduce -0 shares to bring AAPL back to 10.00% of NAV.' == 'No reduction for AAPL; missing, zero, or negative latest price.'
```

The new `SignalService` aggregation test passed in RED, which confirmed that coverage gap as requested without requiring a production change there.

#### GREEN commands

```bash
cd backend
./.venv/bin/pytest tests/unit/test_sizing.py tests/unit/test_signals.py -v
./.venv/bin/ruff check .
```

#### Relevant GREEN output

```text
tests/unit/test_sizing.py::test_max_nav_weight_model_validates_weight_range PASSED
tests/unit/test_sizing.py::test_max_nav_weight_model_recommends_share_reduction PASSED
tests/unit/test_sizing.py::test_max_nav_weight_model_returns_zero_reduction_for_missing_or_non_positive_price[None] PASSED
tests/unit/test_sizing.py::test_max_nav_weight_model_returns_zero_reduction_for_missing_or_non_positive_price[latest_price1] PASSED
tests/unit/test_sizing.py::test_max_nav_weight_model_returns_zero_reduction_for_missing_or_non_positive_price[latest_price2] PASSED
tests/unit/test_signals.py::test_stop_reference_rule_creates_signal_when_price_breaches_stop PASSED
tests/unit/test_signals.py::test_signal_service_returns_signals_only_for_matching_breached_stops PASSED

============================== 7 passed in 0.09s ===============================
All checks passed!
```
