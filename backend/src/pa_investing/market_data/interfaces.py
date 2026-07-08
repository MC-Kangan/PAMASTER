from abc import ABC, abstractmethod

from pa_investing.domain.models import PricePoint


class MarketDataProvider(ABC):
    @abstractmethod
    def get_latest_prices(self, symbols: set[str]) -> dict[str, PricePoint]:
        raise NotImplementedError
