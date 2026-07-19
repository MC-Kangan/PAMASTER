from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from pa_investing.analytics.performance import latest_snapshot_per_day
from pa_investing.domain.models import PortfolioSnapshot


class IndicativeDailyPnlPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    calendar_date: date
    observed_at: datetime
    comparison_date: date | None
    ending_nav: Decimal
    pnl_amount: Decimal | None
    pnl_percent: Decimal | None
    reporting_coverage: Decimal


class IndicativeDailyPnlHistory(BaseModel):
    model_config = ConfigDict(frozen=True)

    reporting_currency: str | None
    latest_nav: Decimal | None
    latest_observed_at: datetime | None
    dtd_pnl_amount: Decimal | None
    dtd_pnl_percent: Decimal | None
    indicative: bool = True
    points: list[IndicativeDailyPnlPoint]


def build_indicative_daily_pnl(
    snapshots: list[PortfolioSnapshot],
) -> IndicativeDailyPnlHistory:
    if not snapshots:
        return IndicativeDailyPnlHistory(
            reporting_currency=None,
            latest_nav=None,
            latest_observed_at=None,
            dtd_pnl_amount=None,
            dtd_pnl_percent=None,
            points=[],
        )

    latest_snapshot = max(snapshots, key=lambda snapshot: snapshot.observed_at)
    reporting_currency = latest_snapshot.base_currency
    daily_snapshots = latest_snapshot_per_day(
        [
            snapshot
            for snapshot in snapshots
            if snapshot.base_currency == reporting_currency
        ]
    )

    points: list[IndicativeDailyPnlPoint] = []
    previous_snapshot: PortfolioSnapshot | None = None
    for snapshot in daily_snapshots:
        pnl_amount: Decimal | None = None
        pnl_percent: Decimal | None = None
        comparison_date: date | None = None
        if previous_snapshot is not None:
            pnl_amount = snapshot.nav - previous_snapshot.nav
            comparison_date = previous_snapshot.observed_at.date()
            if previous_snapshot.nav != 0:
                pnl_percent = pnl_amount / previous_snapshot.nav

        points.append(
            IndicativeDailyPnlPoint(
                calendar_date=snapshot.observed_at.date(),
                observed_at=snapshot.observed_at,
                comparison_date=comparison_date,
                ending_nav=snapshot.nav,
                pnl_amount=pnl_amount,
                pnl_percent=pnl_percent,
                reporting_coverage=snapshot.reporting_coverage,
            )
        )
        previous_snapshot = snapshot

    latest_point = points[-1]
    return IndicativeDailyPnlHistory(
        reporting_currency=reporting_currency,
        latest_nav=latest_point.ending_nav,
        latest_observed_at=latest_point.observed_at,
        dtd_pnl_amount=latest_point.pnl_amount,
        dtd_pnl_percent=latest_point.pnl_percent,
        points=points,
    )
