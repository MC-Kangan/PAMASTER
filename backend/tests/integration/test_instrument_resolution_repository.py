from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from pa_investing.db.base import Base
from pa_investing.db.models import (
    InstrumentIdentifierRecord,
    InstrumentRecord,
    MarketDataMappingRecord,
)
from pa_investing.instruments.resolution import InstrumentResolutionService


def test_portfolio_resolution_uses_only_explicit_provider_mappings() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        session.add(
            InstrumentRecord(
                instrument_id="sgln-id",
                symbol="SGLN",
                name="iShares Physical Gold ETC",
                asset_class="etf",
                currency="GBP",
                venue="LSEETF",
            )
        )
        session.add(
            InstrumentIdentifierRecord(
                instrument_id="sgln-id",
                provider="ibkr",
                identifier_type="conid",
                value="123456",
            )
        )
        session.add_all(
            [
                MarketDataMappingRecord(
                    instrument_id="sgln-id",
                    provider="yahoo",
                    provider_symbol="SGLN.L",
                    provider_exchange=None,
                    expected_currency="GBP",
                    price_multiplier=Decimal("1"),
                    enabled=True,
                ),
                MarketDataMappingRecord(
                    instrument_id="sgln-id",
                    provider="twelve_data",
                    provider_symbol="SGLN",
                    provider_exchange="LSE",
                    expected_currency="GBX",
                    price_multiplier=Decimal("0.01"),
                    enabled=True,
                ),
                MarketDataMappingRecord(
                    instrument_id="sgln-id",
                    provider="unused",
                    provider_symbol="SHOULD-NOT-APPEAR",
                    provider_exchange=None,
                    expected_currency="GBP",
                    price_multiplier=Decimal("1"),
                    enabled=False,
                ),
            ]
        )
        session.commit()

        resolved = InstrumentResolutionService(session=session).for_portfolio(
            "sgln-id"
        )

    assert resolved.instrument_id == "sgln-id"
    assert resolved.display_symbol == "SGLN"
    assert resolved.currency == "GBP"
    assert resolved.exchange == "LSEETF"
    assert resolved.provider_symbols == {
        "yahoo": "SGLN.L",
        "twelve_data": "SGLN",
    }
    assert resolved.provider_exchanges == {"twelve_data": "LSE"}
    assert resolved.provider_currencies == {
        "yahoo": "GBP",
        "twelve_data": "GBX",
    }
    assert resolved.provider_price_multipliers == {
        "yahoo": Decimal("1"),
        "twelve_data": Decimal("0.01"),
    }
    assert resolved.provider_ids == {"ibkr_tws": "conid:123456"}


def test_research_search_does_not_create_permanent_instruments() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        before = session.scalar(select(func.count()).select_from(InstrumentRecord))
        result = InstrumentResolutionService(session=session, searchers=[]).search(
            "NEWIDEA"
        )
        after = session.scalar(select(func.count()).select_from(InstrumentRecord))

    assert result.candidates == []
    assert before == after == 0
