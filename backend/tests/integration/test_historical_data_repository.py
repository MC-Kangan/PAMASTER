from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pa_investing.db.base import Base
from pa_investing.db.models import HistoricalSeriesRecord, InstrumentRecord
from pa_investing.db.repositories import HistoricalDataRepository
from pa_investing.domain.enums import AdjustmentMode, InstrumentScope
from pa_investing.market_data.history.models import (
    DailyBar,
    HistoricalDataset,
    HistoricalInstrumentRef,
)


def _bar(
    trading_date: date,
    close: str,
    adjustment_mode: AdjustmentMode,
) -> DailyBar:
    close_value = Decimal(close)
    return DailyBar(
        trading_date=trading_date,
        open=close_value - Decimal("1"),
        high=close_value + Decimal("2"),
        low=close_value - Decimal("2"),
        close=close_value,
        volume=Decimal("1234.5"),
        adjustment_mode=adjustment_mode,
        dividend=Decimal("0.25"),
        split_ratio=Decimal("1"),
    )


def _research_instrument() -> HistoricalInstrumentRef:
    return HistoricalInstrumentRef(
        scope=InstrumentScope.RESEARCH,
        display_symbol="NVDA",
        asset_class="equity",
        currency="USD",
        exchange="NASDAQ",
        provider_symbols={"yahoo": "NVDA"},
    )


def _dataset(dataset_id: str = "dataset-1") -> HistoricalDataset:
    return HistoricalDataset(
        dataset_id=dataset_id,
        series_key="research|NVDA|NASDAQ|USD|all",
        provider="yahoo",
        provider_symbol="NVDA",
        provider_exchange="NASDAQ",
        currency="USD",
        fetched_at=datetime(2026, 7, 16, 8, 30, tzinfo=UTC),
        bars=[
            _bar(date(2026, 7, 14), "172.1234567890", AdjustmentMode.ALL),
            _bar(date(2026, 7, 15), "173.1234567890", AdjustmentMode.ALL),
        ],
        unadjusted_bars=[
            _bar(date(2026, 7, 14), "175.1234567890", AdjustmentMode.NONE),
            _bar(date(2026, 7, 15), "176.1234567890", AdjustmentMode.NONE),
        ],
        warnings=["missing expected session: 2026-07-13"],
    )


def test_repository_saves_dataset_atomically_and_returns_exact_version() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        repository = HistoricalDataRepository(session)
        saved = repository.save_dataset(_research_instrument(), _dataset())
        session.commit()

        loaded = repository.get_dataset(saved.dataset_id)

    assert loaded == _dataset()
    assert [bar.close for bar in loaded.bars] == [
        Decimal("172.1234567890"),
        Decimal("173.1234567890"),
    ]
    assert loaded.unadjusted_bars is not None
    assert loaded.unadjusted_bars[0].trading_date == date(2026, 7, 14)


def test_research_series_can_be_linked_without_copying_bars() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        session.add(
            InstrumentRecord(
                instrument_id="instrument-nvda",
                symbol="NVDA",
                name="NVIDIA",
                asset_class="equity",
                currency="USD",
                venue="NASDAQ",
            )
        )
        repository = HistoricalDataRepository(session)
        repository.save_dataset(_research_instrument(), _dataset())
        session.flush()

        repository.promote_series(
            series_key=_dataset().series_key,
            instrument_id="instrument-nvda",
        )
        session.commit()

        series = session.scalar(
            select(HistoricalSeriesRecord).where(
                HistoricalSeriesRecord.series_key == _dataset().series_key
            )
        )
        loaded = repository.get_dataset("dataset-1")

    assert series is not None
    assert series.instrument_id == "instrument-nvda"
    assert series.active_dataset_id == "dataset-1"
    assert loaded.dataset_id == "dataset-1"


def test_latest_covering_does_not_return_partial_date_window() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        repository = HistoricalDataRepository(session)
        repository.save_dataset(_research_instrument(), _dataset())
        session.commit()

        covered = repository.latest_covering(
            _dataset().series_key,
            date(2026, 7, 14),
            date(2026, 7, 15),
        )
        missing_left = repository.latest_covering(
            _dataset().series_key,
            date(2026, 7, 13),
            date(2026, 7, 15),
        )
        missing_right = repository.latest_covering(
            _dataset().series_key,
            date(2026, 7, 14),
            date(2026, 7, 16),
        )

    assert covered is not None
    assert covered.dataset_id == "dataset-1"
    assert missing_left is None
    assert missing_right is None
