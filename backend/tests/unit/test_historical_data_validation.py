from datetime import UTC, date, datetime
from decimal import Decimal

from pa_investing.domain.enums import AdjustmentMode, InstrumentScope
from pa_investing.market_data.history.models import (
    DailyBar,
    HistoricalDataRequest,
    HistoricalDataset,
    HistoricalInstrumentRef,
)
from pa_investing.market_data.history.validation import validate_dataset


def _request(
    *,
    start_date: date = date(2026, 7, 13),
    end_date: date = date(2026, 7, 17),
) -> HistoricalDataRequest:
    return HistoricalDataRequest(
        instrument=HistoricalInstrumentRef(
            scope=InstrumentScope.RESEARCH,
            display_symbol="NVDA",
            asset_class="equity",
            currency="USD",
            exchange="NASDAQ",
            provider_exchanges={"test": "NASDAQ"},
        ),
        start_date=start_date,
        end_date=end_date,
    )


def _bar(
    trading_date: date,
    *,
    mode: AdjustmentMode = AdjustmentMode.ALL,
) -> DailyBar:
    return DailyBar(
        trading_date=trading_date,
        open=Decimal("99"),
        high=Decimal("102"),
        low=Decimal("98"),
        close=Decimal("100"),
        volume=Decimal("1000"),
        adjustment_mode=mode,
    )


def _dataset(
    bars: list[DailyBar],
    *,
    currency: str = "USD",
    exchange: str = "NASDAQ",
) -> HistoricalDataset:
    return HistoricalDataset(
        dataset_id="dataset-1",
        series_key=_request().series_key,
        provider="test",
        provider_symbol="NVDA",
        provider_exchange=exchange,
        currency=currency,
        fetched_at=datetime(2026, 7, 18, tzinfo=UTC),
        bars=bars,
    )


def _validate(
    request: HistoricalDataRequest,
    dataset: HistoricalDataset,
    calendar_dates: set[date] | None = None,
):
    return validate_dataset(
        request,
        dataset,
        calendar_dates=calendar_dates,
        today=date(2026, 7, 18),
    )


def test_duplicate_or_descending_dates_are_rejected() -> None:
    duplicate = _dataset(
        [
            _bar(date(2026, 7, 13)),
            _bar(date(2026, 7, 13)),
            _bar(date(2026, 7, 17)),
        ]
    )
    descending = _dataset(
        [
            _bar(date(2026, 7, 17)),
            _bar(date(2026, 7, 13)),
        ]
    )

    assert _validate(_request(), duplicate).code == "duplicate_dates"
    assert _validate(_request(), descending).code == "dates_not_ascending"


def test_future_dates_are_rejected() -> None:
    request = _request(
        start_date=date(2026, 7, 17),
        end_date=date(2026, 7, 20),
    )
    dataset = _dataset(
        [_bar(date(2026, 7, 17)), _bar(date(2026, 7, 20))]
    )

    result = validate_dataset(request, dataset, today=date(2026, 7, 18))

    assert result.accepted is False
    assert result.code == "future_date"


def test_invalid_ohlc_rejects_entire_dataset() -> None:
    invalid = DailyBar.model_construct(
        trading_date=date(2026, 7, 15),
        open=Decimal("100"),
        high=Decimal("90"),
        low=Decimal("80"),
        close=Decimal("85"),
        volume=Decimal("1000"),
        adjustment_mode=AdjustmentMode.ALL,
        dividend=Decimal("0"),
        split_ratio=Decimal("1"),
    )
    dataset = _dataset(
        [_bar(date(2026, 7, 13)), _bar(date(2026, 7, 15)), _bar(date(2026, 7, 17))]
    ).model_copy(
        update={
            "bars": [
                _bar(date(2026, 7, 13)),
                invalid,
                _bar(date(2026, 7, 17)),
            ]
        }
    )

    result = _validate(_request(), dataset)

    assert result.accepted is False
    assert result.code == "invalid_ohlc"


def test_currency_listing_and_adjustment_must_match_request() -> None:
    bars = [_bar(date(2026, 7, 13)), _bar(date(2026, 7, 17))]

    assert _validate(_request(), _dataset(bars, currency="GBP")).code == (
        "currency_mismatch"
    )
    assert _validate(_request(), _dataset(bars, exchange="NYSE")).code == (
        "exchange_mismatch"
    )
    unadjusted = _dataset(
        [
            _bar(date(2026, 7, 13), mode=AdjustmentMode.NONE),
            _bar(date(2026, 7, 17), mode=AdjustmentMode.NONE),
        ]
    )
    assert _validate(_request(), unadjusted).code == "adjustment_mismatch"


def test_insufficient_boundary_coverage_is_rejected() -> None:
    missing_left = _dataset(
        [_bar(date(2026, 7, 14)), _bar(date(2026, 7, 17))]
    )
    missing_right = _dataset(
        [_bar(date(2026, 7, 13)), _bar(date(2026, 7, 16))]
    )

    assert _validate(_request(), missing_left).code == "insufficient_coverage"
    assert _validate(_request(), missing_right).code == "insufficient_coverage"


def test_missing_weekdays_warn_but_exchange_holidays_do_not() -> None:
    dataset = _dataset(
        [
            _bar(date(2026, 7, 13)),
            _bar(date(2026, 7, 14)),
            _bar(date(2026, 7, 16)),
            _bar(date(2026, 7, 17)),
        ]
    )

    without_calendar = _validate(_request(), dataset)
    with_calendar = _validate(
        _request(),
        dataset,
        {
            date(2026, 7, 13),
            date(2026, 7, 14),
            date(2026, 7, 16),
            date(2026, 7, 17),
        },
    )

    assert without_calendar.accepted is True
    assert without_calendar.warnings == ["missing expected session: 2026-07-15"]
    assert with_calendar.accepted is True
    assert with_calendar.warnings == []
