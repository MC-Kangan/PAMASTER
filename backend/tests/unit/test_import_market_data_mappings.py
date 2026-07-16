from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pa_investing.db.base import Base
from pa_investing.db.repositories import MarketDataMappingRepository, PositionRepository
from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Instrument, Position
from pa_investing.scripts.import_market_data_mappings import (
    import_market_data_mappings,
)


def test_import_market_data_mappings_persists_listing_and_multiplier(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        PositionRepository(session).upsert(
            Position(
                account_id="U1",
                instrument=Instrument(
                    instrument_id="sgln-id",
                    symbol="SGLN",
                    name="iShares Physical Gold ETC",
                    asset_class=AssetClass.ETF,
                    currency="GBP",
                    venue="LSEETF",
                ),
                quantity=Decimal("10"),
                average_cost=Decimal("20"),
                latest_price=Decimal("21"),
            )
        )
        session.commit()

    csv_path = tmp_path / "mappings.csv"
    csv_path.write_text(
        "instrument_id,provider,provider_symbol,provider_exchange,"
        "expected_currency,price_multiplier,enabled\n"
        "sgln-id,twelve_data,SGLN,LSE,GBX,0.01,true\n"
    )

    count = import_market_data_mappings(csv_path, session_factory=session_factory)

    with session_factory() as session:
        mappings = MarketDataMappingRepository(session).list_for_instruments(
            {"sgln-id"}, "twelve_data"
        )
    assert count == 1
    assert mappings["sgln-id"].provider_symbol == "SGLN"
    assert mappings["sgln-id"].provider_exchange == "LSE"
    assert mappings["sgln-id"].expected_currency == "GBX"
    assert mappings["sgln-id"].price_multiplier == Decimal("0.01")


def test_import_market_data_mappings_rejects_invalid_boolean(tmp_path) -> None:
    csv_path = tmp_path / "mappings.csv"
    csv_path.write_text(
        "instrument_id,provider,provider_symbol,expected_currency,enabled\n"
        "sgln-id,twelve_data,SGLN,GBP,perhaps\n"
    )

    with pytest.raises(ValueError, match="CSV row 2"):
        import_market_data_mappings(csv_path, session_factory=lambda: None)
