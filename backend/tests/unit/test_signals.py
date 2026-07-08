from decimal import Decimal

from pa_investing.domain.enums import AssetClass, SignalSeverity, SignalType
from pa_investing.domain.models import Instrument, Position
from pa_investing.signals.rules import StopReferenceRule
from pa_investing.sizing.models import MaxNavWeightSizingModel


def test_stop_reference_rule_creates_signal_when_price_breaches_stop() -> None:
    position = Position(
        account_id="manual-pa",
        instrument=Instrument(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.EQUITY),
        quantity=Decimal("100"),
        average_cost=Decimal("100"),
        latest_price=Decimal("90"),
    )
    rule = StopReferenceRule(sizing_model=MaxNavWeightSizingModel(max_weight=Decimal("0.10")))

    signal = rule.evaluate(
        position=position,
        stop_price=Decimal("95"),
        portfolio_nav=Decimal("100000"),
    )

    assert signal is not None
    assert signal.symbol == "AAPL"
    assert signal.signal_type == SignalType.STOP_REFERENCE
    assert signal.severity == SignalSeverity.HIGH
    assert "stop/reference level 95" in signal.message
    assert signal.deterministic_recommendation.startswith("Reduce")
