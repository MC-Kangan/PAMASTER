from datetime import UTC, datetime
from decimal import Decimal

from pa_investing.analytics.metrics import (
    calculate_exposure_by_account,
    calculate_exposure_by_asset_class,
    calculate_exposure_by_currency,
    calculate_nav,
    calculate_portfolio_summary,
    calculate_unrealized_pnl,
    calculate_unrealized_pnl_by_currency,
)
from pa_investing.analytics.snapshots import build_portfolio_snapshot
from pa_investing.domain.enums import AssetClass, CostBasisStatus
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
        cost_basis_status=CostBasisStatus.BROKER,
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


# --- Portfolio summary tests (Task 5) ---


def _pos(
    account_id: str,
    symbol: str,
    asset_class: AssetClass,
    currency: str,
    quantity: str,
    cost: str,
    price: str,
    cost_basis_status: CostBasisStatus = CostBasisStatus.BROKER,
) -> Position:
    return Position(
        account_id=account_id,
        instrument=Instrument(
            symbol=symbol, name=symbol, asset_class=asset_class, currency=currency
        ),
        quantity=Decimal(quantity),
        average_cost=Decimal(cost),
        latest_price=Decimal(price),
        cost_basis_status=cost_basis_status,
    )


def test_calculate_exposure_by_account() -> None:
    positions = [
        _pos("U1", "AAPL", AssetClass.EQUITY, "USD", "10", "150", "175"),
        _pos("U1", "SPY", AssetClass.ETF, "USD", "5", "500", "510"),
        _pos("U2", "SGLN", AssetClass.ETF, "GBP", "50", "41", "45"),
    ]

    exposure = calculate_exposure_by_account(positions)

    assert exposure == {
        "U1": Decimal("4300"),   # 1750 + 2550
        "U2": Decimal("2250"),   # 50 * 45
    }


def test_calculate_exposure_by_currency() -> None:
    positions = [
        _pos("U1", "AAPL", AssetClass.EQUITY, "USD", "10", "150", "175"),
        _pos("U1", "ASML", AssetClass.EQUITY, "EUR", "3", "900", "950"),
        _pos("U2", "SGLN", AssetClass.ETF, "GBP", "50", "41", "45"),
    ]

    exposure = calculate_exposure_by_currency(positions)

    assert exposure == {
        "USD": Decimal("1750"),  # 10 * 175
        "EUR": Decimal("2850"),  # 3 * 950
        "GBP": Decimal("2250"),  # 50 * 45
    }


def test_calculate_unrealized_pnl_by_currency_excludes_unavailable_cost_basis() -> None:
    positions = [
        _pos("U1", "AAPL", AssetClass.EQUITY, "USD", "10", "150", "175",
             cost_basis_status=CostBasisStatus.BROKER),
        _pos("U1", "SPY", AssetClass.ETF, "USD", "5", "500", "510",
             cost_basis_status=CostBasisStatus.BROKER),
        _pos("U1", "MBGL", AssetClass.EQUITY, "USD", "10", "12", "20",
             cost_basis_status=CostBasisStatus.UNAVAILABLE),
    ]

    pnl = calculate_unrealized_pnl_by_currency(positions)

    assert pnl == {
        "USD": Decimal("300"),  # AAPL: 250 + SPY: 50; MBGL excluded
    }

    assert calculate_unrealized_pnl(positions) == Decimal("300")


def test_calculate_portfolio_summary() -> None:
    positions = [
        _pos("U1", "AAPL", AssetClass.EQUITY, "USD", "10", "150", "175",
             cost_basis_status=CostBasisStatus.BROKER),
        _pos("U1", "SPY", AssetClass.ETF, "USD", "5", "500", "510",
             cost_basis_status=CostBasisStatus.BROKER),
        _pos("U1", "MBGL", AssetClass.EQUITY, "USD", "10", "12", "20",
             cost_basis_status=CostBasisStatus.UNAVAILABLE),
    ]

    summary = calculate_portfolio_summary(positions)

    assert summary["total_market_value"] == Decimal("4500")  # 1750 + 2550 + 200
    assert summary["total_cost_basis"] == Decimal("4000")    # reliable positions only
    assert summary["cost_basis_available"] == 2
    assert summary["cost_basis_missing"] == 1
    assert summary["unrealized_pnl_reliable"] == Decimal("300")  # AAPL + SPY only
    assert summary["position_count"] == 3
    assert summary["account_ids"] == ["U1"]


def test_calculate_portfolio_summary_empty_positions() -> None:
    summary = calculate_portfolio_summary([])

    assert summary["total_market_value"] == Decimal("0")
    assert summary["position_count"] == 0
    assert summary["account_ids"] == []
    assert summary["cost_basis_available"] == 0
    assert summary["cost_basis_missing"] == 0
