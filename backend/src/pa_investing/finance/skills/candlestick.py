from dataclasses import dataclass
from datetime import date
from decimal import Decimal

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
from pa_investing.market_data.history.models import (
    DailyBar,
    HistoricalDataset,
)


@dataclass(frozen=True)
class _Pattern:
    code: str
    observed_on: date
    direction: Direction
    summary: str


class CandlestickEventsSkill:
    metadata = SkillMetadata(
        skill_id="candlestick_events.v1",
        name="Candlestick events",
        description="Recent candle patterns recorded as supporting evidence.",
        execution_mode=ExecutionMode.DETERMINISTIC,
        min_bars=2,
        default_thresholds={"doji_body_ratio": Decimal("0.1")},
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
                warnings=["Candlestick analysis requires at least two completed daily bars."],
            )
        thresholds = self.metadata.resolve_thresholds(
            request.threshold_overrides.get(self.metadata.skill_id, {})
        )
        if not Decimal("0") <= thresholds["doji_body_ratio"] <= Decimal("1"):
            raise ValueError("doji body ratio must be between 0 and 1")
        patterns = self._detect(bars, thresholds["doji_body_ratio"])
        recent_start = bars[-5].trading_date if len(bars) >= 5 else bars[0].trading_date
        recent = [pattern for pattern in patterns if pattern.observed_on >= recent_start]
        return SkillResult(
            skill_id=self.metadata.skill_id,
            status=SkillStatus.SUCCESS,
            metrics={
                "detected_event_count": len(patterns),
                "recent_event_count": len(recent),
                "surface_window_sessions": 5,
            },
            findings=[
                Finding(
                    code=pattern.code,
                    severity=FindingSeverity.INFO,
                    direction=pattern.direction,
                    summary=pattern.summary,
                    observed_on=pattern.observed_on,
                )
                for pattern in recent
            ],
        )

    @staticmethod
    def _detect(
        bars: list[DailyBar],
        doji_body_ratio: Decimal,
    ) -> list[_Pattern]:
        patterns: list[_Pattern] = []
        for index, current in enumerate(bars):
            candle_range = current.high - current.low
            body = abs(current.close - current.open)
            if candle_range > 0 and body / candle_range <= doji_body_ratio:
                patterns.append(
                    _Pattern(
                        code="doji",
                        observed_on=current.trading_date,
                        direction=Direction.NEUTRAL,
                        summary="A doji indicates short-term indecision.",
                    )
                )
            if index == 0:
                continue
            previous = bars[index - 1]
            previous_bearish = previous.close < previous.open
            previous_bullish = previous.close > previous.open
            current_bullish = current.close > current.open
            current_bearish = current.close < current.open
            if (
                previous_bearish
                and current_bullish
                and current.open <= previous.close
                and current.close >= previous.open
            ):
                patterns.append(
                    _Pattern(
                        code="bullish_engulfing",
                        observed_on=current.trading_date,
                        direction=Direction.BULLISH,
                        summary="A bullish engulfing pattern appeared in the recent window.",
                    )
                )
            elif (
                previous_bullish
                and current_bearish
                and current.open >= previous.close
                and current.close <= previous.open
            ):
                patterns.append(
                    _Pattern(
                        code="bearish_engulfing",
                        observed_on=current.trading_date,
                        direction=Direction.BEARISH,
                        summary="A bearish engulfing pattern appeared in the recent window.",
                    )
                )
        return patterns
