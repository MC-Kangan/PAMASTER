from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

from pa_investing.finance.models import AnalysisRequest, AnalysisResult
from pa_investing.finance.orchestrator import FinanceOrchestrator
from pa_investing.market_data.history.models import (
    HistoricalDataResult,
    HistoricalInstrumentRef,
)


class HistoricalDataClient(Protocol):
    def get_for_portfolio(
        self,
        instrument_id: str,
        start_date: date,
        end_date: date,
        *,
        allow_stale: bool = False,
    ) -> HistoricalDataResult: ...

    def get_for_research(
        self,
        instrument: HistoricalInstrumentRef,
        start_date: date,
        end_date: date,
        *,
        allow_stale: bool = False,
    ) -> HistoricalDataResult: ...


class PortfolioInstrumentResolver(Protocol):
    def for_portfolio(self, instrument_id: str) -> HistoricalInstrumentRef: ...


class FinanceAnalysisService:
    def __init__(
        self,
        *,
        resolver: PortfolioInstrumentResolver,
        historical_data: HistoricalDataClient,
        orchestrator: FinanceOrchestrator,
    ) -> None:
        self.resolver = resolver
        self.historical_data = historical_data
        self.orchestrator = orchestrator

    def analyze_portfolio(
        self,
        instrument_id: str,
        *,
        as_of: date,
        lookback_days: int = 365,
        bundle: str = "daily_market_review.v1",
        skill_ids: tuple[str, ...] = (),
        threshold_overrides: dict[str, dict[str, Decimal]] | None = None,
        allow_stale: bool = False,
    ) -> AnalysisResult:
        instrument = self.resolver.for_portfolio(instrument_id)
        market_data = self.historical_data.get_for_portfolio(
            instrument_id,
            as_of - timedelta(days=lookback_days),
            as_of,
            allow_stale=allow_stale,
        )
        return self._run(
            instrument,
            market_data,
            as_of=as_of,
            lookback_days=lookback_days,
            bundle=bundle,
            skill_ids=skill_ids,
            threshold_overrides=threshold_overrides,
        )

    def analyze_research(
        self,
        instrument: HistoricalInstrumentRef,
        *,
        as_of: date,
        lookback_days: int = 365,
        bundle: str = "daily_market_review.v1",
        skill_ids: tuple[str, ...] = (),
        threshold_overrides: dict[str, dict[str, Decimal]] | None = None,
        allow_stale: bool = False,
    ) -> AnalysisResult:
        market_data = self.historical_data.get_for_research(
            instrument,
            as_of - timedelta(days=lookback_days),
            as_of,
            allow_stale=allow_stale,
        )
        return self._run(
            instrument,
            market_data,
            as_of=as_of,
            lookback_days=lookback_days,
            bundle=bundle,
            skill_ids=skill_ids,
            threshold_overrides=threshold_overrides,
        )

    def _run(
        self,
        instrument: HistoricalInstrumentRef,
        market_data: HistoricalDataResult,
        *,
        as_of: date,
        lookback_days: int,
        bundle: str,
        skill_ids: tuple[str, ...],
        threshold_overrides: dict[str, dict[str, Decimal]] | None,
    ) -> AnalysisResult:
        request = AnalysisRequest(
            instrument=instrument,
            as_of=as_of,
            lookback_days=lookback_days,
            bundle=bundle,
            skill_ids=skill_ids,
            threshold_overrides=threshold_overrides or {},
        )
        return self.orchestrator.run(request, market_data.dataset)
