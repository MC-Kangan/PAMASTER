from collections.abc import Callable
from contextlib import suppress
from decimal import Decimal

import httpx

from pa_investing.instruments.market_codes import DEFAULT_MARKET_CODES
from pa_investing.instruments.resolution import InstrumentCandidate

YahooSearch = Callable[[str], list[dict[str, object]]]
YahooMetadataLoader = Callable[[str], dict[str, object]]

YAHOO_EXCHANGE_ALIASES = {
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NYQ": "NYSE",
    "ASE": "NYSE",
    "LSE": "LSE",
}

YAHOO_MARKET_SUFFIXES = {
    "LN": (".L",),
    "HK": (".HK",),
    "JP": (".T",),
    "GY": (".DE", ".F"),
    "FP": (".PA",),
    "NA": (".AS",),
    "SW": (".SW",),
    "IM": (".MI",),
    "SM": (".MC",),
}


def _yahoo_display_symbol(symbol: str, market_code: str | None) -> str:
    normalized = symbol.strip().upper()
    for suffix in YAHOO_MARKET_SUFFIXES.get(market_code or "", ()):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def _yahoo_symbol_market(symbol: str) -> str | None:
    normalized = symbol.strip().upper()
    for market_code, suffixes in YAHOO_MARKET_SUFFIXES.items():
        if any(normalized.endswith(suffix) for suffix in suffixes):
            return market_code
    return None


def _search_terms(query: str) -> tuple[str, str | None]:
    tokens = query.strip().upper().split()
    symbol = tokens[0] if tokens else ""
    market_code: str | None = None
    if len(tokens) > 1:
        with suppress(ValueError):
            market_code = DEFAULT_MARKET_CODES.normalize(tokens[1])
    return symbol, market_code


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

    def __init__(
        self,
        search: YahooSearch | None = None,
        metadata_loader: YahooMetadataLoader | None = None,
    ) -> None:
        self._search = search or self._default_search
        self._metadata_loader = metadata_loader or self._default_metadata

    def search(self, query: str) -> list[InstrumentCandidate]:
        symbol_query, market_filter = _search_terms(query)
        try:
            results = self._search(symbol_query)
        except Exception:
            return []
        candidates: list[InstrumentCandidate] = []
        for result in results:
            symbol = str(result.get("symbol") or "").strip()
            if not symbol:
                continue
            asset_class = _asset_class(result.get("quoteType"))
            if asset_class not in {"equity", "etf", "crypto"}:
                continue
            if symbol.upper() != symbol_query and not symbol.upper().startswith(
                f"{symbol_query}."
            ):
                continue
            result_market = _yahoo_symbol_market(symbol)
            if (
                market_filter
                and result_market
                and result_market != market_filter
            ):
                continue
            metadata: dict[str, object] = {}
            if not result.get("currency") or not result.get("exchange"):
                try:
                    metadata = self._metadata_loader(symbol)
                except Exception:
                    metadata = {}
            currency = str(
                result.get("currency") or metadata.get("currency") or ""
            ).strip()
            provider_exchange = str(
                result.get("exchange")
                or metadata.get("exchange")
                or metadata.get("exchangeName")
                or ""
            ).strip().upper()
            if not currency:
                continue
            exchange = YAHOO_EXCHANGE_ALIASES.get(
                provider_exchange,
                provider_exchange or None,
            )
            market_code = DEFAULT_MARKET_CODES.market_for_exchange(exchange)
            if market_filter and market_code and market_code != market_filter:
                continue
            display_symbol = _yahoo_display_symbol(symbol, market_code)
            candidates.append(
                InstrumentCandidate(
                    display_symbol=display_symbol,
                    name=str(result.get("shortname") or result.get("longname") or symbol),
                    asset_class=asset_class,
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

    @staticmethod
    def _default_metadata(symbol: str) -> dict[str, object]:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        metadata = dict(ticker.get_history_metadata() or {})
        if metadata.get("currency"):
            return metadata
        fast_info = ticker.fast_info
        return {
            **metadata,
            "currency": fast_info.get("currency"),
            "exchange": fast_info.get("exchange"),
        }


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
        symbol_query, _market_filter = _search_terms(query)
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=self.timeout,
                headers={"Authorization": f"apikey {self.api_key}"},
            ) as client:
                response = client.get(
                    f"{self.base_url}/symbol_search",
                    params={"symbol": symbol_query, "outputsize": "30"},
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
