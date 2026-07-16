from collections.abc import Callable
from decimal import Decimal

from sqlalchemy import select

from pa_investing.analytics.metrics import (
    calculate_exposure_by_currency,
    calculate_portfolio_summary,
    calculate_unrealized_pnl_by_currency,
)
from pa_investing.core.config import Settings
from pa_investing.db.models import AccountRecord
from pa_investing.db.repositories import PositionRepository
from pa_investing.db.session import DatabaseSessionFactory
from pa_investing.domain.enums import CostBasisStatus


def show_positions(
    *,
    settings: Settings | None = None,
    session_factory: Callable[[], object] | None = None,
) -> None:
    resolved_settings = settings or Settings()
    resolved_session_factory = session_factory or DatabaseSessionFactory(resolved_settings).session

    with resolved_session_factory() as session:
        accounts = session.scalars(select(AccountRecord).order_by(AccountRecord.account_id)).all()
        positions = sorted(
            PositionRepository(session).list_open_positions(),
            key=lambda position: (position.account_id, position.instrument.symbol),
        )

        print(f"Accounts: {len(accounts)}")
        for account in accounts:
            print(
                f"- {account.account_id} | {account.name} | "
                f"{account.source} | {account.base_currency}"
            )

        print(f"Open positions: {len(positions)}")
        print(
            "account_id | instrument_id | symbol | name | asset_class | currency | "
            "quantity | avg_cost | price | mv | cost_basis_status | unrealized_pnl"
        )
        for position in positions:
            print(
                " | ".join(
                    [
                        position.account_id,
                        position.instrument.instrument_id or "",
                        position.instrument.symbol,
                        position.instrument.name,
                        position.instrument.asset_class.value,
                        position.instrument.currency,
                        _format_decimal(position.quantity),
                        _format_decimal(position.average_cost),
                        _format_decimal(position.latest_price),
                        _format_decimal(position.market_value),
                        position.cost_basis_status.value,
                        (
                            "unavailable"
                            if position.cost_basis_status == CostBasisStatus.UNAVAILABLE
                            else _format_decimal(position.unrealized_pnl)
                        ),
                    ]
                )
            )

        # Portfolio summary
        summary = calculate_portfolio_summary(positions)
        exposure_by_currency = calculate_exposure_by_currency(positions)
        pnl_by_currency = calculate_unrealized_pnl_by_currency(positions)

        print()
        print("Portfolio summary")
        print(f"- total market value: {_format_decimal(summary['total_market_value'])}")
        print(f"- positions: {summary['position_count']}")
        print(f"- cost basis available: {summary['cost_basis_available']}")
        print(f"- cost basis missing: {summary['cost_basis_missing']}")
        print()
        print("Market value by currency:")
        for currency in sorted(exposure_by_currency):
            print(f"  {currency}: {_format_decimal(exposure_by_currency[currency])}")
        print()
        print("Unrealized PnL by currency (excluding unavailable cost basis):")
        if pnl_by_currency:
            for currency in sorted(pnl_by_currency):
                print(f"  {currency}: {_format_decimal(pnl_by_currency[currency])}")
        else:
            print("  (none)")
        print()
        print("Cost basis warnings:")
        warnings = [
            position for position in positions
            if position.cost_basis_status == CostBasisStatus.UNAVAILABLE
        ]
        if warnings:
            for position in warnings:
                print(
                    f"- missing cost basis {position.account_id} "
                    f"{position.instrument.symbol}"
                )
        else:
            print("  (none)")


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    return f"{value.normalize():f}"


def main() -> None:
    show_positions()


if __name__ == "__main__":
    main()
