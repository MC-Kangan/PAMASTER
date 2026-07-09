from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import httpx

from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Instrument, PricePoint
from pa_investing.market_data.interfaces import MarketDataProvider

ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"
EQUITY_QUOTE_CURRENCY = "USD"
PROVIDER_NAME = "alpha_vantage"


class AlphaVantageProvider(MarketDataProvider):
    def __init__(
        self,
        api_key: str,
        base_currency: str = "USD",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_currency = base_currency.upper()
        self.transport = transport

    def get_latest_prices(self, symbols: set[str]) -> dict[str, PricePoint]:
        prices: dict[str, PricePoint] = {}
        with httpx.Client(transport=self.transport, timeout=10.0) as client:
            for symbol in sorted({item.upper() for item in symbols}):
                price_point = self._get_price_for_symbol(client, symbol)
                if price_point is not None:
                    prices[symbol] = price_point
        return prices

    def _get_price_for_symbol(
        self,
        client: httpx.Client,
        symbol: str,
    ) -> PricePoint | None:
        if "-" in symbol:
            return self._get_crypto_price(client, symbol)
        return self._get_equity_price(client, symbol)

    def _get_equity_price(
        self,
        client: httpx.Client,
        symbol: str,
    ) -> PricePoint | None:
        response = client.get(
            ALPHA_VANTAGE_URL,
            params=[
                ("function", "GLOBAL_QUOTE"),
                ("symbol", symbol),
                ("apikey", self.api_key),
            ],
        )
        response.raise_for_status()
        payload = response.json()
        if "Note" in payload or "Error Message" in payload:
            return None

        quote = payload.get("Global Quote")
        if not isinstance(quote, dict):
            return None

        price = quote.get("05. price")
        latest_trading_day = quote.get("07. latest trading day")
        if not isinstance(price, str) or not isinstance(latest_trading_day, str):
            return None

        instrument = Instrument(
            symbol=symbol,
            name=symbol,
            asset_class=AssetClass.EQUITY,
            currency=EQUITY_QUOTE_CURRENCY,
        )
        try:
            observed_at = datetime.fromisoformat(latest_trading_day).replace(tzinfo=UTC)
            parsed_price = Decimal(price)
            return PricePoint(
                instrument=instrument,
                price=parsed_price,
                observed_at=observed_at,
                provider=PROVIDER_NAME,
            )
        except (InvalidOperation, ValueError):
            return None

    def _get_crypto_price(
        self,
        client: httpx.Client,
        symbol: str,
    ) -> PricePoint | None:
        from_currency, to_currency = symbol.split("-", maxsplit=1)
        response = client.get(
            ALPHA_VANTAGE_URL,
            params=[
                ("function", "CURRENCY_EXCHANGE_RATE"),
                ("from_currency", from_currency),
                ("to_currency", to_currency),
                ("apikey", self.api_key),
            ],
        )
        response.raise_for_status()
        payload = response.json()
        if "Note" in payload or "Error Message" in payload:
            return None

        rate = payload.get("Realtime Currency Exchange Rate")
        if not isinstance(rate, dict):
            return None

        price = rate.get("5. Exchange Rate")
        last_refreshed = rate.get("6. Last Refreshed")
        if not isinstance(price, str) or not isinstance(last_refreshed, str):
            return None

        instrument = Instrument(
            symbol=symbol,
            name=symbol,
            asset_class=AssetClass.CRYPTO,
            currency=to_currency,
        )
        try:
            observed_at = datetime.fromisoformat(last_refreshed).replace(tzinfo=UTC)
            parsed_price = Decimal(price)
            return PricePoint(
                instrument=instrument,
                price=parsed_price,
                observed_at=observed_at,
                provider=PROVIDER_NAME,
            )
        except (InvalidOperation, ValueError):
            return None
