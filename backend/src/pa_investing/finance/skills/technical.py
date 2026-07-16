from decimal import Decimal

from pa_investing.finance.indicators import (
    adx,
    bars_frame,
    decimal_metric,
    rsi,
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


class TechnicalSnapshotSkill:
    metadata = SkillMetadata(
        skill_id="technical_snapshot.v1",
        name="Technical snapshot",
        description="Trend, momentum, mean-reversion, and volume evidence.",
        execution_mode=ExecutionMode.DETERMINISTIC,
        min_bars=50,
        default_thresholds={
            "rsi_overbought": Decimal("70"),
            "rsi_oversold": Decimal("30"),
            "volume_ratio_watch": Decimal("1.5"),
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
                metrics={
                    "bar_count": len(bars),
                    "latest_close": bars[-1].close if bars else None,
                },
                warnings=[
                    "Technical snapshot requires at least 50 completed daily bars; "
                    "unreliable findings were omitted."
                ],
            )

        thresholds = self.metadata.resolve_thresholds(
            request.threshold_overrides.get(self.metadata.skill_id, {})
        )
        if not (
            Decimal("0")
            <= thresholds["rsi_oversold"]
            < thresholds["rsi_overbought"]
            <= Decimal("100")
        ):
            raise ValueError(
                "RSI thresholds must satisfy 0 <= oversold < overbought <= 100"
            )
        if thresholds["volume_ratio_watch"] <= 0:
            raise ValueError("volume ratio threshold must be positive")
        frame = bars_frame(bars)
        close = frame["close"]
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        sma_20 = close.rolling(20).mean()
        sma_50 = close.rolling(50).mean()
        rsi_14 = rsi(close, 14)
        adx_14 = adx(frame, 14)
        previous_volume = frame["volume"].iloc[-21:-1].dropna()
        volume_ratio = (
            frame["volume"].iloc[-1] / previous_volume.mean()
            if not previous_volume.empty
            else float("nan")
        )
        latest_close = close.iloc[-1]
        metrics = {
            "latest_close": decimal_metric(latest_close),
            "ema_12": decimal_metric(ema_12.iloc[-1]),
            "ema_26": decimal_metric(ema_26.iloc[-1]),
            "sma_20": decimal_metric(sma_20.iloc[-1]),
            "sma_50": decimal_metric(sma_50.iloc[-1]),
            "rsi_14": decimal_metric(rsi_14.iloc[-1]),
            "adx_14": decimal_metric(adx_14.iloc[-1]),
            "volume_ratio_20": decimal_metric(volume_ratio),
            "close_above_sma_50": bool(latest_close > sma_50.iloc[-1]),
        }
        findings: list[Finding] = []
        if latest_close > sma_50.iloc[-1] and ema_12.iloc[-1] > ema_26.iloc[-1]:
            findings.append(
                Finding(
                    code="trend_confirmed",
                    severity=FindingSeverity.WATCH,
                    direction=Direction.BULLISH,
                    summary="Price and short-term EMA remain above the medium-term trend.",
                )
            )
        elif latest_close < sma_50.iloc[-1] and ema_12.iloc[-1] < ema_26.iloc[-1]:
            findings.append(
                Finding(
                    code="trend_confirmed",
                    severity=FindingSeverity.WATCH,
                    direction=Direction.BEARISH,
                    summary="Price and short-term EMA remain below the medium-term trend.",
                )
            )

        latest_rsi = metrics["rsi_14"]
        if isinstance(latest_rsi, Decimal):
            if latest_rsi >= thresholds["rsi_overbought"]:
                findings.append(
                    Finding(
                        code="rsi_overbought",
                        severity=FindingSeverity.WATCH,
                        direction=Direction.BEARISH,
                        summary="RSI is in the configured overbought range.",
                        values={"rsi_14": latest_rsi},
                    )
                )
            elif latest_rsi <= thresholds["rsi_oversold"]:
                findings.append(
                    Finding(
                        code="rsi_oversold",
                        severity=FindingSeverity.WATCH,
                        direction=Direction.BULLISH,
                        summary="RSI is in the configured oversold range.",
                        values={"rsi_14": latest_rsi},
                    )
                )

        latest_volume_ratio = metrics["volume_ratio_20"]
        if (
            isinstance(latest_volume_ratio, Decimal)
            and latest_volume_ratio >= thresholds["volume_ratio_watch"]
        ):
            findings.append(
                Finding(
                    code="unusual_volume",
                    severity=FindingSeverity.WATCH,
                    direction=Direction.NEUTRAL,
                    summary="Latest volume is materially above its 20-session average.",
                    values={"volume_ratio_20": latest_volume_ratio},
                )
            )
        return SkillResult(
            skill_id=self.metadata.skill_id,
            status=SkillStatus.SUCCESS,
            metrics=metrics,
            findings=findings,
        )
