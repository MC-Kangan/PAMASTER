from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pa_investing.domain.models import FxRatePoint, Position


@dataclass(frozen=True)
class ReportingCoverage:
    position_count: int
    valued_position_count: int

    @property
    def ratio(self) -> Decimal:
        if self.position_count == 0:
            return Decimal("1")
        return Decimal(self.valued_position_count) / Decimal(self.position_count)


def apply_reporting_currency(
    positions: list[Position],
    reporting_currency: str,
    fx_rates: dict[tuple[str, str], FxRatePoint],
    *,
    now: datetime | None = None,
    stale_after: timedelta = timedelta(days=5),
) -> ReportingCoverage:
    reporting_currency = reporting_currency.upper()
    observed_now = now or datetime.now(tz=UTC)
    valued = 0
    for position in positions:
        position.reporting_currency = reporting_currency
        local_currency = position.instrument.currency.upper()
        if local_currency == reporting_currency:
            position.fx_rate = Decimal("1")
            position.fx_observed_at = observed_now
            position.fx_provider = "identity"
            position.fx_stale = False
            if position.latest_price is not None:
                valued += 1
            continue

        point = fx_rates.get((local_currency, reporting_currency))
        if point is None:
            position.fx_rate = None
            position.fx_observed_at = None
            position.fx_provider = None
            position.fx_stale = False
            continue
        position.fx_rate = point.rate
        position.fx_observed_at = point.observed_at
        position.fx_provider = point.provider
        position.fx_stale = observed_now - point.observed_at > stale_after
        if position.latest_price is not None:
            valued += 1

    return ReportingCoverage(
        position_count=len(positions),
        valued_position_count=valued,
    )
