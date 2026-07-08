from datetime import UTC, datetime
from decimal import Decimal

from pa_investing.domain.enums import AssetClass, SignalSeverity, SignalStatus, SignalType
from pa_investing.domain.models import Instrument, Position, PricePoint, Signal


def test_position_market_value_uses_latest_price() -> None:
    instrument = Instrument(
        symbol="AAPL",
        name="Apple Inc.",
        asset_class=AssetClass.EQUITY,
        currency="USD",
    )
    position = Position(
        account_id="acct-1",
        instrument=instrument,
        quantity=Decimal("10"),
        average_cost=Decimal("150"),
        latest_price=Decimal("175"),
    )

    assert position.market_value == Decimal("1750")
    assert position.unrealized_pnl == Decimal("250")


def test_signal_contains_deterministic_recommendation_fields() -> None:
    signal = Signal(
        signal_id="sig-1",
        symbol="AAPL",
        signal_type=SignalType.STOP_REFERENCE,
        severity=SignalSeverity.HIGH,
        status=SignalStatus.OPEN,
        message="Reference stop was breached.",
        deterministic_recommendation="Reduce 2 shares",
        audit_id="audit-1",
        created_at=datetime(2026, 7, 8, tzinfo=UTC),
    )

    assert signal.symbol == "AAPL"
    assert signal.deterministic_recommendation == "Reduce 2 shares"


def test_price_point_rejects_non_positive_price() -> None:
    instrument = Instrument(
        symbol="BTC-USD",
        name="Bitcoin",
        asset_class=AssetClass.CRYPTO,
        currency="USD",
    )

    try:
        PricePoint(
            instrument=instrument,
            price=Decimal("0"),
            observed_at=datetime(2026, 7, 8, tzinfo=UTC),
        )
    except ValueError as exc:
        assert "price must be positive" in str(exc)
    else:
        raise AssertionError("PricePoint accepted a non-positive price")
