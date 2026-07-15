from decimal import Decimal
from pathlib import Path

from pytest import CaptureFixture
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pa_investing.core.config import Settings
from pa_investing.db.base import Base
from pa_investing.db.models import AccountRecord, InstrumentRecord, PositionRecord
from pa_investing.db.repositories import PositionRepository
from pa_investing.db.session import DatabaseSessionFactory
from pa_investing.scripts.seed_demo_portfolio import main
from pa_investing.seeds.demo_portfolio import seed_demo_portfolio


def test_seed_demo_portfolio_loads_account_and_positions() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        result = seed_demo_portfolio(
            session=session,
            csv_path=Path("tests/fixtures/positions_demo_portfolio.csv"),
        )
        session.commit()

        account_ids = session.scalars(select(AccountRecord.account_id)).all()
        positions = session.execute(
            select(PositionRecord, InstrumentRecord).join(
                InstrumentRecord,
                PositionRecord.instrument_id == InstrumentRecord.instrument_id,
            )
        ).all()

    assert result.account_id == "pa-demo"
    assert result.positions_loaded == 5
    assert account_ids == ["pa-demo"]
    assert len(positions) == 5
    assert {instrument.symbol for _, instrument in positions} == {
        "SPGI",
        "ASML",
        "SAP",
        "SGLN",
        "SMH",
    }


def test_seed_demo_portfolio_is_idempotent_on_rerun() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        first_result = seed_demo_portfolio(
            session=session,
            csv_path=Path("tests/fixtures/positions_demo_portfolio.csv"),
        )
        second_result = seed_demo_portfolio(
            session=session,
            csv_path=Path("tests/fixtures/positions_demo_portfolio.csv"),
        )
        session.commit()

        account_count = len(session.scalars(select(AccountRecord.account_id)).all())
        position_count = len(session.scalars(select(PositionRecord.id)).all())

    assert first_result.positions_loaded == 5
    assert second_result.positions_loaded == 5
    assert account_count == 1
    assert position_count == 5


def test_seed_demo_portfolio_overwrites_existing_position_values(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    updated_csv = tmp_path / "positions_demo_portfolio.csv"
    updated_csv.write_text(
        "account_id,symbol,name,asset_class,currency,quantity,average_cost,latest_price\n"
        "pa-demo,SPGI,S&P Global Inc.,equity,USD,14,460,470\n"
        "pa-demo,ASML,ASML Holding N.V.,equity,EUR,6,890,905\n"
        "pa-demo,SAP,SAP SE,equity,EUR,15,235,242\n"
        "pa-demo,SGLN,iShares Physical Gold ETC,etf,GBP,120,21.5,22.1\n"
        "pa-demo,SMH,VanEck Semiconductor UCITS ETF,etf,USD,20,248,252\n"
    )

    with session_factory() as session:
        seed_demo_portfolio(
            session=session,
            csv_path=Path("tests/fixtures/positions_demo_portfolio.csv"),
        )
        seed_demo_portfolio(session=session, csv_path=updated_csv)
        session.commit()

        positions = PositionRepository(session).list_open_positions()

    spgi_position = next(
        position for position in positions if position.instrument.symbol == "SPGI"
    )
    assert spgi_position.quantity == Decimal("14.00000000")
    assert spgi_position.average_cost == Decimal("460.00000000")


def test_seed_demo_portfolio_command_returns_summary(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    database_path = tmp_path / "demo.sqlite"
    settings = Settings(
        database_url=f"sqlite+pysqlite:///{database_path}",
    )
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)

    result = main(
        settings=settings,
        csv_path=Path("tests/fixtures/positions_demo_portfolio.csv"),
        session_factory=DatabaseSessionFactory(settings),
    )

    captured = capsys.readouterr()

    assert result.account_id == "pa-demo"
    assert result.positions_loaded == 5
    assert "pa-demo" in captured.out
    assert "5 positions" in captured.out
