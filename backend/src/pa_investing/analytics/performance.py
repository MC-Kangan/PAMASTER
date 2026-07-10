from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from pa_investing.domain.models import PortfolioSnapshot


class PerformancePoint(BaseModel):
    observed_at: datetime
    nav: Decimal
    unrealized_pnl: Decimal
    peak_nav: Decimal
    drawdown: Decimal
    simple_return: Decimal


class PerformanceHistory(BaseModel):
    points: list[PerformancePoint]
    start_observed_at: datetime | None
    end_observed_at: datetime | None
    starting_nav: Decimal | None
    ending_nav: Decimal | None
    simple_return: Decimal | None
    max_drawdown: Decimal | None


def build_performance_history(snapshots: list[PortfolioSnapshot]) -> PerformanceHistory:
    if not snapshots:
        return PerformanceHistory(
            points=[],
            start_observed_at=None,
            end_observed_at=None,
            starting_nav=None,
            ending_nav=None,
            simple_return=None,
            max_drawdown=None,
        )

    sorted_snapshots = sorted(snapshots, key=lambda snapshot: snapshot.observed_at)
    first_nav = sorted_snapshots[0].nav
    peak_nav = first_nav
    max_drawdown = Decimal("0")
    points: list[PerformancePoint] = []

    for snapshot in sorted_snapshots:
        peak_nav = max(peak_nav, snapshot.nav)
        drawdown = Decimal("0")
        if peak_nav != 0:
            drawdown = (snapshot.nav - peak_nav) / peak_nav
        simple_return = Decimal("0")
        if first_nav != 0:
            simple_return = (snapshot.nav / first_nav) - Decimal("1")
        max_drawdown = min(max_drawdown, drawdown)
        points.append(
            PerformancePoint(
                observed_at=snapshot.observed_at,
                nav=snapshot.nav,
                unrealized_pnl=snapshot.unrealized_pnl,
                peak_nav=peak_nav,
                drawdown=drawdown,
                simple_return=simple_return,
            )
        )

    return PerformanceHistory(
        points=points,
        start_observed_at=points[0].observed_at,
        end_observed_at=points[-1].observed_at,
        starting_nav=points[0].nav,
        ending_nav=points[-1].nav,
        simple_return=points[-1].simple_return,
        max_drawdown=max_drawdown,
    )
