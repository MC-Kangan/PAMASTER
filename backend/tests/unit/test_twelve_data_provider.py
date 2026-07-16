from datetime import UTC, datetime
from decimal import Decimal

import httpx

from pa_investing.domain.enums import AssetClass, QuoteQuality
from pa_investing.domain.models import Instrument, MarketDataMapping
from pa_investing.market_data.interfaces import FxRateRequest, QuoteRequest
from pa_investing.market_data.twelve_data import TwelveDataProvider


def test_twelve_data_fetches_mapped_quote_and_fx_rate() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "apikey test-key"
        if request.url.path == "/quote":
            return httpx.Response(
                200,
                json={
                    "symbol": "SGLN",
                    "exchange": "LSE",
                    "mic_code": "XLON",
                    "currency": "GBX",
                    "timestamp": 1784116800,
                    "close": "6125.5",
                },
            )
        if request.url.path == "/currency_conversion":
            return httpx.Response(
                200,
                json={
                    "symbol": "GBP/USD",
                    "rate": 1.31,
                    "amount": 1.31,
                    "timestamp": 1784116800,
                },
            )
        raise AssertionError(f"unexpected request: {request.url}")

    instrument = Instrument(
        instrument_id="instrument-1",
        symbol="SGLN",
        name="iShares Physical Gold ETC",
        asset_class=AssetClass.ETF,
        currency="GBX",
        venue="LSEETF",
    )
    provider = TwelveDataProvider(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    quotes = provider.get_quotes(
        [
            QuoteRequest(
                instrument=instrument,
                mapping=MarketDataMapping(
                    instrument_id="instrument-1",
                    provider="twelve_data",
                    provider_symbol="SGLN",
                    provider_exchange="LSE",
                    expected_currency="GBX",
                ),
            )
        ]
    )
    rates = provider.get_fx_rates({FxRateRequest("GBP", "USD")})

    assert quotes["instrument-1"].price == Decimal("6125.5")
    assert quotes["instrument-1"].quote_currency == "GBX"
    assert quotes["instrument-1"].provider_exchange == "LSE"
    assert quotes["instrument-1"].quality == QuoteQuality.DELAYED
    assert quotes["instrument-1"].observed_at == datetime(
        2026, 7, 15, 12, tzinfo=UTC
    )
    assert rates[("GBP", "USD")].rate == Decimal("1.31")
    assert str(requests[0].url) == (
        "https://api.twelvedata.com/quote?symbol=SGLN&exchange=LSE"
    )
    assert str(requests[1].url) == (
        "https://api.twelvedata.com/currency_conversion?symbol=GBP%2FUSD"
        "&amount=1&timezone=UTC"
    )


def test_twelve_data_skips_error_and_malformed_payloads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/quote":
            return httpx.Response(200, json={"status": "error", "message": "missing"})
        return httpx.Response(200, json={"rate": None, "timestamp": None})

    provider = TwelveDataProvider(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    instrument = Instrument(
        instrument_id="instrument-1",
        symbol="AAPL",
        name="Apple",
        asset_class=AssetClass.EQUITY,
    )
    mapping = MarketDataMapping(
        instrument_id="instrument-1",
        provider="twelve_data",
        provider_symbol="AAPL",
        expected_currency="USD",
    )

    assert provider.get_quotes([QuoteRequest(instrument, mapping)]) == {}
    assert provider.get_fx_rates({FxRateRequest("GBP", "USD")}) == {}
