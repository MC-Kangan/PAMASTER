from collections.abc import Callable
from decimal import Decimal

import httpx

from pa_investing.instruments.market_codes import DEFAULT_MARKET_CODES
from pa_investing.instruments.resolution import InstrumentCandidate

YahooSearch = Callable[[str], list[dict[str, object]]]

YAHOO_EXCHANGE_ALIASES = {
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NYQ": "NYSE",
    "ASE": "NYSE",
    "LSE": "LSE",
}


def _asset_class(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"equity", "common stock", "stock"}:
        return "equity"
    if normalized in {"etf", "exchange-traded fund"}:
        return "etf"
    if normalized in {"cryptocurrency", "crypto"}:
        return "crypto"
    return normalized or "equity"


class YahooInstrumentSearcher:
    provider_name = "yahoo"

    def __init__(self, search: YahooSearch | None = None) -> None:
        self._search = search or self._default_search

    def search(self, query: str) -> list[InstrumentCandidate]:
        try:
            results = self._search(query)
        except Exception:
            return []
        candidates: list[InstrumentCandidate] = []
        for result in results:
            symbol = str(result.get("symbol") or "").strip()
            currency = str(result.get("currency") or "").strip()
            provider_exchange = str(result.get("exchange") or "").strip().upper()
            if not symbol or not currency:
                continue
            exchange = YAHOO_EXCHANGE_ALIASES.get(
                provider_exchange,
                provider_exchange or None,
            )
            market_code = DEFAULT_MARKET_CODES.market_for_exchange(exchange)
            display_symbol = (
                DEFAULT_MARKET_CODES.display_symbol(symbol, market_code) if market_code else symbol
            )
            candidates.append(
                InstrumentCandidate(
                    display_symbol=display_symbol,
                    name=str(result.get("shortname") or result.get("longname") or symbol),
                    asset_class=_asset_class(result.get("quoteType")),
                    currency=currency,
                    exchange=exchange,
                    mic_code=None,
                    provider_symbols={self.provider_name: symbol},
                    provider_exchanges=(
                        {self.provider_name: provider_exchange} if provider_exchange else {}
                    ),
                    provider_currencies={self.provider_name: currency},
                    provider_price_multipliers={self.provider_name: Decimal("1")},
                    confidence=Decimal("0.8"),
                )
            )
        return candidates

    @staticmethod
    def _default_search(query: str) -> list[dict[str, object]]:
        import yfinance as yf

        quotes = yf.Search(query, max_results=25).quotes
        return [quote for quote in quotes if isinstance(quote, dict)]


class TwelveDataInstrumentSearcher:
    provider_name = "twelve_data"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.twelvedata.com",
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.timeout = timeout

    def search(self, query: str) -> list[InstrumentCandidate]:
        if not self.api_key:
            return []
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=self.timeout,
                headers={"Authorization": f"apikey {self.api_key}"},
            ) as client:
                response = client.get(
                    f"{self.base_url}/symbol_search",
                    params={"symbol": query, "outputsize": "30"},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        if not isinstance(payload, dict) or payload.get("status") == "error":
            return []
        data = payload.get("data")
        if not isinstance(data, list):
            return []
        candidates: list[InstrumentCandidate] = []
        for result in data:
            if not isinstance(result, dict):
                continue
            symbol = str(result.get("symbol") or "").strip()
            currency = str(result.get("currency") or "").strip()
            exchange = str(result.get("exchange") or "").strip()
            if not symbol or not currency:
                continue
            candidates.append(
                InstrumentCandidate(
                    display_symbol=symbol,
                    name=str(result.get("instrument_name") or symbol),
                    asset_class=_asset_class(result.get("instrument_type")),
                    currency=currency,
                    exchange=exchange or None,
                    mic_code=str(result.get("mic_code") or "") or None,
                    provider_symbols={self.provider_name: symbol},
                    provider_exchanges=({self.provider_name: exchange} if exchange else {}),
                    provider_currencies={self.provider_name: currency},
                    provider_price_multipliers={self.provider_name: Decimal("1")},
                    confidence=Decimal("0.8"),
                )
            )
        return candidates
