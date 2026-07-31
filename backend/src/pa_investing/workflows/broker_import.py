from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from pa_investing.brokers.interfaces import BrokerConnector
from pa_investing.db.repositories import (
    AccountRepository,
    BrokerReconciliationRepository,
    MarketDataMappingRepository,
    PositionRepository,
    PriceRepository,
    ProviderRunRepository,
    TransactionRepository,
)
from pa_investing.domain.enums import (
    CostBasisStatus,
    ProviderRunStatus,
    QuoteQuality,
)
from pa_investing.domain.models import Account, PricePoint, ProviderRun
from pa_investing.instruments.default_mappings import seed_default_yahoo_mappings


@dataclass(frozen=True)
class BrokerImportResult:
    accounts_imported: int
    positions_imported: int
    positions_closed: int
    skipped_positions: list[dict[str, str]]
    cost_basis_available: int = 0
    cost_basis_missing: int = 0
    missing_cost_basis_positions: list[dict[str, str]] | None = None
    transactions_imported: int = 0
    reconciliations_imported: int = 0
    reconciliation_warnings: int = 0
    market_data_mappings_imported: int = 0


class BrokerImportWorkflow:
    def __init__(
        self,
        connector: BrokerConnector,
        account_repository: AccountRepository,
        position_repository: PositionRepository,
        commit: Callable[[], None],
        price_repository: PriceRepository | None = None,
        transaction_repository: TransactionRepository | None = None,
        reconciliation_repository: BrokerReconciliationRepository | None = None,
        provider_run_repository: ProviderRunRepository | None = None,
        market_data_mapping_repository: MarketDataMappingRepository | None = None,
        rollback: Callable[[], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.connector = connector
        self.account_repository = account_repository
        self.position_repository = position_repository
        self.commit = commit
        self.price_repository = price_repository
        self.transaction_repository = transaction_repository
        self.reconciliation_repository = reconciliation_repository
        self.provider_run_repository = provider_run_repository
        self.market_data_mapping_repository = market_data_mapping_repository
        self.rollback = rollback
        self.clock = clock or (lambda: datetime.now(tz=UTC))

    def run(self) -> BrokerImportResult:
        started_at = self.clock()
        run = ProviderRun(
            run_id=str(uuid4()),
            provider=_connector_provider(self.connector),
            operation="broker_import",
            status=ProviderRunStatus.RUNNING,
            started_at=started_at,
        )
        if self.provider_run_repository is not None:
            self.provider_run_repository.upsert(run)
            self.commit()
        try:
            return self._run_import(run)
        except Exception as error:
            if self.provider_run_repository is not None:
                if self.rollback is not None:
                    self.rollback()
                self.provider_run_repository.upsert(
                    run.model_copy(
                        update={
                            "status": ProviderRunStatus.FAILED,
                            "finished_at": self.clock(),
                            "error_message": str(error)[:2048],
                        }
                    )
                )
                self.commit()
            raise

    def _run_import(self, run: ProviderRun) -> BrokerImportResult:
        accounts = self.connector.list_accounts()
        positions = self.connector.fetch_positions()
        transactions = self.connector.fetch_transactions()
        reconciliations = self.connector.fetch_reconciliations()
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
        for item in [*transactions, *reconciliations]:
            if item.account_id not in accounts_by_id:
                accounts_by_id[item.account_id] = Account(
                    account_id=item.account_id,
                    name=item.account_id,
                    source=_connector_provider(self.connector),
                    base_currency=getattr(item, "currency", "USD"),
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
        if self.transaction_repository is not None:
            for transaction in transactions:
                self.transaction_repository.upsert(transaction)
        if self.reconciliation_repository is not None:
            for reconciliation in reconciliations:
                self.reconciliation_repository.upsert(reconciliation)
        market_data_mappings_imported = (
            seed_default_yahoo_mappings(
                effective_positions,
                self.market_data_mapping_repository,
            )
            if self.market_data_mapping_repository is not None
            else 0
        )

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
        reconciliation_warnings = sum(
            reconciliation.status.value == "warning"
            for reconciliation in reconciliations
        )
        if self.provider_run_repository is not None:
            self.provider_run_repository.upsert(
                run.model_copy(
                    update={
                        "status": ProviderRunStatus.SUCCESS,
                        "finished_at": self.clock(),
                        "records_read": (
                            len(accounts)
                            + len(positions)
                            + len(transactions)
                            + len(reconciliations)
                        ),
                        "records_written": (
                            len(accounts_by_id)
                            + len(positions)
                            + len(transactions)
                            + len(reconciliations)
                            + market_data_mappings_imported
                        ),
                        "warning_count": (
                            len(getattr(self.connector, "last_skipped_positions", []))
                            + cost_basis_missing
                            + reconciliation_warnings
                        ),
                    }
                )
            )
        self.commit()

        return BrokerImportResult(
            accounts_imported=len(accounts_by_id),
            positions_imported=len(positions),
            positions_closed=positions_closed,
            skipped_positions=getattr(self.connector, "last_skipped_positions", []),
            cost_basis_available=cost_basis_available,
            cost_basis_missing=cost_basis_missing,
            missing_cost_basis_positions=missing_cost_basis_positions or None,
            transactions_imported=len(transactions),
            reconciliations_imported=len(reconciliations),
            reconciliation_warnings=reconciliation_warnings,
            market_data_mappings_imported=market_data_mappings_imported,
        )


def _connector_provider(connector: BrokerConnector) -> str:
    name = connector.__class__.__name__.lower()
    if "flex" in name:
        return "ibkr-flex"
    if "clientportal" in name or "client_portal" in name:
        return "ibkr-client-portal"
    return name
