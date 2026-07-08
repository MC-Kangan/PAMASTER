from datetime import datetime

from pa_investing.analytics.metrics import (
    calculate_gross_exposure,
    calculate_nav,
    calculate_unrealized_pnl,
)
from pa_investing.domain.models import PortfolioSnapshot, Position


def build_portfolio_snapshot(
    snapshot_id: str,
    positions: list[Position],
    observed_at: datetime,
    base_currency: str,
) -> PortfolioSnapshot:
    nav = calculate_nav(positions)
    unrealized_pnl = calculate_unrealized_pnl(positions)
    return PortfolioSnapshot(
        snapshot_id=snapshot_id,
        observed_at=observed_at,
        base_currency=base_currency,
        nav=nav,
        gross_exposure=calculate_gross_exposure(positions),
        net_exposure=nav,
        unrealized_pnl=unrealized_pnl,
    )
