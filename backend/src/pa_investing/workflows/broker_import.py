from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from pa_investing.brokers.interfaces import BrokerConnector
from pa_investing.db.repositories import (
    AccountRepository,
    PositionRepository,
    PriceRepository,
)
from pa_investing.domain.enums import CostBasisStatus, QuoteQuality
from pa_investing.domain.models import Account, PricePoint


@dataclass(frozen=True)
class BrokerImportResult:
    accounts_imported: int
    positions_imported: int
    positions_closed: int
    skipped_positions: list[dict[str, str]]
    cost_basis_available: int = 0
    cost_basis_missing: int = 0
    missing_cost_basis_positions: list[dict[str, str]] | None = None


class BrokerImportWorkflow:
    def __init__(
        self,
        connector: BrokerConnector,
        account_repository: AccountRepository,
        position_repository: PositionRepository,
        commit: Callable[[], None],
        price_repository: PriceRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.connector = connector
        self.account_repository = account_repository
        self.position_repository = position_repository
        self.commit = commit
        self.price_repository = price_repository
        self.clock = clock or (lambda: datetime.now(tz=UTC))

    def run(self) -> BrokerImportResult:
        accounts = self.connector.list_accounts()
        positions = self.connector.fetch_positions()
        if not accounts and not positions:
            raise RuntimeError("IBKR import returned no supported accounts or positions")

        accounts_by_id = {account.account_id: account for account in accounts}
        for position in positions:
            if position.account_id not in accounts_by_id:
                accounts_by_id[position.account_id] = Account(
                    account_id=position.account_id,
                    name=position.account_id,
                    source="ibkr",
                    base_currency=position.instrument.currency,
                )

        for account in accounts_by_id.values():
            self.account_repository.upsert(account)
        imported_at = self.clock()
        for position in positions:
            if position.latest_price is None:
                continue
            account = accounts_by_id[position.account_id]
            position.latest_price_observed_at = imported_at
            if account.source == "ibkr-flex":
                position.latest_price_provider = "ibkr_flex_eod"
                position.latest_price_quality = QuoteQuality.EOD_FALLBACK
            else:
                position.latest_price_provider = account.source
                position.latest_price_quality = QuoteQuality.DELAYED
        effective_positions = [
            self.position_repository.upsert_broker_position(position)
            for position in positions
        ]
        imported_instrument_ids_by_account: dict[str, set[str]] = {}
        for position in effective_positions:
            instrument_id = position.instrument.instrument_id
            if instrument_id is None:
                raise RuntimeError("persisted instrument is missing its internal id")
            imported_instrument_ids_by_account.setdefault(
                position.account_id,
                set(),
            ).add(instrument_id)
            if self.price_repository is not None and position.latest_price is not None:
                self.price_repository.upsert(
                    PricePoint(
                        instrument=position.instrument,
                        price=position.latest_price,
                        observed_at=position.latest_price_observed_at or imported_at,
                        provider=position.latest_price_provider or "broker_eod",
                        quote_currency=position.instrument.currency,
                        provider_symbol=position.instrument.symbol,
                        provider_exchange=position.instrument.venue,
                        quality=(
                            position.latest_price_quality
                            or QuoteQuality.EOD_FALLBACK
                        ),
                    )
                )

        positions_closed = self.position_repository.close_positions_missing_from_snapshot(
            set(accounts_by_id),
            imported_instrument_ids_by_account,
        )
        self.commit()

        cost_basis_available = 0
        cost_basis_missing = 0
        missing_cost_basis_positions: list[dict[str, str]] = []
        for position in effective_positions:
            if position.cost_basis_status == CostBasisStatus.UNAVAILABLE:
                cost_basis_missing += 1
                missing_cost_basis_positions.append(
                    {
                        "account_id": position.account_id,
                        "symbol": position.instrument.symbol,
                        "reason": "cost basis unavailable",
                    }
                )
            else:
                cost_basis_available += 1

        return BrokerImportResult(
            accounts_imported=len(accounts_by_id),
            positions_imported=len(positions),
            positions_closed=positions_closed,
            skipped_positions=getattr(self.connector, "last_skipped_positions", []),
            cost_basis_available=cost_basis_available,
            cost_basis_missing=cost_basis_missing,
            missing_cost_basis_positions=missing_cost_basis_positions or None,
        )
