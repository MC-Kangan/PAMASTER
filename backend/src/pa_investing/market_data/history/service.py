from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from pa_investing.db.repositories import (
    HistoricalDataRepository,
    ProviderRunRepository,
)
from pa_investing.domain.enums import InstrumentScope, ProviderRunStatus
from pa_investing.domain.models import ProviderRun
from pa_investing.instruments.resolution import InstrumentResolutionService
from pa_investing.market_data.history.models import (
    HistoricalDataRequest,
    HistoricalDataResult,
    HistoricalInstrumentRef,
)
from pa_investing.market_data.history.router import (
    HistoricalDataRouter,
    HistoricalDataUnavailable,
)


class HistoricalDataService:
    def __init__(
        self,
        *,
        session: Session,
        repository: HistoricalDataRepository,
        resolver: InstrumentResolutionService,
        router: HistoricalDataRouter,
    ) -> None:
        self.session = session
        self.repository = repository
        self.resolver = resolver
        self.router = router

    def get_for_portfolio(
        self,
        instrument_id: str,
        start_date: date,
        end_date: date,
        *,
        allow_stale: bool = False,
    ) -> HistoricalDataResult:
        instrument = self.resolver.for_portfolio(instrument_id)
        return self._get(
            instrument,
            start_date,
            end_date,
            allow_stale=allow_stale,
            promoted_instrument_id=instrument_id,
        )

    def get_for_research(
        self,
        instrument: HistoricalInstrumentRef,
        start_date: date,
        end_date: date,
        *,
        allow_stale: bool = False,
    ) -> HistoricalDataResult:
        if instrument.scope is not InstrumentScope.RESEARCH:
            raise ValueError("research entry point requires a research-scoped identity")
        return self._get(
            instrument,
            start_date,
            end_date,
            allow_stale=allow_stale,
        )

    def _get(
        self,
        instrument: HistoricalInstrumentRef,
        start_date: date,
        end_date: date,
        *,
        allow_stale: bool,
        promoted_instrument_id: str | None = None,
    ) -> HistoricalDataResult:
        request = HistoricalDataRequest(
            instrument=instrument,
            start_date=start_date,
            end_date=end_date,
            allow_stale=allow_stale,
        )
        cached = self.repository.latest_covering(
            request.series_key,
            request.start_date,
            request.end_date,
        )
        if cached is None and promoted_instrument_id is not None:
            cached = self.repository.latest_covering_for_instrument(
                promoted_instrument_id,
                request.start_date,
                request.end_date,
            )
        if cached is not None:
            return HistoricalDataResult(dataset=cached)

        try:
            result = self.router.fetch(request)
        except HistoricalDataUnavailable as exc:
            self._record_failed_run(exc)
            stale = self.repository.latest(request.series_key) if allow_stale else None
            if stale is None:
                raise
            return HistoricalDataResult(
                dataset=stale,
                attempts=exc.attempts,
                stale=True,
            )

        try:
            self.repository.save_dataset(instrument, result.dataset)
            self._record_successful_run(result)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return result

    def _record_successful_run(self, result: HistoricalDataResult) -> None:
        started_at = (
            min(attempt.started_at for attempt in result.attempts)
            if result.attempts
            else result.dataset.fetched_at
        )
        finished_at = (
            max(attempt.finished_at for attempt in result.attempts)
            if result.attempts
            else datetime.now(UTC)
        )
        warning_count = len(result.dataset.warnings) + sum(
            len(attempt.warnings) for attempt in result.attempts
        )
        ProviderRunRepository(self.session).upsert(
            ProviderRun(
                run_id=str(uuid4()),
                provider=result.dataset.provider,
                operation="historical_daily",
                status=ProviderRunStatus.SUCCESS,
                started_at=started_at,
                finished_at=finished_at,
                records_read=len(result.dataset.bars),
                records_written=len(result.dataset.bars),
                warning_count=warning_count,
            )
        )

    def _record_failed_run(self, exc: HistoricalDataUnavailable) -> None:
        now = datetime.now(UTC)
        ProviderRunRepository(self.session).upsert(
            ProviderRun(
                run_id=str(uuid4()),
                provider="historical_router",
                operation="historical_daily",
                status=ProviderRunStatus.FAILED,
                started_at=(
                    min(attempt.started_at for attempt in exc.attempts)
                    if exc.attempts
                    else now
                ),
                finished_at=(
                    max(attempt.finished_at for attempt in exc.attempts)
                    if exc.attempts
                    else now
                ),
                warning_count=sum(
                    len(attempt.warnings) for attempt in exc.attempts
                ),
                error_message="; ".join(
                    f"{attempt.provider}:{attempt.error_code}"
                    for attempt in exc.attempts
                ),
            )
        )
        self.session.commit()
