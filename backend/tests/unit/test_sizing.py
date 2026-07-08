from decimal import Decimal

from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Instrument, Position
from pa_investing.sizing.models import MaxNavWeightSizingModel


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
