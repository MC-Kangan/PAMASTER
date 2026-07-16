from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from pa_investing.domain.enums import AdjustmentMode, InstrumentScope
from pa_investing.finance.defaults import build_default_finance_registry
from pa_investing.finance.models import (
    AnalysisRequest,
    Direction,
    SkillStatus,
)
from pa_investing.finance.orchestrator import FinanceOrchestrator
from pa_investing.finance.skills.candlestick import CandlestickEventsSkill
from pa_investing.finance.skills.market_risk import MarketRiskSnapshotSkill
from pa_investing.finance.skills.technical import TechnicalSnapshotSkill
from pa_investing.market_data.history.models import (
    DailyBar,
    HistoricalDataset,
    HistoricalInstrumentRef,
)


def _bar(index: int, close: Decimal, *, volume: Decimal = Decimal("1000")) -> DailyBar:
    return DailyBar(
        trading_date=date(2026, 1, 1) + timedelta(days=index),
        open=close - Decimal("0.5"),
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        volume=volume,
        adjustment_mode=AdjustmentMode.ALL,
    )


def _dataset(bars: list[DailyBar]) -> HistoricalDataset:
    return HistoricalDataset(
        dataset_id="dataset-1",
        series_key="research|ADBE|NASDAQ|USD|all",
        provider="yahoo",
        provider_symbol="ADBE",
        provider_exchange="NASDAQ",
        currency="USD",
        fetched_at=datetime(2026, 7, 15, tzinfo=UTC),
        bars=bars,
    )


def _request() -> AnalysisRequest:
    return AnalysisRequest(
        instrument=HistoricalInstrumentRef(
            scope=InstrumentScope.RESEARCH,
            display_symbol="ADBE",
            asset_class="equity",
            currency="USD",
            exchange="NASDAQ",
            provider_symbols={"yahoo": "ADBE"},
        ),
        as_of=date(2026, 7, 15),
    )


def test_technical_snapshot_returns_metrics_and_material_findings() -> None:
    bars = [
        _bar(
            index,
            Decimal("100") + Decimal(index),
            volume=Decimal("3000") if index == 79 else Decimal("1000"),
        )
        for index in range(80)
    ]

    result = TechnicalSnapshotSkill().run(_request(), _dataset(bars))

    assert result.status is SkillStatus.SUCCESS
    assert result.metrics["rsi_14"] == Decimal("100.0")
    assert result.metrics["close_above_sma_50"] is True
    assert {finding.code for finding in result.findings} >= {
        "trend_confirmed",
        "rsi_overbought",
        "unusual_volume",
    }


def test_technical_snapshot_omits_findings_when_history_is_insufficient() -> None:
    result = TechnicalSnapshotSkill().run(
        _request(),
        _dataset([_bar(index, Decimal("100") + index) for index in range(20)]),
    )

    assert result.status is SkillStatus.PARTIAL
    assert result.findings == []
    assert "requires at least 50 completed daily bars" in result.warnings[0]


def test_candlestick_events_surfaces_only_recent_patterns() -> None:
    bars = [_bar(index, Decimal("100")) for index in range(10)]
    bars[1] = bars[1].model_copy(
        update={
            "open": Decimal("102"),
            "high": Decimal("103"),
            "low": Decimal("99"),
            "close": Decimal("100"),
        }
    )
    bars[2] = bars[2].model_copy(
        update={
            "open": Decimal("99"),
            "high": Decimal("104"),
            "low": Decimal("98"),
            "close": Decimal("103"),
        }
    )
    bars[8] = bars[8].model_copy(
        update={
            "open": Decimal("102"),
            "high": Decimal("103"),
            "low": Decimal("99"),
            "close": Decimal("100"),
        }
    )
    bars[9] = bars[9].model_copy(
        update={
            "open": Decimal("99"),
            "high": Decimal("104"),
            "low": Decimal("98"),
            "close": Decimal("103"),
        }
    )

    result = CandlestickEventsSkill().run(_request(), _dataset(bars))

    bullish = [finding for finding in result.findings if finding.code == "bullish_engulfing"]
    assert len(bullish) == 1
    assert bullish[0].observed_on == bars[9].trading_date
    assert bullish[0].direction is Direction.BULLISH
    assert result.metrics["detected_event_count"] >= 2


def test_market_risk_snapshot_flags_material_drawdown() -> None:
    closes = [Decimal("100") + Decimal(index) / 10 for index in range(59)]
    closes.append(Decimal("80"))

    result = MarketRiskSnapshotSkill().run(
        _request(),
        _dataset([_bar(index, close) for index, close in enumerate(closes)]),
    )

    assert result.status is SkillStatus.SUCCESS
    assert result.metrics["drawdown_from_peak"] < Decimal("-0.2")
    assert "material_drawdown" in {finding.code for finding in result.findings}
    assert "abnormal_daily_move" in {finding.code for finding in result.findings}


def test_default_bundle_runs_all_three_skills() -> None:
    bars = [_bar(index, Decimal("100") + Decimal(index) / 10) for index in range(80)]

    result = FinanceOrchestrator(build_default_finance_registry()).run(
        _request(),
        _dataset(bars),
    )

    assert [item.skill_id for item in result.skill_results] == [
        "technical_snapshot.v1",
        "candlestick_events.v1",
        "market_risk_snapshot.v1",
    ]
