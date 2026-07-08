from decimal import ROUND_DOWN, Decimal

from pydantic import BaseModel

from pa_investing.domain.models import Position


class SizingRecommendation(BaseModel):
    symbol: str
    quantity_to_reduce: Decimal
    message: str


class MaxNavWeightSizingModel:
    def __init__(self, max_weight: Decimal) -> None:
        if max_weight <= 0 or max_weight > 1:
            raise ValueError("max_weight must be greater than 0 and less than or equal to 1")
        self.max_weight = max_weight

    def recommend_reduction(
        self,
        position: Position,
        portfolio_nav: Decimal,
    ) -> SizingRecommendation:
        if position.latest_price is None or position.latest_price <= 0:
            return SizingRecommendation(
                symbol=position.instrument.symbol,
                quantity_to_reduce=Decimal("0"),
                message=(
                    f"No reduction for {position.instrument.symbol}; "
                    "missing, zero, or negative latest price."
                ),
            )

        if portfolio_nav <= 0:
            return SizingRecommendation(
                symbol=position.instrument.symbol,
                quantity_to_reduce=Decimal("0"),
                message=f"No reduction for {position.instrument.symbol}; missing price or NAV.",
            )

        max_value = portfolio_nav * self.max_weight
        excess_value = max(position.market_value - max_value, Decimal("0"))
        quantity = (excess_value / position.latest_price).quantize(
            Decimal("1"),
            rounding=ROUND_DOWN,
        )
        pct = (self.max_weight * Decimal("100")).quantize(Decimal("0.01"))
        return SizingRecommendation(
            symbol=position.instrument.symbol,
            quantity_to_reduce=quantity,
            message=(
                f"Reduce {quantity} shares to bring "
                f"{position.instrument.symbol} back to {pct}% of NAV."
            ),
        )
