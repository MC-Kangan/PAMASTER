from datetime import date, timedelta
from decimal import Decimal

from pydantic import BaseModel, Field

from pa_investing.market_data.history.models import (
    DailyBar,
    HistoricalDataRequest,
    HistoricalDataset,
)


class ValidationResult(BaseModel):
    accepted: bool
    code: str
    warnings: list[str] = Field(default_factory=list)
    message: str


def _rejected(code: str, message: str) -> ValidationResult:
    return ValidationResult(accepted=False, code=code, message=message)


def _has_valid_ohlc(bar: DailyBar) -> bool:
    prices = (bar.open, bar.high, bar.low, bar.close)
    return (
        all(price > Decimal("0") for price in prices)
        and bar.high >= max(prices)
        and bar.low <= min(prices)
        and (bar.volume is None or bar.volume >= 0)
    )


def _weekday_dates(start_date: date, end_date: date) -> set[date]:
    dates: set[date] = set()
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            dates.add(current)
        current += timedelta(days=1)
    return dates


def validate_dataset(
    request: HistoricalDataRequest,
    dataset: HistoricalDataset,
    calendar_dates: set[date] | None = None,
    *,
    today: date | None = None,
) -> ValidationResult:
    if dataset.series_key != request.series_key:
        return _rejected("series_mismatch", "dataset series does not match request")
    if not dataset.bars:
        return _rejected("empty_dataset", "provider returned no daily bars")
    if dataset.currency.upper() != request.instrument.currency:
        return _rejected("currency_mismatch", "dataset currency does not match listing")
    expected_exchange = request.instrument.provider_exchanges.get(dataset.provider)
    if (
        expected_exchange
        and dataset.provider_exchange
        and dataset.provider_exchange.upper() != expected_exchange
    ):
        return _rejected("exchange_mismatch", "dataset exchange does not match listing")

    trading_dates = [bar.trading_date for bar in dataset.bars]
    if len(trading_dates) != len(set(trading_dates)):
        return _rejected("duplicate_dates", "dataset contains duplicate trading dates")
    if trading_dates != sorted(trading_dates):
        return _rejected("dates_not_ascending", "trading dates must be ascending")

    current_date = today or date.today()
    if any(trading_date > current_date for trading_date in trading_dates):
        return _rejected("future_date", "dataset contains a future trading date")
    if any(not _has_valid_ohlc(bar) for bar in dataset.bars):
        return _rejected("invalid_ohlc", "one or more bars contain invalid OHLC values")
    if any(
        bar.adjustment_mode is not request.required_adjustment
        for bar in dataset.bars
    ):
        return _rejected(
            "adjustment_mismatch",
            "dataset adjustment mode does not satisfy the request",
        )
    if (
        trading_dates[0] > request.start_date
        or trading_dates[-1] < request.end_date
    ):
        return _rejected(
            "insufficient_coverage",
            "dataset does not cover the complete requested date range",
        )

    expected_dates = (
        {
            trading_date
            for trading_date in calendar_dates
            if request.start_date <= trading_date <= request.end_date
        }
        if calendar_dates is not None
        else _weekday_dates(request.start_date, request.end_date)
    )
    actual_dates = set(trading_dates)
    warnings = [
        f"missing expected session: {missing_date.isoformat()}"
        for missing_date in sorted(expected_dates - actual_dates)
    ]
    return ValidationResult(
        accepted=True,
        code="accepted",
        warnings=warnings,
        message="dataset passed validation",
    )
