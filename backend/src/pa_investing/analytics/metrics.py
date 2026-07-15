from collections import defaultdict
from decimal import Decimal

from pa_investing.domain.enums import AssetClass, CostBasisStatus
from pa_investing.domain.models import Position


def calculate_nav(positions: list[Position]) -> Decimal:
    return sum((position.market_value for position in positions), Decimal("0"))


def calculate_unrealized_pnl(positions: list[Position]) -> Decimal:
    return sum(
        (
            position.unrealized_pnl
            for position in positions
            if position.cost_basis_status != CostBasisStatus.UNAVAILABLE
        ),
        Decimal("0"),
    )


def calculate_gross_exposure(positions: list[Position]) -> Decimal:
    return sum((abs(position.market_value) for position in positions), Decimal("0"))


def calculate_exposure_by_asset_class(positions: list[Position]) -> dict[AssetClass, Decimal]:
    exposure: defaultdict[AssetClass, Decimal] = defaultdict(lambda: Decimal("0"))
    for position in positions:
        exposure[position.instrument.asset_class] += abs(position.market_value)
    return dict(exposure)


def calculate_exposure_by_account(positions: list[Position]) -> dict[str, Decimal]:
    exposure: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for position in positions:
        exposure[position.account_id] += abs(position.market_value)
    return dict(exposure)


def calculate_exposure_by_currency(positions: list[Position]) -> dict[str, Decimal]:
    exposure: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for position in positions:
        exposure[position.instrument.currency] += abs(position.market_value)
    return dict(exposure)


def calculate_unrealized_pnl_by_currency(
    positions: list[Position],
) -> dict[str, Decimal]:
    pnl: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for position in positions:
        if position.cost_basis_status == CostBasisStatus.UNAVAILABLE:
            continue
        pnl[position.instrument.currency] += position.unrealized_pnl
    return dict(pnl)


def calculate_portfolio_summary(
    positions: list[Position],
) -> dict:
    total_market_value = sum((position.market_value for position in positions), Decimal("0"))
    total_cost_basis = Decimal("0")
    cost_basis_available = 0
    cost_basis_missing = 0
    unrealized_pnl_reliable = Decimal("0")
    account_ids: list[str] = []

    for position in positions:
        if position.cost_basis_status == CostBasisStatus.UNAVAILABLE:
            cost_basis_missing += 1
        else:
            cost_basis_available += 1
            total_cost_basis += position.cost_basis
            unrealized_pnl_reliable += position.unrealized_pnl

        if position.account_id not in account_ids:
            account_ids.append(position.account_id)

    return {
        "total_market_value": total_market_value,
        "total_cost_basis": total_cost_basis,
        "cost_basis_available": cost_basis_available,
        "cost_basis_missing": cost_basis_missing,
        "unrealized_pnl_reliable": unrealized_pnl_reliable,
        "position_count": len(positions),
        "account_ids": account_ids,
    }
