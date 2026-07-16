from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from pa_investing.domain.enums import AdjustmentMode, InstrumentScope
from pa_investing.finance.models import (
    AnalysisRequest,
    ExecutionMode,
    SkillMetadata,
    SkillResult,
    SkillStatus,
)
from pa_investing.finance.orchestrator import FinanceOrchestrator
from pa_investing.finance.registry import SkillRegistry
from pa_investing.finance.service import FinanceAnalysisService
from pa_investing.market_data.history.models import (
    DailyBar,
    HistoricalDataResult,
    HistoricalDataset,
    HistoricalInstrumentRef,
)


class RecordingHistoryService:
    def __init__(self, dataset: HistoricalDataset) -> None:
        self.dataset = dataset
        self.calls: list[tuple[object, date, date]] = []

    def get_for_portfolio(
        self,
        instrument_id: str,
        start_date: date,
        end_date: date,
        *,
        allow_stale: bool = False,
    ) -> HistoricalDataResult:
        self.calls.append((instrument_id, start_date, end_date))
        return HistoricalDataResult(dataset=self.dataset)

    def get_for_research(
        self,
        instrument: HistoricalInstrumentRef,
        start_date: date,
        end_date: date,
        *,
        allow_stale: bool = False,
    ) -> HistoricalDataResult:
        self.calls.append((instrument, start_date, end_date))
        return HistoricalDataResult(dataset=self.dataset)


class StubResolver:
    def __init__(self, instrument: HistoricalInstrumentRef) -> None:
        self.instrument = instrument

    def for_portfolio(self, instrument_id: str) -> HistoricalInstrumentRef:
        assert instrument_id == "instrument-1"
        return self.instrument


class EchoSkill:
    metadata = SkillMetadata(
        skill_id="echo.v1",
        name="Echo",
        description="Returns the dataset bar count.",
        execution_mode=ExecutionMode.DETERMINISTIC,
        min_bars=1,
    )

    def run(
        self,
        request: AnalysisRequest,
        dataset: HistoricalDataset,
    ) -> SkillResult:
        return SkillResult(
            skill_id=self.metadata.skill_id,
            status=SkillStatus.SUCCESS,
            metrics={"bar_count": len(dataset.bars)},
        )


def _instrument(scope: InstrumentScope) -> HistoricalInstrumentRef:
    return HistoricalInstrumentRef(
        scope=scope,
        instrument_id="instrument-1" if scope is InstrumentScope.PORTFOLIO else None,
        display_symbol="ADBE",
        asset_class="equity",
        currency="USD",
        exchange="NASDAQ",
        provider_symbols={"yahoo": "ADBE"},
    )


def test_finance_service_fetches_default_twelve_month_portfolio_history() -> None:
    dataset = HistoricalDataset(
        dataset_id="dataset-1",
        series_key="portfolio|instrument-1|all",
        provider="yahoo",
        provider_symbol="ADBE",
        provider_exchange="NASDAQ",
        currency="USD",
        fetched_at=datetime(2026, 7, 15, tzinfo=UTC),
        bars=[
            DailyBar(
                trading_date=date(2026, 7, 15),
                open=Decimal("99"),
                high=Decimal("102"),
                low=Decimal("98"),
                close=Decimal("101"),
                adjustment_mode=AdjustmentMode.ALL,
            )
        ],
    )
    history = RecordingHistoryService(dataset)
    registry = SkillRegistry()
    registry.register(EchoSkill())
    registry.register_bundle("daily_market_review.v1", ("echo.v1",))
    service = FinanceAnalysisService(
        resolver=StubResolver(_instrument(InstrumentScope.PORTFOLIO)),
        historical_data=history,
        orchestrator=FinanceOrchestrator(registry),
    )

    result = service.analyze_portfolio(
        "instrument-1",
        as_of=date(2026, 7, 15),
    )

    assert history.calls == [
        (
            "instrument-1",
            date(2026, 7, 15) - timedelta(days=365),
            date(2026, 7, 15),
        )
    ]
    assert result.dataset_id == "dataset-1"
    assert result.skill_results[0].metrics["bar_count"] == 1
