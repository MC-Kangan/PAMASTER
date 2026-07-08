from decimal import Decimal

import pytest

from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Instrument, Position
from pa_investing.sizing.models import MaxNavWeightSizingModel


def test_max_nav_weight_model_validates_weight_range() -> None:
    invalid_weights = (Decimal("-0.01"), Decimal("0"), Decimal("1.01"))

    for invalid_weight in invalid_weights:
        try:
            MaxNavWeightSizingModel(max_weight=invalid_weight)
        except ValueError as exc:
            assert str(exc) == "max_weight must be greater than 0 and less than or equal to 1"
        else:
            raise AssertionError(f"Expected ValueError for max_weight={invalid_weight}")


def test_max_nav_weight_model_recommends_share_reduction() -> None:
    position = Position(
        account_id="manual-pa",
        instrument=Instrument(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.EQUITY),
        quantity=Decimal("100"),
        average_cost=Decimal("100"),
        latest_price=Decimal("200"),
    )
    model = MaxNavWeightSizingModel(max_weight=Decimal("0.10"))

    recommendation = model.recommend_reduction(position=position, portfolio_nav=Decimal("100000"))

    assert recommendation.quantity_to_reduce == Decimal("50")
    assert recommendation.message == "Reduce 50 shares to bring AAPL back to 10.00% of NAV."


@pytest.mark.parametrize("latest_price", [None, Decimal("0"), Decimal("-1")])
def test_max_nav_weight_model_returns_zero_reduction_for_missing_or_non_positive_price(
    latest_price: Decimal | None,
) -> None:
    position = Position(
        account_id="manual-pa",
        instrument=Instrument(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.EQUITY),
        quantity=Decimal("100"),
        average_cost=Decimal("100"),
        latest_price=latest_price,
    )
    model = MaxNavWeightSizingModel(max_weight=Decimal("0.10"))

    recommendation = model.recommend_reduction(position=position, portfolio_nav=Decimal("100000"))

    assert recommendation.quantity_to_reduce == Decimal("0")
    assert recommendation.message == (
        "No reduction for AAPL; missing, zero, or negative latest price."
    )
