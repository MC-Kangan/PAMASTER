# Claude Code Handover: Skill-Specific Research Reports And Configurable Skill Args

## Summary

Upgrade PAMASTER's Research Playground from raw metric tables into deterministic, skill-specific research reports with Plotly charts and narrative explanations. Start with `technical`, `worth-buy-stocks`, and `markov-method`; all other skills keep the current generic metrics/raw JSON template.

Architecture decision:

- TradeAgent owns computation, sanitized report JSON, and typed skill parameter schemas.
- PAMASTER owns web/iPhone presentation templates, deterministic narratives, and Plotly charts.
- Browser/iPhone still talks only to PAMASTER; PAMASTER proxies to TradeAgent.

Current context:

- PAMASTER repo: `/Users/chenkangan/Documents/PAMASTER`
- TradeAgent repo: `/Users/chenkangan/Documents/TradeAgent`
- PAMASTER Research tab already exists at `/analysis/research`.
- Local ports: PAMASTER `8001`, TradeAgent `8002`.
- TradeAgent explanation references:
  - `docs/EXPLAINING_SKILL_OUTPUTS.md`
  - `skills/technical-analysis/SKILL.md` and `examples.md`
  - `skills/worth-buy-stocks/EXPLANATION.md`
  - `skills/markov-method/EXPLANATION.md`

## Key Changes

### TradeAgent: Typed Skill Args

Add a typed parameter contract exposed through `/skills` and `/skills/{name}`.

- Extend skill description payloads with `parameters`.
- Add parameter definitions for:
  - `technical`: `window` int, default `20`, min `2`, max `252`.
  - `worth-buy-stocks`: `benchmark_symbols` string/list UI-compatible value, default `SPY,QQQ`.
  - `markov-method`: `window` int default `20`, `threshold` float default `0.05`, `min_train` int default `252`, `run_walkforward` bool default `false`.
- Add `skill_parameters: dict[str, dict[str, JsonValue]] = {}` to `AnalysisRequest`.
- In `ResearchApplication.run_skill`, validate parameters for the selected skill and instantiate/configure that skill for the run without mutating the frozen registry.
- Keep queued `/research` unchanged or explicitly ignore `skill_parameters` for queued mode in this slice; PAMASTER uses synchronous `/skills/{name}/run`.
- Add tests proving invalid args fail with `422`, defaults work, and configured args affect output provenance/method windows where applicable.

### PAMASTER: Proxy Args And Dynamic Controls

Update the Research playground API and UI to support skill args.

- Extend `ResearchSkillsResponse` to include each skill's parameter definitions.
- Extend `ResearchRunRequest` with `skill_parameters`.
- Update `TradeAgentClient.run_skill` to send `skill_parameters: {skill_name: {...}}`.
- Render controls dynamically under each selected skill:
  - number inputs for ints/floats;
  - checkbox for bool;
  - text input for benchmark list.
- Preserve manual research/no-current-position mode.
- Do not expose TradeAgent token or direct TradeAgent URL to the browser.

### PAMASTER: Deterministic Report Templates

Replace raw metric-first display with skill-specific report cards.

- Add a client-side template registry keyed by `analyst`:
  - `technical`
  - `worth-buy-stocks`
  - `markov-method`
  - fallback generic template
- Each template must use only sanitized report fields: `status`, `signal`, `missing_metrics`, `limitations`, `observations`, `methods`, `citations`, `failure_category`.
- Do not fetch prices, recalculate indicators, or infer missing metrics.
- Keep raw JSON in a collapsible details section for audit/debugging.

Template behavior:

- `technical`:
  - Narrative sections: Summary, Trend, Momentum, Risk Range, Volume/Data Quality.
  - Plotly mini charts/cards: indicator bars for return, RSI, MACD histogram, volatility, volume trend.
  - Explain missing OHLCV/insufficient history clearly.
- `worth-buy-stocks`:
  - Narrative sections following `EXPLANATION.md`: setup quality, composite score, risk veto, entry class, reference levels.
  - Plotly gauge/bar visuals for composite score and risk veto.
  - Show entry/stop/target as model reference levels, not order instructions.
  - Translate entry class codes `0..5` into labels from the docs.
- `markov-method`:
  - Narrative sections: regime bias, signal, stationary mix, persistence, data quality.
  - Plotly bar chart for stationary bull/sideways/bear probabilities.
  - Plotly heatmap or compact bar group for persistence metrics.
  - Translate regime code `0/1/2` into Bear/Sideways/Bull.
- Fallback:
  - Current metric table plus status, signal, limitations, and raw JSON.

## Test Plan

TradeAgent:

- `/skills` includes parameter definitions for the three starting skills.
- `/skills/technical/run` with `window=10` succeeds and output method/provenance reflects the 10-observation window where applicable.
- `/skills/markov-method/run` with custom `window`, `threshold`, `min_train`, and `run_walkforward` validates and runs.
- Invalid args return `422` without stack traces or secret leakage.
- Existing TradeAgent tests still pass.

PAMASTER:

- Research skills endpoint proxies parameter definitions.
- Research run endpoint sends selected per-skill parameters to TradeAgent.
- UI page contains dynamic parameter controls and Plotly dependency.
- Template tests verify presence of technical, worth-buy-stocks, markov-method, and fallback renderers.
- Error states remain graceful when TradeAgent is disabled, unreachable, or returns skill-level failures.
- Existing auth boundary remains: browser never receives TradeAgent token.

Manual acceptance:

- Refresh `/analysis/research`; skill checkboxes appear with configurable options.
- Run `technical` on AAPL and see narrative plus charted technical factors, not only metric rows.
- Run `worth-buy-stocks` and see verdict, composite, risk veto, entry class, and reference levels.
- Run `markov-method` and see regime explanation plus stationary/persistence visuals.
- Select "Manual research / no current position", enter a symbol/market, and run the same templates without portfolio context.

## Assumptions

- Use Plotly for charts, consistent with PAMASTER's Position Chart page.
- PAMASTER templates are deterministic browser code; no LLM calls are introduced.
- The first slice supports only synchronous manual skill runs.
- Fundamental and filings keep the generic fallback until their own templates are added later.
- Claude Code should implement this in two repos if needed: TradeAgent first for typed args, then PAMASTER for controls/templates.
