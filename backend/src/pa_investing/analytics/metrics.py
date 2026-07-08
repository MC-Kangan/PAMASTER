from collections import defaultdict
from decimal import Decimal

from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Position


def calculate_nav(positions: list[Position]) -> Decimal:
    return sum((position.market_value for position in positions), Decimal("0"))


def calculate_unrealized_pnl(positions: list[Position]) -> Decimal:
    return sum((position.unrealized_pnl for position in positions), Decimal("0"))


def calculate_gross_exposure(positions: list[Position]) -> Decimal:
    return sum((abs(position.market_value) for position in positions), Decimal("0"))


def calculate_exposure_by_asset_class(positions: list[Position]) -> dict[AssetClass, Decimal]:
    exposure: defaultdict[AssetClass, Decimal] = defaultdict(lambda: Decimal("0"))
    for position in positions:
        exposure[position.instrument.asset_class] += abs(position.market_value)
    return dict(exposure)
