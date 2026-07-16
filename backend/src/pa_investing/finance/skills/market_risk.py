from decimal import Decimal

from pa_investing.finance.indicators import (
    annualized_volatility,
    bars_frame,
    decimal_metric,
)
from pa_investing.finance.models import (
    AnalysisRequest,
    Direction,
    ExecutionMode,
    Finding,
    FindingSeverity,
    SkillMetadata,
    SkillResult,
    SkillStatus,
)
from pa_investing.market_data.history.models import HistoricalDataset


class MarketRiskSnapshotSkill:
    metadata = SkillMetadata(
        skill_id="market_risk_snapshot.v1",
        name="Market risk snapshot",
        description="Volatility, drawdown, and abnormal daily-move evidence.",
        execution_mode=ExecutionMode.DETERMINISTIC,
        min_bars=21,
        default_thresholds={
            "drawdown_watch": Decimal("-0.08"),
            "drawdown_attention": Decimal("-0.15"),
            "volatility_watch": Decimal("0.25"),
            "volatility_attention": Decimal("0.40"),
            "daily_move_watch": Decimal("0.05"),
        },
    )

    def run(
        self,
        request: AnalysisRequest,
        dataset: HistoricalDataset,
    ) -> SkillResult:
        bars = dataset.bars
        if len(bars) < self.metadata.min_bars:
            return SkillResult(
                skill_id=self.metadata.skill_id,
                status=SkillStatus.PARTIAL,
                metrics={"bar_count": len(bars)},
                warnings=["Market risk snapshot requires at least 21 completed daily bars."],
            )
        thresholds = {
            **self.metadata.default_thresholds,
            **request.threshold_overrides.get(self.metadata.skill_id, {}),
        }
        close = bars_frame(bars)["close"]
        peak = float(close.max())
        latest = float(close.iloc[-1])
        drawdown = latest / peak - 1
        daily_move = latest / float(close.iloc[-2]) - 1
        volatility = annualized_volatility(close, 20)
        drawdown_metric = decimal_metric(drawdown)
        daily_move_metric = decimal_metric(daily_move)
        volatility_metric = decimal_metric(volatility)
        findings: list[Finding] = []

        if drawdown_metric <= thresholds["drawdown_attention"]:
            findings.append(
                Finding(
                    code="material_drawdown",
                    severity=FindingSeverity.ATTENTION,
                    direction=Direction.BEARISH,
                    summary="Price is in a material drawdown from the requested-period peak.",
                    values={"drawdown_from_peak": drawdown_metric},
                )
            )
        elif drawdown_metric <= thresholds["drawdown_watch"]:
            findings.append(
                Finding(
                    code="developing_drawdown",
                    severity=FindingSeverity.WATCH,
                    direction=Direction.BEARISH,
                    summary="Price is meaningfully below the requested-period peak.",
                    values={"drawdown_from_peak": drawdown_metric},
                )
            )

        volatility_severity: FindingSeverity | None = None
        if volatility_metric >= thresholds["volatility_attention"]:
            volatility_severity = FindingSeverity.ATTENTION
        elif volatility_metric >= thresholds["volatility_watch"]:
            volatility_severity = FindingSeverity.WATCH
        if volatility_severity:
            findings.append(
                Finding(
                    code="elevated_volatility",
                    severity=volatility_severity,
                    direction=Direction.NEUTRAL,
                    summary="Twenty-session annualized volatility is elevated.",
                    values={"annualized_volatility_20": volatility_metric},
                )
            )

        if abs(daily_move_metric) >= thresholds["daily_move_watch"]:
            findings.append(
                Finding(
                    code="abnormal_daily_move",
                    severity=FindingSeverity.ATTENTION,
                    direction=(Direction.BULLISH if daily_move_metric > 0 else Direction.BEARISH),
                    summary="The latest completed daily move exceeded the configured threshold.",
                    values={"latest_daily_return": daily_move_metric},
                )
            )
        return SkillResult(
            skill_id=self.metadata.skill_id,
            status=SkillStatus.SUCCESS,
            metrics={
                "annualized_volatility_20": volatility_metric,
                "drawdown_from_peak": drawdown_metric,
                "latest_daily_return": daily_move_metric,
                "period_peak": decimal_metric(peak),
            },
            findings=findings,
        )
