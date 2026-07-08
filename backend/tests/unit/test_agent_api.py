from decimal import Decimal

from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Instrument, Position
from pa_investing.workflows.agent_api import AgentAPI


def test_agent_api_daily_review_returns_snapshot_and_signals() -> None:
    positions = [
        Position(
            account_id="manual-pa",
            instrument=Instrument(
                symbol="AAPL",
                name="Apple Inc.",
                asset_class=AssetClass.EQUITY,
            ),
            quantity=Decimal("100"),
            average_cost=Decimal("100"),
            latest_price=Decimal("90"),
        )
    ]
    api = AgentAPI()

    result = api.run_daily_review(positions=positions, stop_prices={"AAPL": Decimal("95")})

    assert result.snapshot.nav == Decimal("9000")
    assert len(result.signals) == 1
    assert result.signals[0].symbol == "AAPL"
