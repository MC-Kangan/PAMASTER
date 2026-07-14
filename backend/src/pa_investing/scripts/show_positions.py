from collections.abc import Callable
from decimal import Decimal

from sqlalchemy import select

from pa_investing.core.config import Settings
from pa_investing.db.models import AccountRecord
from pa_investing.db.repositories import PositionRepository
from pa_investing.db.session import DatabaseSessionFactory


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
            "account_id | symbol | name | asset_class | currency | "
            "quantity | avg_cost | price | mv"
        )
        for position in positions:
            print(
                " | ".join(
                    [
                        position.account_id,
                        position.instrument.symbol,
                        position.instrument.name,
                        position.instrument.asset_class.value,
                        position.instrument.currency,
                        _format_decimal(position.quantity),
                        _format_decimal(position.average_cost),
                        _format_decimal(position.latest_price),
                        _format_decimal(position.market_value),
                    ]
                )
            )


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    return f"{value.normalize():f}"


def main() -> None:
    show_positions()


if __name__ == "__main__":
    main()
