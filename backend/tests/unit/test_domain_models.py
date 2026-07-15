from datetime import UTC, datetime
from decimal import Decimal

import pytest

from pa_investing.domain.enums import (
    AssetClass,
    CostBasisStatus,
    SignalSeverity,
    SignalStatus,
    SignalType,
)
from pa_investing.domain.models import (
    Instrument,
    InstrumentIdentifier,
    Position,
    PricePoint,
    Signal,
)


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


def test_instrument_normalizes_generic_identity_metadata() -> None:
    instrument = Instrument(
        symbol="smh",
        name="VanEck Semiconductor ETF",
        asset_class=AssetClass.ETF,
        currency="usd",
        venue="lseetf",
        identifiers=(
            InstrumentIdentifier(
                provider="IBKR",
                identifier_type="CONID",
                value=" 12345 ",
            ),
        ),
    )

    assert instrument.symbol == "SMH"
    assert instrument.currency == "USD"
    assert instrument.venue == "LSEETF"
    assert instrument.identifiers[0].provider == "ibkr"
    assert instrument.identifiers[0].identifier_type == "conid"
    assert instrument.identifiers[0].value == "12345"


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


def test_position_cost_basis_status_defaults_to_unavailable() -> None:
    """Position should default to unavailable when no cost basis status is provided."""
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

    assert position.cost_basis_status == CostBasisStatus.UNAVAILABLE


@pytest.mark.parametrize(
    "status",
    [
        CostBasisStatus.BROKER,
        CostBasisStatus.TRADE_RECONSTRUCTED,
        CostBasisStatus.UNAVAILABLE,
    ],
)
def test_position_accepts_explicit_cost_basis_status(status: CostBasisStatus) -> None:
    """Position round-trips an explicit cost basis status."""
    instrument = Instrument(
        symbol="SPGI",
        name="S&P Global Inc.",
        asset_class=AssetClass.EQUITY,
        currency="USD",
    )
    position = Position(
        account_id="acct-1",
        instrument=instrument,
        quantity=Decimal("10"),
        average_cost=Decimal("420.5"),
        latest_price=Decimal("510.25"),
        cost_basis_status=status,
    )

    assert position.cost_basis_status == status


def test_position_rejects_manual_status_without_override() -> None:
    with pytest.raises(ValueError, match="manual cost status requires an override"):
        Position(
            account_id="acct-1",
            instrument=Instrument(
                symbol="AAPL",
                name="Apple Inc.",
                asset_class=AssetClass.EQUITY,
            ),
            quantity=Decimal("1"),
            average_cost=Decimal("125"),
            cost_basis_status=CostBasisStatus.MANUAL,
        )


def test_position_applies_and_clears_explicit_zero_cost_override() -> None:
    position = Position(
        account_id="acct-1",
        instrument=Instrument(
            symbol="FREE",
            name="Free Signup Share",
            asset_class=AssetClass.EQUITY,
        ),
        quantity=Decimal("1"),
        average_cost=Decimal("125"),
        latest_price=Decimal("140"),
        cost_basis_status=CostBasisStatus.BROKER,
        broker_average_cost=Decimal("125"),
        broker_cost_basis_status=CostBasisStatus.BROKER,
    )

    position.apply_manual_average_cost(Decimal("0"))

    assert position.manual_average_cost == Decimal("0")
    assert position.average_cost == Decimal("0")
    assert position.cost_basis_status == CostBasisStatus.MANUAL

    position.apply_manual_average_cost(None)

    assert position.manual_average_cost is None
    assert position.average_cost == Decimal("125")
    assert position.cost_basis_status == CostBasisStatus.BROKER


def test_position_rejects_negative_manual_cost_override() -> None:
    position = Position(
        account_id="acct-1",
        instrument=Instrument(
            symbol="AAPL",
            name="Apple Inc.",
            asset_class=AssetClass.EQUITY,
        ),
        quantity=Decimal("1"),
        average_cost=Decimal("125"),
        cost_basis_status=CostBasisStatus.BROKER,
        broker_average_cost=Decimal("125"),
        broker_cost_basis_status=CostBasisStatus.BROKER,
    )

    with pytest.raises(ValueError, match="manual average cost cannot be negative"):
        position.apply_manual_average_cost(Decimal("-1"))
