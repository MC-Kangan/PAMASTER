from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pa_investing.db.base import Base
from pa_investing.db.repositories import (
    AccountRepository,
    PositionRepository,
    PriceRepository,
)
from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Account, Instrument, Position, PricePoint


def test_repositories_round_trip_account_position_and_price() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        account_repo = AccountRepository(session)
        position_repo = PositionRepository(session)
        price_repo = PriceRepository(session)

        account_repo.upsert(Account(account_id="acct-1", name="Manual Account", source="csv"))
        instrument = Instrument(
            symbol="AAPL",
            name="Apple Inc.",
            asset_class=AssetClass.EQUITY,
        )
        position_repo.upsert(
            Position(
                account_id="acct-1",
                instrument=instrument,
                quantity=Decimal("10"),
                average_cost=Decimal("150"),
                latest_price=Decimal("175"),
            )
        )
        price_repo.upsert(
            PricePoint(
                instrument=instrument,
                price=Decimal("175"),
                observed_at=datetime(2026, 7, 8, tzinfo=UTC),
                provider="manual",
            )
        )
        session.commit()

        positions = position_repo.list_open_positions()
        prices = price_repo.latest_prices()

    assert len(positions) == 1
    assert positions[0].instrument.symbol == "AAPL"
    assert prices["AAPL"].price == Decimal("175.000000")
