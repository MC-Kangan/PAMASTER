from decimal import Decimal

from pa_investing.domain.enums import AssetClass, SignalSeverity, SignalType
from pa_investing.domain.models import Instrument, Position
from pa_investing.signals.rules import StopReferenceRule
from pa_investing.signals.service import SignalService
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
    assert signal.analytics_path is not None
    assert signal.analytics_path.endswith(signal.signal_id)


def test_stop_reference_rule_ignores_invalid_latest_prices() -> None:
    rule = StopReferenceRule(sizing_model=MaxNavWeightSizingModel(max_weight=Decimal("0.10")))

    for latest_price in (None, Decimal("0"), Decimal("-1")):
        position = Position(
            account_id="manual-pa",
            instrument=Instrument(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.EQUITY),
            quantity=Decimal("100"),
            average_cost=Decimal("100"),
            latest_price=latest_price,
        )

        signal = rule.evaluate(
            position=position,
            stop_price=Decimal("95"),
            portfolio_nav=Decimal("100000"),
        )

        assert signal is None


def test_signal_service_returns_signals_only_for_matching_breached_stops() -> None:
    positions = [
        Position(
            account_id="manual-pa",
            instrument=Instrument(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.EQUITY),
            quantity=Decimal("100"),
            average_cost=Decimal("100"),
            latest_price=Decimal("90"),
        ),
        Position(
            account_id="manual-pa",
            instrument=Instrument(symbol="MSFT", name="Microsoft", asset_class=AssetClass.EQUITY),
            quantity=Decimal("100"),
            average_cost=Decimal("100"),
            latest_price=Decimal("410"),
        ),
        Position(
            account_id="manual-pa",
            instrument=Instrument(symbol="NVDA", name="NVIDIA", asset_class=AssetClass.EQUITY),
            quantity=Decimal("100"),
            average_cost=Decimal("100"),
            latest_price=Decimal("120"),
        ),
    ]
    service = SignalService(
        stop_rule=StopReferenceRule(
            sizing_model=MaxNavWeightSizingModel(max_weight=Decimal("0.10"))
        )
    )

    signals = service.evaluate_stop_rules(
        positions=positions,
        stop_prices={
            "AAPL": Decimal("95"),
            "MSFT": Decimal("400"),
            "TSLA": Decimal("200"),
        },
        portfolio_nav=Decimal("100000"),
    )

    assert [signal.symbol for signal in signals] == ["AAPL"]
    assert all(signal.signal_type == SignalType.STOP_REFERENCE for signal in signals)
