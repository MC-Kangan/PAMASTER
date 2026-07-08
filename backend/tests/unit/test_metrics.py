from datetime import UTC, datetime
from decimal import Decimal

from pa_investing.analytics.metrics import calculate_exposure_by_asset_class, calculate_nav
from pa_investing.analytics.snapshots import build_portfolio_snapshot
from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Instrument, Position


def _position(
    symbol: str, asset_class: AssetClass, quantity: str, cost: str, price: str
) -> Position:
    return Position(
        account_id="manual-pa",
        instrument=Instrument(symbol=symbol, name=symbol, asset_class=asset_class),
        quantity=Decimal(quantity),
        average_cost=Decimal(cost),
        latest_price=Decimal(price),
    )


def test_calculate_nav_and_exposure() -> None:
    positions = [
        _position("AAPL", AssetClass.EQUITY, "10", "150", "175"),
        _position("SPY", AssetClass.ETF, "5", "500", "510"),
    ]

    assert calculate_nav(positions) == Decimal("4300")
    assert calculate_exposure_by_asset_class(positions) == {
        AssetClass.EQUITY: Decimal("1750"),
        AssetClass.ETF: Decimal("2550"),
    }


def test_build_portfolio_snapshot() -> None:
    positions = [_position("AAPL", AssetClass.EQUITY, "10", "150", "175")]

    snapshot = build_portfolio_snapshot(
        snapshot_id="snap-1",
        positions=positions,
        observed_at=datetime(2026, 7, 8, tzinfo=UTC),
        base_currency="USD",
    )

    assert snapshot.nav == Decimal("1750")
    assert snapshot.unrealized_pnl == Decimal("250")
    assert snapshot.gross_exposure == Decimal("1750")


def test_signed_positions_use_absolute_gross_exposure() -> None:
    positions = [
        _position("AAPL", AssetClass.EQUITY, "10", "100", "100"),
        _position("TSLA", AssetClass.EQUITY, "-20", "100", "100"),
    ]

    snapshot = build_portfolio_snapshot(
        snapshot_id="snap-2",
        positions=positions,
        observed_at=datetime(2026, 7, 8, tzinfo=UTC),
        base_currency="USD",
    )

    assert calculate_nav(positions) == Decimal("-1000")
    assert calculate_exposure_by_asset_class(positions) == {
        AssetClass.EQUITY: Decimal("3000"),
    }
    assert snapshot.net_exposure == Decimal("-1000")
    assert snapshot.gross_exposure == Decimal("3000")
