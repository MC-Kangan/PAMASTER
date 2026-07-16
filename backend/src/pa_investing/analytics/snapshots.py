from datetime import datetime
from decimal import Decimal

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
    reporting_mode = any(
        position.reporting_currency == base_currency.upper()
        for position in positions
    )
    if reporting_mode:
        reporting_values = [
            position.reporting_market_value
            for position in positions
            if position.reporting_market_value is not None
        ]
        nav = sum(reporting_values, Decimal("0"))
        gross_exposure = sum((abs(value) for value in reporting_values), Decimal("0"))
        unrealized_pnl = sum(
            (
                position.reporting_unrealized_pnl
                for position in positions
                if position.reporting_unrealized_pnl is not None
            ),
            Decimal("0"),
        )
        valued_count = len(reporting_values)
    else:
        nav = calculate_nav(positions)
        gross_exposure = calculate_gross_exposure(positions)
        unrealized_pnl = calculate_unrealized_pnl(positions)
        valued_count = len(positions)
    coverage = (
        Decimal("1")
        if not positions
        else Decimal(valued_count) / Decimal(len(positions))
    )
    return PortfolioSnapshot(
        snapshot_id=snapshot_id,
        observed_at=observed_at,
        base_currency=base_currency,
        nav=nav,
        gross_exposure=gross_exposure,
        net_exposure=nav,
        unrealized_pnl=unrealized_pnl,
        position_count=len(positions),
        valued_position_count=valued_count,
        reporting_coverage=coverage,
    )
