from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pa_investing.db.base import Base
from pa_investing.db.models import ProviderRunRecord
from pa_investing.db.repositories import HistoricalDataRepository
from pa_investing.domain.enums import AdjustmentMode, InstrumentScope
from pa_investing.instruments.resolution import InstrumentResolutionService
from pa_investing.market_data.history.models import (
    DailyBar,
    HistoricalDataResult,
    HistoricalDataset,
    HistoricalInstrumentRef,
    ProviderAttempt,
)
from pa_investing.market_data.history.router import HistoricalDataUnavailable
from pa_investing.market_data.history.service import HistoricalDataService


class StubRouter:
    def __init__(
        self,
        result: HistoricalDataResult | None = None,
        error: HistoricalDataUnavailable | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def fetch(self, request):
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("router has no result")
        return self.result


def _instrument() -> HistoricalInstrumentRef:
    return HistoricalInstrumentRef(
        scope=InstrumentScope.RESEARCH,
        display_symbol="NVDA",
        asset_class="equity",
        currency="USD",
        exchange="NASDAQ",
        provider_symbols={"yahoo": "NVDA"},
    )


def _dataset(
    *,
    dataset_id: str = "dataset-1",
    start: date = date(2025, 1, 6),
    end: date = date(2025, 1, 10),
) -> HistoricalDataset:
    dates = []
    current = start
    while current <= end:
        dates.append(current)
        current = date.fromordinal(current.toordinal() + 1)
    bars = [
        DailyBar(
            trading_date=trading_date,
            open=Decimal("99"),
            high=Decimal("101"),
            low=Decimal("98"),
            close=Decimal("100"),
            adjustment_mode=AdjustmentMode.ALL,
        )
        for trading_date in dates
    ]
    return HistoricalDataset(
        dataset_id=dataset_id,
        series_key="research|NVDA|NASDAQ|USD|all",
        provider="yahoo",
        provider_symbol="NVDA",
        provider_exchange="NASDAQ",
        currency="USD",
        fetched_at=datetime(2025, 1, 11, tzinfo=UTC),
        bars=bars,
    )


def _attempt(*, accepted: bool, code: str | None = None) -> ProviderAttempt:
    return ProviderAttempt(
        provider="yahoo",
        accepted=accepted,
        started_at=datetime(2025, 1, 11, tzinfo=UTC),
        finished_at=datetime(2025, 1, 11, 0, 0, 1, tzinfo=UTC),
        error_code=code,
        message=code,
    )


def test_existing_covering_dataset_causes_no_provider_call() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        repository = HistoricalDataRepository(session)
        repository.save_dataset(_instrument(), _dataset())
        session.commit()
        router = StubRouter()
        service = HistoricalDataService(
            session=session,
            repository=repository,
            resolver=InstrumentResolutionService(session=session),
            router=router,
        )

        result = service.get_for_research(
            _instrument(),
            date(2025, 1, 6),
            date(2025, 1, 10),
        )

    assert result.dataset.dataset_id == "dataset-1"
    assert result.attempts == []
    assert router.calls == 0


def test_uncovered_range_routes_persists_and_records_provider_run() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    routed = HistoricalDataResult(
        dataset=_dataset(),
        attempts=[_attempt(accepted=True)],
    )

    with session_factory() as session:
        repository = HistoricalDataRepository(session)
        service = HistoricalDataService(
            session=session,
            repository=repository,
            resolver=InstrumentResolutionService(session=session),
            router=StubRouter(result=routed),
        )

        result = service.get_for_research(
            _instrument(),
            date(2025, 1, 6),
            date(2025, 1, 10),
        )
        stored = repository.get_dataset("dataset-1")
        provider_run = session.scalar(select(ProviderRunRecord))

    assert result.dataset == stored
    assert provider_run is not None
    assert provider_run.status == "success"
    assert provider_run.records_written == len(routed.dataset.bars)


def test_failed_fetch_can_return_explicit_stale_dataset_without_replacing_it() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    attempts = [_attempt(accepted=False, code="timeout")]

    with session_factory() as session:
        repository = HistoricalDataRepository(session)
        repository.save_dataset(_instrument(), _dataset())
        session.commit()
        router = StubRouter(error=HistoricalDataUnavailable(attempts))
        service = HistoricalDataService(
            session=session,
            repository=repository,
            resolver=InstrumentResolutionService(session=session),
            router=router,
        )

        with pytest.raises(HistoricalDataUnavailable):
            service.get_for_research(
                _instrument(),
                date(2025, 1, 5),
                date(2025, 1, 11),
                allow_stale=False,
            )

        stale = service.get_for_research(
            _instrument(),
            date(2025, 1, 5),
            date(2025, 1, 11),
            allow_stale=True,
        )
        active = repository.latest(_dataset().series_key)

    assert stale.stale is True
    assert stale.dataset.dataset_id == "dataset-1"
    assert stale.attempts[0].error_code == "timeout"
    assert active is not None
    assert active.dataset_id == "dataset-1"
