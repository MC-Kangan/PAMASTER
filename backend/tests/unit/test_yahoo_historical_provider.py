from datetime import UTC, date, datetime
from decimal import Decimal

import pandas as pd
import pytest

from pa_investing.domain.enums import AdjustmentMode, InstrumentScope
from pa_investing.market_data.history.models import (
    HistoricalDataRequest,
    HistoricalInstrumentRef,
)
from pa_investing.market_data.history.provider import HistoricalProviderError
from pa_investing.market_data.history.providers.yahoo import (
    YahooHistoricalDataProvider,
)


def _request(*, mapped: bool = True) -> HistoricalDataRequest:
    return HistoricalDataRequest(
        instrument=HistoricalInstrumentRef(
            scope=InstrumentScope.RESEARCH,
            display_symbol="SGLN",
            asset_class="etf",
            currency="GBP",
            exchange="LSE",
            provider_symbols={"yahoo": "SGLN.L"} if mapped else {},
            provider_exchanges={"yahoo": "LSE"},
        ),
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 14),
    )


def test_yahoo_produces_adjusted_and_raw_bars_with_actions() -> None:
    calls: list[dict[str, object]] = []

    def downloader(**kwargs: object) -> pd.DataFrame:
        calls.append(kwargs)
        return pd.DataFrame(
            {
                "Open": [100.0, 110.0],
                "High": [105.0, 115.0],
                "Low": [95.0, 105.0],
                "Close": [100.0, 110.0],
                "Adj Close": [50.0, 55.0],
                "Volume": [1000, 1200],
                "Dividends": [0.0, 1.5],
                "Stock Splits": [2.0, 0.0],
            },
            index=pd.to_datetime(["2026-07-13", "2026-07-14"]),
        )

    provider = YahooHistoricalDataProvider(
        downloader=downloader,
        metadata_loader=lambda symbol: {
            "symbol": symbol,
            "currency": "GBP",
            "exchange": "LSE",
        },
        clock=lambda: datetime(2026, 7, 15, 8, tzinfo=UTC),
    )

    dataset = provider.fetch_daily(_request())

    assert dataset.provider == "yahoo"
    assert dataset.provider_symbol == "SGLN.L"
    assert dataset.currency == "GBP"
    assert dataset.bars[0].adjustment_mode == AdjustmentMode.ALL
    assert dataset.bars[0].open == Decimal("50.0")
    assert dataset.bars[0].high == Decimal("52.50")
    assert dataset.bars[1].dividend == Decimal("1.5")
    assert dataset.bars[0].split_ratio == Decimal("2.0")
    assert dataset.unadjusted_bars is not None
    assert dataset.unadjusted_bars[0].adjustment_mode == AdjustmentMode.NONE
    assert dataset.unadjusted_bars[0].open == Decimal("100.0")
    assert calls == [
        {
            "tickers": "SGLN.L",
            "start": "2026-07-13",
            "end": "2026-07-15",
            "interval": "1d",
            "auto_adjust": False,
            "actions": True,
            "repair": False,
            "keepna": True,
            "progress": False,
            "threads": False,
            "timeout": 10,
        }
    ]


def test_yahoo_requires_mapping_and_matching_listing_metadata() -> None:
    provider = YahooHistoricalDataProvider(
        downloader=lambda **kwargs: pd.DataFrame(),
        metadata_loader=lambda symbol: {
            "symbol": symbol,
            "currency": "USD",
            "exchange": "NASDAQ",
        },
    )

    with pytest.raises(HistoricalProviderError) as missing:
        provider.fetch_daily(_request(mapped=False))
    assert missing.value.code == "mapping_missing"

    with pytest.raises(HistoricalProviderError) as mismatch:
        provider.fetch_daily(_request())
    assert mismatch.value.code == "currency_mismatch"


def test_yahoo_rejects_empty_or_zero_close_frames() -> None:
    def metadata(symbol: str) -> dict[str, object]:
        return {
            "symbol": symbol,
            "currency": "GBP",
            "exchange": "LSE",
        }

    empty_provider = YahooHistoricalDataProvider(
        downloader=lambda **kwargs: pd.DataFrame(),
        metadata_loader=metadata,
    )
    zero_close_provider = YahooHistoricalDataProvider(
        downloader=lambda **kwargs: pd.DataFrame(
            {
                "Open": [1],
                "High": [1],
                "Low": [1],
                "Close": [0],
                "Adj Close": [1],
                "Volume": [1],
            },
            index=pd.to_datetime(["2026-07-13"]),
        ),
        metadata_loader=metadata,
    )

    with pytest.raises(HistoricalProviderError) as empty:
        empty_provider.fetch_daily(_request())
    assert empty.value.code == "empty_response"

    with pytest.raises(HistoricalProviderError) as invalid:
        zero_close_provider.fetch_daily(_request())
    assert invalid.value.code == "invalid_adjustment_factor"
