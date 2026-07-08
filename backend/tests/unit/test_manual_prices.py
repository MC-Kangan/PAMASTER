from decimal import Decimal
from pathlib import Path

from pa_investing.market_data.manual_prices import ManualPriceProvider


def test_manual_price_provider_returns_requested_latest_prices() -> None:
    provider = ManualPriceProvider.from_csv(Path("tests/fixtures/prices_sample.csv"))

    prices = provider.get_latest_prices({"AAPL", "BTC-USD"})

    assert set(prices) == {"AAPL", "BTC-USD"}
    assert prices["AAPL"].price == Decimal("175")
    assert prices["BTC-USD"].price == Decimal("62000")


def test_manual_price_provider_reports_missing_symbols() -> None:
    provider = ManualPriceProvider.from_csv(Path("tests/fixtures/prices_sample.csv"))

    try:
        provider.get_latest_prices({"MSFT"})
    except KeyError as exc:
        assert "missing prices for symbols: MSFT" in str(exc)
    else:
        raise AssertionError("ManualPriceProvider accepted a missing symbol")
