from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pa_investing.db.base import Base
from pa_investing.db.repositories import (
    AccountRepository,
    AppSettingRepository,
    FxRateRepository,
    MarketDataMappingRepository,
    PositionRepository,
    PriceRepository,
)
from pa_investing.domain.enums import AssetClass, CostBasisStatus
from pa_investing.domain.models import (
    Account,
    FxRatePoint,
    Instrument,
    InstrumentIdentifier,
    MarketDataMapping,
    Position,
    PricePoint,
)


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
        closed_instrument = Instrument(
            symbol="MSFT",
            name="Microsoft Corp.",
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
        position_repo.upsert(
            Position(
                account_id="acct-1",
                instrument=closed_instrument,
                quantity=Decimal("0"),
                average_cost=Decimal("300"),
                latest_price=Decimal("0"),
            )
        )
        latest_timestamp = datetime(2026, 7, 8, 12, 30, tzinfo=UTC)
        price_repo.upsert(
            PricePoint(
                instrument=instrument,
                price=Decimal("175"),
                observed_at=latest_timestamp,
                provider="manual",
            )
        )
        session.commit()

        positions = position_repo.list_open_positions()
        prices = price_repo.latest_prices()

    assert len(positions) == 1
    assert all(position.quantity != 0 for position in positions)
    assert positions[0].instrument.symbol == "AAPL"
    assert prices["AAPL"].price == Decimal("175.000000")
    assert prices["AAPL"].observed_at == latest_timestamp


def test_account_and_app_setting_repositories_round_trip() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        accounts = AccountRepository(session)
        settings = AppSettingRepository(session)
        accounts.upsert(
            Account(
                account_id="U123",
                name="IBKR",
                source="ibkr_flex",
                base_currency="GBP",
            )
        )
        settings.set("portfolio_base_currency", "GBP")
        settings.set("portfolio_base_currency", "USD")
        session.commit()

        stored_accounts = accounts.list_all()
        stored_base_currency = settings.get("portfolio_base_currency")

    assert stored_accounts == [
        Account(
            account_id="U123",
            name="IBKR",
            source="ibkr_flex",
            base_currency="GBP",
        )
    ]
    assert stored_base_currency == "USD"


def test_position_cost_basis_status_round_trip() -> None:
    """Upsert a position with trade_reconstructed status and read it back."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        position_repo = PositionRepository(session)
        instrument = Instrument(
            symbol="SPGI",
            name="S&P Global Inc.",
            asset_class=AssetClass.EQUITY,
            currency="USD",
        )
        position_repo.upsert(
            Position(
                account_id="U1234567",
                instrument=instrument,
                quantity=Decimal("10"),
                average_cost=Decimal("420.5"),
                latest_price=Decimal("510.25"),
                cost_basis_status=CostBasisStatus.TRADE_RECONSTRUCTED,
            )
        )
        session.commit()

        positions = position_repo.list_open_positions()

    assert len(positions) == 1
    assert positions[0].cost_basis_status == CostBasisStatus.TRADE_RECONSTRUCTED


def test_manual_cost_override_survives_broker_reimport_and_can_be_cleared() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    instrument = Instrument(
        symbol="FREE",
        name="Free Signup Share",
        asset_class=AssetClass.EQUITY,
        currency="USD",
    )

    with session_factory() as session:
        repository = PositionRepository(session)
        repository.upsert_broker_position(
            Position(
                account_id="U1234567",
                instrument=instrument,
                quantity=Decimal("1"),
                average_cost=Decimal("0"),
                latest_price=Decimal("140"),
                cost_basis_status=CostBasisStatus.UNAVAILABLE,
            )
        )
        repository.set_manual_average_cost("U1234567", "FREE", Decimal("0"))

        repository.upsert_broker_position(
            Position(
                account_id="U1234567",
                instrument=instrument,
                quantity=Decimal("1"),
                average_cost=Decimal("125"),
                latest_price=Decimal("145"),
                cost_basis_status=CostBasisStatus.BROKER,
            )
        )
        overridden = repository.list_open_positions()[0]

        assert overridden.manual_average_cost == Decimal("0")
        assert overridden.broker_average_cost == Decimal("125")
        assert overridden.average_cost == Decimal("0")
        assert overridden.cost_basis_status == CostBasisStatus.MANUAL

        repository.set_manual_average_cost("U1234567", "FREE", None)
        cleared = repository.list_open_positions()[0]

    assert cleared.manual_average_cost is None
    assert cleared.average_cost == Decimal("125")
    assert cleared.cost_basis_status == CostBasisStatus.BROKER


def test_internal_ids_allow_same_symbol_on_different_venues() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        accounts = AccountRepository(session)
        positions = PositionRepository(session)
        accounts.upsert(Account(account_id="U123", name="IBKR", source="ibkr-flex"))
        for venue, conid in (("NASDAQ", "1001"), ("LSEETF", "2002")):
            positions.upsert_broker_position(
                Position(
                    account_id="U123",
                    instrument=Instrument(
                        symbol="SMH",
                        name=f"SMH {venue}",
                        asset_class=AssetClass.ETF,
                        currency="USD",
                        venue=venue,
                        identifiers=(
                            InstrumentIdentifier(
                                provider="ibkr",
                                identifier_type="conid",
                                value=conid,
                            ),
                        ),
                    ),
                    quantity=Decimal("1"),
                    average_cost=Decimal("100"),
                    cost_basis_status=CostBasisStatus.BROKER,
                )
            )
        session.commit()

        stored = positions.list_open_positions()
        instrument_ids = {position.instrument.instrument_id for position in stored}

        price_repository = PriceRepository(session)
        for index, position in enumerate(stored, start=1):
            price_repository.upsert(
                PricePoint(
                    instrument=position.instrument,
                    price=Decimal(100 + index),
                    observed_at=datetime(2026, 7, 15, 12, tzinfo=UTC),
                    provider="manual",
                )
            )
        prices_by_id = price_repository.latest_prices_by_instrument_id()

        assert len(stored) == 2
        assert len(instrument_ids) == 2
        assert set(prices_by_id) == instrument_ids
        with pytest.raises(ValueError, match="multiple instruments use symbol"):
            price_repository.latest_prices()
        with pytest.raises(ValueError, match="symbol is ambiguous"):
            positions.set_manual_average_cost("U123", "SMH", Decimal("90"))


def test_provider_identifier_resolves_existing_instrument_after_symbol_change() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    identifier = InstrumentIdentifier(
        provider="ibkr",
        identifier_type="conid",
        value="12345",
    )

    with session_factory() as session:
        accounts = AccountRepository(session)
        positions = PositionRepository(session)
        accounts.upsert(Account(account_id="U123", name="IBKR", source="ibkr-flex"))
        first = positions.upsert_broker_position(
            Position(
                account_id="U123",
                instrument=Instrument(
                    symbol="OLD",
                    name="Old symbol",
                    asset_class=AssetClass.EQUITY,
                    venue="NYSE",
                    identifiers=(identifier,),
                ),
                quantity=Decimal("1"),
                average_cost=Decimal("10"),
                cost_basis_status=CostBasisStatus.BROKER,
            )
        )
        updated = positions.upsert_broker_position(
            Position(
                account_id="U123",
                instrument=Instrument(
                    symbol="NEW",
                    name="New symbol",
                    asset_class=AssetClass.EQUITY,
                    venue="NYSE",
                    identifiers=(identifier,),
                ),
                quantity=Decimal("2"),
                average_cost=Decimal("11"),
                cost_basis_status=CostBasisStatus.BROKER,
            )
        )
        session.commit()

        stored = positions.list_open_positions()

    assert first.instrument.instrument_id == updated.instrument.instrument_id
    assert len(stored) == 1
    assert stored[0].instrument.symbol == "NEW"
    assert stored[0].quantity == 2


def test_market_data_mapping_and_fx_rate_repositories_round_trip() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    observed_at = datetime(2026, 7, 15, 12, tzinfo=UTC)

    with session_factory() as session:
        accounts = AccountRepository(session)
        positions = PositionRepository(session)
        accounts.upsert(Account(account_id="U1", name="IBKR", source="ibkr-flex"))
        stored_position = positions.upsert_broker_position(
            Position(
                account_id="U1",
                instrument=Instrument(
                    symbol="SGLN",
                    name="Gold ETC",
                    asset_class=AssetClass.ETF,
                    currency="GBP",
                    venue="LSEETF",
                ),
                quantity=Decimal("10"),
                average_cost=Decimal("50"),
                cost_basis_status=CostBasisStatus.BROKER,
            )
        )
        instrument_id = stored_position.instrument.instrument_id
        assert instrument_id is not None
        mapping_repository = MarketDataMappingRepository(session)
        mapping_repository.upsert(
            MarketDataMapping(
                instrument_id=instrument_id,
                provider="twelve_data",
                provider_symbol="SGLN",
                provider_exchange="LSE",
                expected_currency="GBX",
                price_multiplier=Decimal("0.01"),
            )
        )
        fx_repository = FxRateRepository(session)
        fx_repository.upsert(
            FxRatePoint(
                base_currency="GBP",
                quote_currency="USD",
                rate=Decimal("1.31"),
                observed_at=observed_at,
                provider="twelve_data",
            )
        )
        session.commit()

        mappings = mapping_repository.list_for_instruments(
            {instrument_id},
            "twelve_data",
        )
        rate = fx_repository.latest("GBP", "USD")

    assert mappings[instrument_id].provider_exchange == "LSE"
    assert mappings[instrument_id].price_multiplier == Decimal("0.010000000000")
    assert rate is not None
    assert rate.rate == Decimal("1.310000000000")
