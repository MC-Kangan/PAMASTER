from collections.abc import Callable
from dataclasses import dataclass

from pa_investing.brokers.interfaces import BrokerConnector
from pa_investing.db.repositories import AccountRepository, PositionRepository
from pa_investing.domain.models import Account


@dataclass(frozen=True)
class BrokerImportResult:
    accounts_imported: int
    positions_imported: int
    positions_closed: int
    skipped_positions: list[dict[str, str]]


class BrokerImportWorkflow:
    def __init__(
        self,
        connector: BrokerConnector,
        account_repository: AccountRepository,
        position_repository: PositionRepository,
        commit: Callable[[], None],
    ) -> None:
        self.connector = connector
        self.account_repository = account_repository
        self.position_repository = position_repository
        self.commit = commit

    def run(self) -> BrokerImportResult:
        accounts = self.connector.list_accounts()
        positions = self.connector.fetch_positions()
        if not accounts and not positions:
            raise RuntimeError("IBKR import returned no supported accounts or positions")

        accounts_by_id = {account.account_id: account for account in accounts}
        imported_symbols_by_account: dict[str, set[str]] = {}

        for position in positions:
            imported_symbols_by_account.setdefault(position.account_id, set()).add(
                position.instrument.symbol
            )
            if position.account_id not in accounts_by_id:
                accounts_by_id[position.account_id] = Account(
                    account_id=position.account_id,
                    name=position.account_id,
                    source="ibkr",
                    base_currency=position.instrument.currency,
                )

        for account in accounts_by_id.values():
            self.account_repository.upsert(account)
        for position in positions:
            self.position_repository.upsert(position)

        positions_closed = self.position_repository.close_positions_missing_from_snapshot(
            set(accounts_by_id),
            imported_symbols_by_account,
        )
        self.commit()

        return BrokerImportResult(
            accounts_imported=len(accounts_by_id),
            positions_imported=len(positions),
            positions_closed=positions_closed,
            skipped_positions=getattr(self.connector, "last_skipped_positions", []),
        )
