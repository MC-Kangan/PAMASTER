from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import httpx

from pa_investing.domain.enums import AssetClass, QuoteQuality
from pa_investing.domain.models import FxRatePoint, Instrument, PricePoint
from pa_investing.market_data.interfaces import (
    FxRateRequest,
    MarketDataProvider,
    QuoteRequest,
)

TWELVE_DATA_API_URL = "https://api.twelvedata.com"
PROVIDER_NAME = "twelve_data"


class TwelveDataProvider(MarketDataProvider):
    provider_name = PROVIDER_NAME

    def __init__(
        self,
        api_key: str,
        base_url: str = TWELVE_DATA_API_URL,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.timeout = timeout

    def get_latest_prices(self, symbols: set[str]) -> dict[str, PricePoint]:
        prices: dict[str, PricePoint] = {}
        with self._client() as client:
            for symbol in sorted(symbols):
                payload = self._get_json(client, "/quote", {"symbol": symbol})
                point = self._parse_quote(
                    payload,
                    Instrument(
                        symbol=symbol,
                        name=symbol,
                        asset_class=AssetClass.EQUITY,
                    ),
                    provider_symbol=symbol,
                    provider_exchange=None,
                )
                if point is not None:
                    prices[symbol] = point
        return prices

    def get_quotes(self, requests: list[QuoteRequest]) -> dict[str, PricePoint]:
        quotes: dict[str, PricePoint] = {}
        with self._client() as client:
            for request in requests:
                instrument_id = request.instrument.instrument_id
                if instrument_id is None:
                    continue
                params = {"symbol": request.mapping.provider_symbol}
                if request.mapping.provider_exchange:
                    params["exchange"] = request.mapping.provider_exchange
                payload = self._get_json(client, "/quote", params)
                point = self._parse_quote(
                    payload,
                    request.instrument,
                    provider_symbol=request.mapping.provider_symbol,
                    provider_exchange=request.mapping.provider_exchange,
                )
                if point is not None:
                    quotes[instrument_id] = point
        return quotes

    def get_fx_rates(
        self,
        requests: set[FxRateRequest],
    ) -> dict[tuple[str, str], FxRatePoint]:
        rates: dict[tuple[str, str], FxRatePoint] = {}
        with self._client() as client:
            for request in sorted(
                requests,
                key=lambda item: (item.base_currency, item.quote_currency),
            ):
                base = request.base_currency.upper()
                quote = request.quote_currency.upper()
                payload = self._get_json(
                    client,
                    "/currency_conversion",
                    {
                        "symbol": f"{base}/{quote}",
                        "amount": "1",
                        "timezone": "UTC",
                    },
                )
                point = self._parse_fx_rate(payload, base, quote)
                if point is not None:
                    rates[(base, quote)] = point
        return rates

    def _client(self) -> httpx.Client:
        return httpx.Client(
            transport=self.transport,
            timeout=self.timeout,
            headers={"Authorization": f"apikey {self.api_key}"},
        )

    def _get_json(
        self,
        client: httpx.Client,
        path: str,
        params: dict[str, str],
    ) -> dict[str, object]:
        try:
            response = client.get(f"{self.base_url}{path}", params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return {}
        if not isinstance(payload, dict) or payload.get("status") == "error":
            return {}
        return payload

    @staticmethod
    def _parse_quote(
        payload: dict[str, object],
        instrument: Instrument,
        *,
        provider_symbol: str,
        provider_exchange: str | None,
    ) -> PricePoint | None:
        close = payload.get("close")
        currency = payload.get("currency")
        timestamp = payload.get("timestamp")
        if close in (None, "") or not isinstance(currency, str):
            return None
        try:
            observed_at = datetime.fromtimestamp(int(str(timestamp)), tz=UTC)
            return PricePoint(
                instrument=instrument,
                price=Decimal(str(close)),
                observed_at=observed_at,
                provider=PROVIDER_NAME,
                quote_currency=currency,
                provider_symbol=str(payload.get("symbol") or provider_symbol),
                provider_exchange=str(
                    payload.get("exchange") or provider_exchange or ""
                )
                or None,
                quality=QuoteQuality.DELAYED,
            )
        except (InvalidOperation, TypeError, ValueError, OSError):
            return None

    @staticmethod
    def _parse_fx_rate(
        payload: dict[str, object],
        base_currency: str,
        quote_currency: str,
    ) -> FxRatePoint | None:
        rate = payload.get("rate")
        timestamp = payload.get("timestamp")
        if rate in (None, "") or timestamp in (None, ""):
            return None
        try:
            return FxRatePoint(
                base_currency=base_currency,
                quote_currency=quote_currency,
                rate=Decimal(str(rate)),
                observed_at=datetime.fromtimestamp(int(str(timestamp)), tz=UTC),
                provider=PROVIDER_NAME,
            )
        except (InvalidOperation, TypeError, ValueError, OSError):
            return None
