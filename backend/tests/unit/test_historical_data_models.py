from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pa_investing.domain.enums import AdjustmentMode, InstrumentScope
from pa_investing.market_data.history.models import (
    DailyBar,
    HistoricalDataRequest,
    HistoricalInstrumentRef,
)


def test_research_request_has_stable_identity_without_permanent_instrument() -> None:
    instrument = HistoricalInstrumentRef(
        scope=InstrumentScope.RESEARCH,
        display_symbol="NVDA",
        asset_class="equity",
        currency="usd",
        exchange="nasdaq",
        provider_symbols={"yahoo": "NVDA", "twelve_data": "NVDA"},
        provider_currencies={"twelve_data": "USD"},
        provider_price_multipliers={"twelve_data": Decimal("1")},
    )

    request = HistoricalDataRequest(
        instrument=instrument,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )

    assert request.instrument.instrument_id is None
    assert request.instrument.currency == "USD"
    assert request.instrument.exchange == "NASDAQ"
    assert request.instrument.provider_price_multipliers["twelve_data"] == Decimal("1")
    assert request.interval == "1d"
    assert request.required_adjustment == AdjustmentMode.ALL
    assert request.series_key == "research|NVDA|NASDAQ|USD|all"


def test_portfolio_request_requires_permanent_instrument_id() -> None:
    with pytest.raises(ValidationError, match="instrument_id"):
        HistoricalInstrumentRef(
            scope=InstrumentScope.PORTFOLIO,
            display_symbol="SGLN",
            asset_class="etf",
            currency="GBP",
            exchange="LSE",
        )


def test_request_rejects_inverted_date_range() -> None:
    instrument = HistoricalInstrumentRef(
        scope=InstrumentScope.RESEARCH,
        display_symbol="NVDA",
        asset_class="equity",
        currency="USD",
        exchange="NASDAQ",
    )

    with pytest.raises(ValidationError, match="end_date"):
        HistoricalDataRequest(
            instrument=instrument,
            start_date=date(2025, 12, 31),
            end_date=date(2025, 1, 1),
        )


def test_daily_bar_rejects_invalid_ohlc() -> None:
    with pytest.raises(ValidationError, match="OHLC"):
        DailyBar(
            trading_date=date(2026, 7, 15),
            open=Decimal("100"),
            high=Decimal("90"),
            low=Decimal("80"),
            close=Decimal("85"),
            volume=Decimal("1000"),
            adjustment_mode=AdjustmentMode.ALL,
        )


def test_daily_bar_rejects_non_positive_prices_and_negative_volume() -> None:
    with pytest.raises(ValidationError, match="positive"):
        DailyBar(
            trading_date=date(2026, 7, 15),
            open=Decimal("0"),
            high=Decimal("100"),
            low=Decimal("90"),
            close=Decimal("95"),
            adjustment_mode=AdjustmentMode.ALL,
        )

    with pytest.raises(ValidationError, match="volume"):
        DailyBar(
            trading_date=date(2026, 7, 15),
            open=Decimal("95"),
            high=Decimal("100"),
            low=Decimal("90"),
            close=Decimal("96"),
            volume=Decimal("-1"),
            adjustment_mode=AdjustmentMode.ALL,
        )
