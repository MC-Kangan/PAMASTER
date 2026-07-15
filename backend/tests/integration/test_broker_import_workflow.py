from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pa_investing.brokers.interfaces import BrokerConnector
from pa_investing.db.base import Base
from pa_investing.db.models import InstrumentRecord, PositionRecord
from pa_investing.db.repositories import AccountRepository, PositionRepository
from pa_investing.domain.enums import AssetClass, CostBasisStatus
from pa_investing.domain.models import Account, Instrument, Position
from pa_investing.workflows.broker_import import BrokerImportWorkflow


class StubBrokerConnector(BrokerConnector):
    def __init__(self, accounts: list[Account], positions: list[Position]) -> None:
        self._accounts = accounts
        self._positions = positions

    def list_accounts(self) -> list[Account]:
        return self._accounts

    def fetch_positions(self) -> list[Position]:
        return self._positions


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
            commit=session.commit,
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

    assert result.accounts_imported == 1
    assert result.positions_imported == 2
    assert result.positions_closed == 1
    assert result.cost_basis_available == 1
    assert result.cost_basis_missing == 1
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
    assert position_by_key[("U1234567", "ASML")].quantity == Decimal("0")
    assert position_by_key[("manual-pa", "AAPL")].quantity == Decimal("2")


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
