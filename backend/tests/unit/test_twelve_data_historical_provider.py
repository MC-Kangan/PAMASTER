from datetime import date
from decimal import Decimal

import httpx
import pytest

from pa_investing.domain.enums import AdjustmentMode, InstrumentScope
from pa_investing.market_data.history.models import (
    HistoricalDataRequest,
    HistoricalInstrumentRef,
)
from pa_investing.market_data.history.provider import HistoricalProviderError
from pa_investing.market_data.history.providers.twelve_data import (
    TwelveDataHistoricalDataProvider,
)


def _request() -> HistoricalDataRequest:
    return HistoricalDataRequest(
        instrument=HistoricalInstrumentRef(
            scope=InstrumentScope.RESEARCH,
            display_symbol="SGLN",
            asset_class="etf",
            currency="GBP",
            exchange="LSE",
            provider_symbols={"twelve_data": "SGLN"},
            provider_exchanges={"twelve_data": "LSE"},
            provider_currencies={"twelve_data": "GBX"},
            provider_price_multipliers={"twelve_data": Decimal("0.01")},
        ),
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 14),
    )


def _payload(*, adjusted: bool) -> dict[str, object]:
    multiplier = Decimal("0.9") if adjusted else Decimal("1")
    values = []
    for trading_date, close in (("2026-07-14", "6125"), ("2026-07-13", "6100")):
        close_value = Decimal(close) * multiplier
        values.append(
            {
                "datetime": trading_date,
                "open": str(close_value - Decimal("10")),
                "high": str(close_value + Decimal("20")),
                "low": str(close_value - Decimal("20")),
                "close": str(close_value),
                "volume": "1000",
                "dividend": "0.5" if trading_date == "2026-07-14" else "0",
                "split": "1",
            }
        )
    return {
        "meta": {
            "symbol": "SGLN",
            "interval": "1day",
            "currency": "GBX",
            "exchange": "LSE",
        },
        "values": values,
        "status": "ok",
    }


def test_twelve_data_fetches_aligned_raw_and_adjusted_series() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "apikey test-key"
        return httpx.Response(
            200,
            json=_payload(adjusted=request.url.params["adjust"] == "all"),
        )

    provider = TwelveDataHistoricalDataProvider(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    dataset = provider.fetch_daily(_request())

    assert [bar.trading_date for bar in dataset.bars] == [
        date(2026, 7, 13),
        date(2026, 7, 14),
    ]
    assert dataset.currency == "GBP"
    assert dataset.bars[0].adjustment_mode == AdjustmentMode.ALL
    assert dataset.bars[0].close == Decimal("54.900")
    assert dataset.unadjusted_bars is not None
    assert dataset.unadjusted_bars[0].close == Decimal("61.00")
    assert dataset.bars[1].dividend == Decimal("0.005")
    assert [request.url.params["adjust"] for request in requests] == ["none", "all"]
    for request in requests:
        assert request.url.params["symbol"] == "SGLN"
        assert request.url.params["exchange"] == "LSE"
        assert request.url.params["start_date"] == "2026-07-13"
        assert request.url.params["end_date"] == "2026-07-14"
        assert request.url.params["outputsize"] == "5000"


def test_twelve_data_rejects_error_envelopes_and_misaligned_dates() -> None:
    error_provider = TwelveDataHistoricalDataProvider(
        api_key="test-key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"status": "error", "code": 400, "message": "bad symbol"},
            )
        ),
    )
    calls = 0

    def mismatched_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = _payload(adjusted=calls == 2)
        if calls == 2:
            payload["values"] = list(payload["values"])[1:]
        return httpx.Response(200, json=payload)

    mismatch_provider = TwelveDataHistoricalDataProvider(
        api_key="test-key",
        transport=httpx.MockTransport(mismatched_handler),
    )

    with pytest.raises(HistoricalProviderError) as error:
        error_provider.fetch_daily(_request())
    assert error.value.code == "provider_error"

    with pytest.raises(HistoricalProviderError) as mismatch:
        mismatch_provider.fetch_daily(_request())
    assert mismatch.value.code == "series_misaligned"


def test_twelve_data_requires_explicit_symbol_and_exchange_mapping() -> None:
    request = _request()
    request.instrument.provider_symbols.clear()
    provider = TwelveDataHistoricalDataProvider(api_key="test-key")

    with pytest.raises(HistoricalProviderError) as missing:
        provider.fetch_daily(request)

    assert missing.value.code == "mapping_missing"
