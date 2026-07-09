import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx

from pa_investing.domain.enums import AssetClass
from pa_investing.market_data.alpha_vantage import AlphaVantageProvider


def test_alpha_vantage_provider_reads_equity_quote() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "alpha_vantage_global_quote_aapl.json"
    )
    response_body = json.loads(fixture_path.read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == (
            "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=AAPL&apikey=demo"
        )
        return httpx.Response(200, json=response_body)

    provider = AlphaVantageProvider(
        api_key="demo",
        transport=httpx.MockTransport(handler),
    )

    prices = provider.get_latest_prices({"AAPL"})

    assert prices["AAPL"].price == Decimal("210.55")
    assert prices["AAPL"].provider == "alpha_vantage"
    assert prices["AAPL"].instrument.symbol == "AAPL"
    assert prices["AAPL"].instrument.asset_class == AssetClass.EQUITY
    assert prices["AAPL"].instrument.currency == "USD"
    assert prices["AAPL"].observed_at == datetime(2026, 7, 7, 0, 0, 0, tzinfo=UTC)


def test_alpha_vantage_provider_reads_crypto_quote_against_usd() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1] / "fixtures" / "alpha_vantage_btc_usd.json"
    )
    response_body = json.loads(fixture_path.read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == (
            "https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=BTC"
            "&to_currency=USD&apikey=demo"
        )
        return httpx.Response(200, json=response_body)

    provider = AlphaVantageProvider(
        api_key="demo",
        transport=httpx.MockTransport(handler),
    )

    prices = provider.get_latest_prices({"BTC-USD"})

    assert prices["BTC-USD"].price == Decimal("65000.00")
    assert prices["BTC-USD"].provider == "alpha_vantage"
    assert prices["BTC-USD"].instrument.symbol == "BTC-USD"
    assert prices["BTC-USD"].instrument.asset_class == AssetClass.CRYPTO
    assert prices["BTC-USD"].instrument.currency == "USD"
    assert prices["BTC-USD"].observed_at == datetime(2026, 7, 7, 20, 0, 0, tzinfo=UTC)


def test_alpha_vantage_provider_skips_malformed_equity_payload_without_aborting_batch() -> None:
    bad_equity_payload = {
        "Global Quote": {
            "01. symbol": "AAPL",
            "05. price": "not-a-decimal",
            "07. latest trading day": "2026-07-07",
        }
    }
    fixture_path = (
        Path(__file__).resolve().parents[1] / "fixtures" / "alpha_vantage_btc_usd.json"
    )
    good_crypto_payload = json.loads(fixture_path.read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        if "function=GLOBAL_QUOTE" in str(request.url):
            return httpx.Response(200, json=bad_equity_payload)
        if "function=CURRENCY_EXCHANGE_RATE" in str(request.url):
            return httpx.Response(200, json=good_crypto_payload)
        raise AssertionError(f"Unexpected request: {request.url}")

    provider = AlphaVantageProvider(
        api_key="demo",
        transport=httpx.MockTransport(handler),
    )

    prices = provider.get_latest_prices({"AAPL", "BTC-USD"})

    assert "AAPL" not in prices
    assert prices["BTC-USD"].price == Decimal("65000.00")


def test_alpha_vantage_provider_skips_malformed_crypto_payload_without_aborting_batch() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "alpha_vantage_global_quote_aapl.json"
    )
    good_equity_payload = json.loads(fixture_path.read_text())
    bad_crypto_payload = {
        "Realtime Currency Exchange Rate": {
            "1. From_Currency Code": "BTC",
            "3. To_Currency Code": "USD",
            "5. Exchange Rate": "65000.00",
            "6. Last Refreshed": "not-a-datetime",
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "function=GLOBAL_QUOTE" in str(request.url):
            return httpx.Response(200, json=good_equity_payload)
        if "function=CURRENCY_EXCHANGE_RATE" in str(request.url):
            return httpx.Response(200, json=bad_crypto_payload)
        raise AssertionError(f"Unexpected request: {request.url}")

    provider = AlphaVantageProvider(
        api_key="demo",
        transport=httpx.MockTransport(handler),
    )

    prices = provider.get_latest_prices({"AAPL", "BTC-USD"})

    assert prices["AAPL"].price == Decimal("210.55")
    assert "BTC-USD" not in prices


def test_alpha_vantage_provider_keeps_equity_quote_currency_truthful() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "alpha_vantage_global_quote_aapl.json"
    )
    response_body = json.loads(fixture_path.read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_body)

    provider = AlphaVantageProvider(
        api_key="demo",
        base_currency="EUR",
        transport=httpx.MockTransport(handler),
    )

    prices = provider.get_latest_prices({"AAPL"})

    assert prices["AAPL"].instrument.currency == "USD"
