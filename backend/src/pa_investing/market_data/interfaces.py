from abc import ABC, abstractmethod
from dataclasses import dataclass

from pa_investing.domain.models import (
    FxRatePoint,
    Instrument,
    MarketDataMapping,
    PricePoint,
)


@dataclass(frozen=True)
class QuoteRequest:
    instrument: Instrument
    mapping: MarketDataMapping


@dataclass(frozen=True)
class FxRateRequest:
    base_currency: str
    quote_currency: str


class MarketDataProvider(ABC):
    provider_name: str = "unknown"

    @abstractmethod
    def get_latest_prices(self, symbols: set[str]) -> dict[str, PricePoint]:
        raise NotImplementedError

    def get_quotes(self, requests: list[QuoteRequest]) -> dict[str, PricePoint]:
        symbols = {request.mapping.provider_symbol for request in requests}
        legacy_prices = self.get_latest_prices(symbols)
        quotes: dict[str, PricePoint] = {}
        for request in requests:
            instrument_id = request.instrument.instrument_id
            point = legacy_prices.get(request.mapping.provider_symbol)
            if instrument_id is None or point is None:
                continue
            quotes[instrument_id] = point.model_copy(
                update={
                    "instrument": request.instrument,
                    "provider_symbol": request.mapping.provider_symbol,
                    "provider_exchange": request.mapping.provider_exchange,
                }
            )
        return quotes

    def get_fx_rates(
        self,
        requests: set[FxRateRequest],
    ) -> dict[tuple[str, str], FxRatePoint]:
        return {}
