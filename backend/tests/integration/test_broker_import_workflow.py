from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pa_investing.brokers.interfaces import BrokerConnector
from pa_investing.db.base import Base
from pa_investing.db.models import (
    BrokerReconciliationRecord,
    InstrumentRecord,
    MarketDataMappingRecord,
    PositionRecord,
    PriceRecord,
    ProviderRunRecord,
    TransactionRecord,
)
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
    AssetClass,
    CostBasisStatus,
    ProviderRunStatus,
    QuoteQuality,
    ReconciliationStatus,
    TransactionType,
)
from pa_investing.domain.models import (
    Account,
    BrokerReconciliation,
    Instrument,
    Position,
    Transaction,
)
from pa_investing.workflows.broker_import import BrokerImportWorkflow


class StubBrokerConnector(BrokerConnector):
    def __init__(
        self,
        accounts: list[Account],
        positions: list[Position],
        transactions: list[Transaction] | None = None,
        reconciliations: list[BrokerReconciliation] | None = None,
    ) -> None:
        self._accounts = accounts
        self._positions = positions
        self._transactions = transactions or []
        self._reconciliations = reconciliations or []

    def list_accounts(self) -> list[Account]:
        return self._accounts

    def fetch_positions(self) -> list[Position]:
        return self._positions

    def fetch_transactions(self) -> list[Transaction]:
        return self._transactions

    def fetch_reconciliations(self) -> list[BrokerReconciliation]:
        return self._reconciliations


def test_broker_import_workflow_overwrites_matching_account_positions() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        account_repository = AccountRepository(session)
        position_repository = PositionRepository(session)
        account_repository.upsert(
            Account(account_id="U1234567", name="Old IBKR", source="ibkr")
        )
        account_repository.upsert(
            Account(account_id="manual-pa", name="Manual", source="csv")
        )
        position_repository.upsert(
            Position(
                account_id="U1234567",
                instrument=Instrument(
                    symbol="SPGI",
                    name="S&P Global",
                    asset_class=AssetClass.EQUITY,
                    currency="USD",
                ),
                quantity=Decimal("5"),
                average_cost=Decimal("400"),
                latest_price=Decimal("500"),
            )
        )
        position_repository.set_manual_average_cost(
            "U1234567",
            "SPGI",
            Decimal("0"),
        )
        position_repository.upsert(
            Position(
                account_id="U1234567",
                instrument=Instrument(
                    symbol="ASML",
                    name="ASML Holding",
                    asset_class=AssetClass.EQUITY,
                    currency="EUR",
                ),
                quantity=Decimal("3"),
                average_cost=Decimal("900"),
                latest_price=Decimal("950"),
            )
        )
        position_repository.upsert(
            Position(
                account_id="manual-pa",
                instrument=Instrument(
                    symbol="AAPL",
                    name="Apple Inc.",
                    asset_class=AssetClass.EQUITY,
                    currency="USD",
                ),
                quantity=Decimal("2"),
                average_cost=Decimal("150"),
                latest_price=Decimal("200"),
            )
        )
        session.commit()

        workflow = BrokerImportWorkflow(
            connector=StubBrokerConnector(
                accounts=[
                    Account(account_id="U1234567", name="Primary IBKR", source="ibkr"),
                ],
                positions=[
                    Position(
                        account_id="U1234567",
                        instrument=Instrument(
                            symbol="SPGI",
                            name="S&P Global",
                            asset_class=AssetClass.EQUITY,
                            currency="USD",
                        ),
                        quantity=Decimal("10"),
                        average_cost=Decimal("420"),
                        latest_price=Decimal("510"),
                        cost_basis_status=CostBasisStatus.BROKER,
                    ),
                    Position(
                        account_id="U1234567",
                        instrument=Instrument(
                            symbol="SGLN",
                            name="iShares Physical Gold ETC",
                            asset_class=AssetClass.ETF,
                            currency="GBP",
                        ),
                        quantity=Decimal("50"),
                        average_cost=Decimal("41"),
                        latest_price=Decimal("45"),
                        cost_basis_status=CostBasisStatus.UNAVAILABLE,
                    ),
                ],
            ),
            account_repository=account_repository,
            position_repository=position_repository,
            price_repository=PriceRepository(session),
            market_data_mapping_repository=MarketDataMappingRepository(session),
            commit=session.commit,
            clock=lambda: datetime(2026, 7, 15, 7, tzinfo=UTC),
        )

        result = workflow.run()
        session.commit()

        stored_positions = session.execute(
            select(PositionRecord, InstrumentRecord)
            .join(
                InstrumentRecord,
                PositionRecord.instrument_id == InstrumentRecord.instrument_id,
            )
            .order_by(PositionRecord.account_id, InstrumentRecord.symbol)
        ).all()
        stored_prices = session.scalars(select(PriceRecord)).all()
        stored_mappings = session.scalars(select(MarketDataMappingRecord)).all()

    assert result.accounts_imported == 1
    assert result.positions_imported == 2
    assert result.positions_closed == 1
    assert result.cost_basis_available == 1
    assert result.cost_basis_missing == 1
    assert result.market_data_mappings_imported == 1
    assert result.missing_cost_basis_positions == [
        {
            "account_id": "U1234567",
            "symbol": "SGLN",
            "reason": "cost basis unavailable",
        }
    ]

    position_by_key = {
        (position.account_id, instrument.symbol): position
        for position, instrument in stored_positions
    }
    assert position_by_key[("U1234567", "SPGI")].quantity == Decimal("10")
    assert position_by_key[("U1234567", "SPGI")].average_cost == Decimal("0")
    assert position_by_key[("U1234567", "SPGI")].manual_average_cost == Decimal("0")
    assert position_by_key[("U1234567", "SPGI")].broker_average_cost == Decimal("420")
    assert position_by_key[("U1234567", "SPGI")].cost_basis_status == "manual"
    assert position_by_key[("U1234567", "SGLN")].quantity == Decimal("50")
    assert position_by_key[("U1234567", "SGLN")].latest_price_provider == "ibkr"
    assert position_by_key[("U1234567", "SGLN")].latest_price_quality == "delayed"
    assert position_by_key[("U1234567", "ASML")].quantity == Decimal("0")
    assert position_by_key[("manual-pa", "AAPL")].quantity == Decimal("2")
    assert len(stored_prices) == 2
    assert {row.quality for row in stored_prices} == {QuoteQuality.DELAYED.value}
    assert [
        (
            row.provider,
            row.provider_symbol,
            row.expected_currency,
            row.price_multiplier,
        )
        for row in stored_mappings
    ] == [("yahoo", "SPGI", "USD", Decimal("1"))]


def test_broker_import_workflow_fails_when_no_supported_accounts_or_positions_are_returned(
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        workflow = BrokerImportWorkflow(
            connector=StubBrokerConnector(accounts=[], positions=[]),
            account_repository=AccountRepository(session),
            position_repository=PositionRepository(session),
            commit=session.commit,
        )

        try:
            workflow.run()
        except RuntimeError as error:
            assert str(error) == "IBKR import returned no supported accounts or positions"
        else:
            raise AssertionError("Expected broker import to fail")


def test_broker_import_persists_ledger_reconciliation_and_provider_health() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    observed_at = datetime(2026, 7, 10, tzinfo=UTC)
    instrument = Instrument(
        symbol="SPGI",
        name="S&P Global",
        asset_class=AssetClass.EQUITY,
        currency="USD",
    )

    with session_factory() as session:
        workflow = BrokerImportWorkflow(
            connector=StubBrokerConnector(
                accounts=[
                    Account(
                        account_id="U1",
                        name="IBKR",
                        source="ibkr-flex",
                        base_currency="GBP",
                    )
                ],
                positions=[
                    Position(
                        account_id="U1",
                        instrument=instrument,
                        quantity=Decimal("2"),
                        average_cost=Decimal("430"),
                        latest_price=Decimal("450"),
                        cost_basis_status=CostBasisStatus.BROKER,
                    )
                ],
                transactions=[
                    Transaction(
                        transaction_id="ibkr-flex:U1:tx-1",
                        account_id="U1",
                        provider="ibkr-flex",
                        external_id="tx-1",
                        occurred_at=observed_at,
                        transaction_type=TransactionType.BUY,
                        currency="USD",
                        symbol="SPGI",
                        instrument=instrument,
                        quantity=Decimal("2"),
                        unit_price=Decimal("430"),
                        gross_amount=Decimal("-860"),
                        fees=Decimal("-1"),
                        net_cash=Decimal("-861"),
                    )
                ],
                reconciliations=[
                    BrokerReconciliation(
                        reconciliation_id="ibkr-flex:U1:20260710",
                        account_id="U1",
                        provider="ibkr-flex",
                        observed_at=observed_at,
                        currency="GBP",
                        broker_nav=Decimal("1000"),
                        calculated_nav=Decimal("1000"),
                        nav_difference=Decimal("0"),
                        broker_cash=Decimal("100"),
                        calculated_cash=Decimal("100"),
                        cash_difference=Decimal("0"),
                        status=ReconciliationStatus.MATCHED,
                    )
                ],
            ),
            account_repository=AccountRepository(session),
            position_repository=PositionRepository(session),
            transaction_repository=TransactionRepository(session),
            reconciliation_repository=BrokerReconciliationRepository(session),
            provider_run_repository=ProviderRunRepository(session),
            commit=session.commit,
            rollback=session.rollback,
            clock=lambda: observed_at,
        )

        first = workflow.run()
        second = workflow.run()

        transactions = session.scalars(select(TransactionRecord)).all()
        reconciliations = session.scalars(
            select(BrokerReconciliationRecord)
        ).all()
        provider_runs = session.scalars(select(ProviderRunRecord)).all()

    assert first.transactions_imported == 1
    assert first.reconciliations_imported == 1
    assert second.transactions_imported == 1
    assert len(transactions) == 1
    assert len(reconciliations) == 1
    assert len(provider_runs) == 2
    assert {run.status for run in provider_runs} == {
        ProviderRunStatus.SUCCESS.value
    }


def test_broker_import_persists_failed_provider_run_after_rollback() -> None:
    class FailingConnector(StubBrokerConnector):
        def fetch_positions(self) -> list[Position]:
            raise RuntimeError("broker unavailable")

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        workflow = BrokerImportWorkflow(
            connector=FailingConnector(
                accounts=[
                    Account(
                        account_id="U1",
                        name="IBKR",
                        source="ibkr-flex",
                    )
                ],
                positions=[],
            ),
            account_repository=AccountRepository(session),
            position_repository=PositionRepository(session),
            provider_run_repository=ProviderRunRepository(session),
            commit=session.commit,
            rollback=session.rollback,
        )

        with pytest.raises(RuntimeError, match="broker unavailable"):
            workflow.run()

        runs = ProviderRunRepository(session).latest_by_provider()

    assert len(runs) == 1
    assert runs[0].status == ProviderRunStatus.FAILED
    assert runs[0].error_message == "broker unavailable"
