import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Instrument, PricePoint
from pa_investing.market_data.interfaces import MarketDataProvider


class ManualPriceProvider(MarketDataProvider):
    def __init__(self, prices: dict[str, PricePoint]) -> None:
        self.prices = prices

    @classmethod
    def from_csv(cls, path: Path) -> "ManualPriceProvider":
        prices: dict[str, PricePoint] = {}
        with path.open(newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                instrument = Instrument(
                    symbol=row["symbol"],
                    name=row["name"],
                    asset_class=AssetClass(row["asset_class"]),
                    currency=row["currency"],
                )
                prices[instrument.symbol] = PricePoint(
                    instrument=instrument,
                    price=Decimal(row["price"]),
                    observed_at=datetime.fromisoformat(row["observed_at"]),
                    provider="manual",
                )
        return cls(prices)

    def get_latest_prices(self, symbols: set[str]) -> dict[str, PricePoint]:
        normalized = {symbol.upper() for symbol in symbols}
        missing = sorted(symbol for symbol in normalized if symbol not in self.prices)
        if missing:
            raise KeyError(f"missing prices for symbols: {', '.join(missing)}")
        return {symbol: self.prices[symbol] for symbol in normalized}
