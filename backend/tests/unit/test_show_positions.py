from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pa_investing.db.base import Base
from pa_investing.db.repositories import AccountRepository, PositionRepository
from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Account, Instrument, Position
from pa_investing.scripts.show_positions import show_positions


def test_show_positions_prints_accounts_and_open_positions(capsys) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        AccountRepository(session).upsert(
            Account(
                account_id="U1234567",
                name="Primary IBKR",
                source="ibkr-flex",
                base_currency="USD",
            )
        )
        PositionRepository(session).upsert(
            Position(
                account_id="U1234567",
                instrument=Instrument(
                    symbol="SPGI",
                    name="S&P Global Inc.",
                    asset_class=AssetClass.EQUITY,
                    currency="USD",
                ),
                quantity=Decimal("10"),
                average_cost=Decimal("420.5"),
                latest_price=Decimal("510.25"),
            )
        )
        PositionRepository(session).upsert(
            Position(
                account_id="U1234567",
                instrument=Instrument(
                    symbol="CLOSED",
                    name="Closed Position",
                    asset_class=AssetClass.EQUITY,
                    currency="USD",
                ),
                quantity=Decimal("0"),
                average_cost=Decimal("1"),
                latest_price=Decimal("2"),
            )
        )
        session.commit()

        show_positions(session_factory=session_factory)

    captured = capsys.readouterr()

    assert "Open positions: 1" in captured.out
    assert "U1234567" in captured.out
    assert "SPGI" in captured.out
    assert "S&P Global Inc." in captured.out
    assert "CLOSED" not in captured.out
