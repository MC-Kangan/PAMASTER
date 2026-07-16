from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from pa_investing.db.base import Base
from pa_investing.db.models import (
    PortfolioSnapshotRecord,
    PositionRecord,
    PriceRecord,
    SignalRecord,
)
from pa_investing.db.repositories import (
    AccountRepository,
    AppSettingRepository,
    AuditEventRepository,
    FxRateRepository,
    MarketDataMappingRepository,
    PortfolioSnapshotRepository,
    PositionRepository,
    PriceRepository,
    SignalRepository,
)
from pa_investing.domain.enums import AssetClass, CostBasisStatus
from pa_investing.domain.models import (
    Account,
    FxRatePoint,
    Instrument,
    MarketDataMapping,
    Position,
    PricePoint,
)
from pa_investing.market_data.interfaces import (
    FxRateRequest,
    MarketDataProvider,
    QuoteRequest,
)
from pa_investing.notion.client import FakeNotionClient, NotionReadError
from pa_investing.notion.schemas import (
    NotionDatabaseRow,
    NotionPagePayload,
    NotionPropertyValue,
)
from pa_investing.notion.sync import PORTFOLIO_BASE_CURRENCY_KEY, NotionSync
from pa_investing.workflows.daily_review import DailyReviewPersistence, DailyReviewWorkflow
from pa_investing.workflows.refresh_and_sync import RefreshAndSyncWorkflow


class FakeMarketDataProvider(MarketDataProvider):
    def __init__(self, prices: dict[str, PricePoint]) -> None:
        self.prices = prices

    def get_latest_prices(self, symbols: set[str]) -> dict[str, PricePoint]:
        return {symbol: self.prices[symbol] for symbol in symbols}


class FakeMappedMarketDataProvider(FakeMarketDataProvider):
    provider_name = "twelve_data"

    def __init__(
        self,
        quotes: dict[str, PricePoint],
        rates: dict[tuple[str, str], FxRatePoint],
    ) -> None:
        super().__init__({})
        self.quotes = quotes
        self.rates = rates

    def get_quotes(self, requests: list[QuoteRequest]) -> dict[str, PricePoint]:
        requested_ids = {
            request.instrument.instrument_id for request in requests
        }
        return {
            instrument_id: point
            for instrument_id, point in self.quotes.items()
            if instrument_id in requested_ids
        }

    def get_fx_rates(
        self,
        requests: set[FxRateRequest],
    ) -> dict[tuple[str, str], FxRatePoint]:
        requested = {
            (request.base_currency, request.quote_currency)
            for request in requests
        }
        return {key: point for key, point in self.rates.items() if key in requested}


class VisibilityCheckingNotionClient(FakeNotionClient):
    def __init__(self, session_factory: sessionmaker) -> None:
        super().__init__()
        self.session_factory = session_factory
        self.checked_visibility = False

    def upsert_page(
        self,
        database_name: str,
        external_id: str,
        payload: NotionPagePayload,
    ) -> str:
        if not self.checked_visibility:
            with self.session_factory() as fresh_session:
                assert fresh_session.scalar(select(func.count()).select_from(PriceRecord)) == 1
                assert (
                    fresh_session.scalar(select(func.count()).select_from(PositionRecord))
                    == 1
                )
                assert (
                    fresh_session.scalar(
                        select(func.count()).select_from(PortfolioSnapshotRecord)
                    )
                    == 1
                )
                assert fresh_session.scalar(select(func.count()).select_from(SignalRecord)) == 1
            self.checked_visibility = True
        return super().upsert_page(database_name, external_id, payload)


def test_refresh_and_sync_workflow_updates_prices_and_syncs_notion() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    notion_client = FakeNotionClient()
    observed_at = datetime(2026, 7, 9, 14, 30, tzinfo=UTC)
    instrument = Instrument(
        symbol="AAPL",
        name="Apple Inc.",
        asset_class=AssetClass.EQUITY,
    )

    with session_factory() as session:
        account_repository = AccountRepository(session)
        position_repository = PositionRepository(session)
        price_repository = PriceRepository(session)

        account_repository.upsert(
            Account(account_id="acct-1", name="Manual Account", source="csv")
        )
        position_repository.upsert(
            Position(
                account_id="acct-1",
                instrument=instrument,
                quantity=Decimal("10"),
                average_cost=Decimal("150"),
                latest_price=Decimal("150"),
            )
        )
        session.commit()

        workflow = RefreshAndSyncWorkflow(
            position_repository=position_repository,
            price_repository=price_repository,
            market_data_provider=FakeMarketDataProvider(
                prices={
                    "AAPL": PricePoint(
                        instrument=instrument,
                        price=Decimal("175"),
                        observed_at=observed_at,
                        provider="alpha_vantage",
                    )
                }
            ),
            daily_review_workflow=DailyReviewWorkflow(
                notion_sync=NotionSync(client=notion_client),
                persistence=DailyReviewPersistence(
                    audit_event_repository=AuditEventRepository(session),
                    snapshot_repository=PortfolioSnapshotRepository(session),
                    signal_repository=SignalRepository(session),
                ),
            ),
            notion_sync=NotionSync(client=notion_client),
            commit=session.commit,
        )

        result = workflow.run(stop_prices={"AAPL": Decimal("180")})
        second_result = workflow.run(stop_prices={"AAPL": Decimal("180")})
        latest_prices = price_repository.latest_prices()
        stored_positions = position_repository.list_open_positions()
        stored_snapshot_ids = session.scalars(
            select(PortfolioSnapshotRecord.snapshot_id)
        ).all()
        stored_signal_ids = session.scalars(select(SignalRecord.signal_id)).all()

    assert result.snapshot.nav == Decimal("1750")
    assert second_result.snapshot.nav == Decimal("1750")
    assert len(result.signals) == 1
    assert latest_prices["AAPL"].provider == "alpha_vantage"
    assert latest_prices["AAPL"].price == Decimal("175.000000")
    assert stored_positions[0].latest_price == Decimal("175.000000")
    assert set(stored_snapshot_ids) == {
        result.snapshot.snapshot_id,
        second_result.snapshot.snapshot_id,
    }
    assert set(stored_signal_ids) == {
        result.signals[0].signal_id,
        second_result.signals[0].signal_id,
    }
    assert next(iter(notion_client.pages["Signals"])) == result.signals[0].signal_id
    daily_review_external_id = (
        f"daily-review:{result.snapshot.observed_at.date().isoformat()}:default"
    )
    assert list(notion_client.pages["Daily Review"]) == [daily_review_external_id]
    assert (
        notion_client.pages["Daily Review"][daily_review_external_id].properties["NAV"]
        == NotionPropertyValue.number(Decimal("1750.00000000"))
    )


def test_refresh_and_sync_commits_rows_before_notion_sync(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'visibility.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    notion_client = VisibilityCheckingNotionClient(session_factory)
    instrument = Instrument(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.EQUITY)

    with session_factory() as session:
        AccountRepository(session).upsert(
            Account(account_id="acct-1", name="Manual Account", source="csv")
        )
        PositionRepository(session).upsert(
            Position(
                account_id="acct-1",
                instrument=instrument,
                quantity=Decimal("10"),
                average_cost=Decimal("150"),
                latest_price=Decimal("150"),
            )
        )
        session.commit()
        notion_sync = NotionSync(client=notion_client)
        workflow = RefreshAndSyncWorkflow(
            position_repository=PositionRepository(session),
            price_repository=PriceRepository(session),
            market_data_provider=FakeMarketDataProvider(
                {
                    "AAPL": PricePoint(
                        instrument=instrument,
                        price=Decimal("175"),
                        observed_at=datetime(2026, 7, 9, 14, 30, tzinfo=UTC),
                        provider="alpha_vantage",
                    )
                }
            ),
            daily_review_workflow=DailyReviewWorkflow(
                notion_sync=notion_sync,
                persistence=DailyReviewPersistence(
                    audit_event_repository=AuditEventRepository(session),
                    snapshot_repository=PortfolioSnapshotRepository(session),
                    signal_repository=SignalRepository(session),
                ),
            ),
            notion_sync=notion_sync,
            commit=session.commit,
        )

        workflow.run(stop_prices={"AAPL": Decimal("180")})

    assert notion_client.checked_visibility is True


def test_refresh_and_sync_does_not_call_notion_when_commit_fails(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'commit-failure.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    notion_client = FakeNotionClient()
    instrument = Instrument(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.EQUITY)

    with session_factory() as session:
        AccountRepository(session).upsert(
            Account(account_id="acct-1", name="Manual Account", source="csv")
        )
        PositionRepository(session).upsert(
            Position(
                account_id="acct-1",
                instrument=instrument,
                quantity=Decimal("10"),
                average_cost=Decimal("150"),
                latest_price=Decimal("150"),
            )
        )
        session.commit()
        notion_sync = NotionSync(client=notion_client)

        def fail_commit() -> None:
            raise RuntimeError("commit failed")

        workflow = RefreshAndSyncWorkflow(
            position_repository=PositionRepository(session),
            price_repository=PriceRepository(session),
            market_data_provider=FakeMarketDataProvider(
                {
                    "AAPL": PricePoint(
                        instrument=instrument,
                        price=Decimal("175"),
                        observed_at=datetime(2026, 7, 9, 14, 30, tzinfo=UTC),
                        provider="alpha_vantage",
                    )
                }
            ),
            daily_review_workflow=DailyReviewWorkflow(
                notion_sync=notion_sync,
                persistence=DailyReviewPersistence(
                    audit_event_repository=AuditEventRepository(session),
                    snapshot_repository=PortfolioSnapshotRepository(session),
                    signal_repository=SignalRepository(session),
                ),
            ),
            notion_sync=notion_sync,
            commit=fail_commit,
        )

        with pytest.raises(RuntimeError, match="commit failed"):
            workflow.run(stop_prices={"AAPL": Decimal("180")})

    assert notion_client.pages == {}


def test_refresh_and_sync_applies_and_clears_notion_portfolio_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    notion_client = FakeNotionClient(
        configured_databases={
            "Settings",
            "Accounts",
            "Positions",
            "Signals",
            "Daily Review",
        }
    )
    notion_client.seed_rows(
        "Settings",
        [
            NotionDatabaseRow(
                external_id="portfolio-settings",
                title="Portfolio Settings",
                properties={"Base Currency": "GBP"},
            )
        ],
    )
    notion_client.seed_rows(
        "Positions",
        [
            NotionDatabaseRow(
                external_id="position:U123:FREE",
                title="FREE",
                properties={"Cost Override": Decimal("0")},
            )
        ],
    )
    instrument = Instrument(
        symbol="FREE",
        name="Free Signup Share",
        asset_class=AssetClass.EQUITY,
        currency="USD",
    )

    with session_factory() as session:
        account_repository = AccountRepository(session)
        position_repository = PositionRepository(session)
        app_setting_repository = AppSettingRepository(session)
        account_repository.upsert(
            Account(
                account_id="U123",
                name="IBKR",
                source="ibkr_flex",
                base_currency="GBP",
            )
        )
        position_repository.upsert_broker_position(
            Position(
                account_id="U123",
                instrument=instrument,
                quantity=Decimal("1"),
                average_cost=Decimal("125"),
                cost_basis_status=CostBasisStatus.BROKER,
                latest_price=Decimal("140"),
            )
        )
        session.commit()
        notion_sync = NotionSync(notion_client)
        workflow = RefreshAndSyncWorkflow(
            position_repository=position_repository,
            price_repository=PriceRepository(session),
            market_data_provider=FakeMarketDataProvider(
                {
                    "FREE": PricePoint(
                        instrument=instrument,
                        price=Decimal("145"),
                        observed_at=datetime(2026, 7, 15, 12, tzinfo=UTC),
                        provider="manual",
                    )
                }
            ),
            daily_review_workflow=DailyReviewWorkflow(
                notion_sync=notion_sync,
                persistence=DailyReviewPersistence(
                    audit_event_repository=AuditEventRepository(session),
                    snapshot_repository=PortfolioSnapshotRepository(session),
                    signal_repository=SignalRepository(session),
                ),
            ),
            notion_sync=notion_sync,
            commit=session.commit,
            account_repository=account_repository,
            app_setting_repository=app_setting_repository,
        )

        workflow.run(stop_prices={})
        overridden = position_repository.list_open_positions()[0]

        assert overridden.average_cost == 0
        assert overridden.cost_basis_status == CostBasisStatus.MANUAL
        assert app_setting_repository.get(PORTFOLIO_BASE_CURRENCY_KEY) == "GBP"
        position_external_id = notion_sync.position_external_id(overridden)
        position_page = notion_client.pages["Positions"][position_external_id]
        assert {"Cost Override", "Theme", "Notes"}.isdisjoint(
            position_page.properties
        )

        original_query = notion_client.query_database

        def fail_query(database_name: str) -> list[NotionDatabaseRow]:
            raise NotionReadError(f"failed to read {database_name}")

        monkeypatch.setattr(notion_client, "query_database", fail_query)
        workflow.run(stop_prices={})
        retained = position_repository.list_open_positions()[0]
        assert retained.manual_average_cost == 0
        assert retained.cost_basis_status == CostBasisStatus.MANUAL
        monkeypatch.setattr(notion_client, "query_database", original_query)

        notion_client.seed_rows(
            "Positions",
            [
                NotionDatabaseRow(
                    external_id="position:U123:FREE",
                    title="FREE",
                    properties={"Cost Override": None},
                )
            ],
        )
        workflow.run(stop_prices={})
        cleared = position_repository.list_open_positions()[0]

    assert cleared.manual_average_cost is None
    assert cleared.average_cost == Decimal("125")
    assert cleared.cost_basis_status == CostBasisStatus.BROKER
    assert "Settings" in notion_client.pages
    assert "Accounts" in notion_client.pages
    assert "Positions" in notion_client.pages


def test_refresh_and_sync_uses_mapped_quotes_and_reporting_currency() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    notion_client = FakeNotionClient()
    observed_at = datetime(2026, 7, 15, 12, tzinfo=UTC)

    with session_factory() as session:
        accounts = AccountRepository(session)
        positions = PositionRepository(session)
        accounts.upsert(
            Account(
                account_id="U1",
                name="IBKR",
                source="ibkr-flex",
                base_currency="GBP",
            )
        )
        stored = positions.upsert_broker_position(
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
                latest_price=Decimal("55"),
                cost_basis_status=CostBasisStatus.BROKER,
            )
        )
        instrument_id = stored.instrument.instrument_id
        assert instrument_id is not None
        mappings = MarketDataMappingRepository(session)
        mappings.upsert(
            MarketDataMapping(
                instrument_id=instrument_id,
                provider="twelve_data",
                provider_symbol="SGLN",
                provider_exchange="LSE",
                expected_currency="GBX",
                price_multiplier=Decimal("0.01"),
            )
        )
        settings = AppSettingRepository(session)
        settings.set(PORTFOLIO_BASE_CURRENCY_KEY, "USD")
        session.commit()
        quote = PricePoint(
            instrument=stored.instrument,
            price=Decimal("6000"),
            observed_at=observed_at,
            provider="twelve_data",
            quote_currency="GBX",
            provider_symbol="SGLN",
            provider_exchange="LSE",
        )
        fx = FxRatePoint(
            base_currency="GBP",
            quote_currency="USD",
            rate=Decimal("1.30"),
            observed_at=observed_at,
            provider="twelve_data",
        )
        notion_sync = NotionSync(notion_client)
        workflow = RefreshAndSyncWorkflow(
            position_repository=positions,
            price_repository=PriceRepository(session),
            market_data_provider=FakeMappedMarketDataProvider(
                {instrument_id: quote},
                {("GBP", "USD"): fx},
            ),
            daily_review_workflow=DailyReviewWorkflow(
                notion_sync=notion_sync,
                persistence=DailyReviewPersistence(
                    audit_event_repository=AuditEventRepository(session),
                    snapshot_repository=PortfolioSnapshotRepository(session),
                    signal_repository=SignalRepository(session),
                ),
            ),
            notion_sync=notion_sync,
            commit=session.commit,
            account_repository=accounts,
            app_setting_repository=settings,
            market_data_mapping_repository=mappings,
            fx_rate_repository=FxRateRepository(session),
        )

        result = workflow.run(stop_prices={})
        refreshed = positions.list_open_positions()[0]

    assert refreshed.latest_price == Decimal("60")
    assert refreshed.latest_price_provider == "twelve_data"
    assert result.snapshot.base_currency == "USD"
    assert result.snapshot.nav == Decimal("780.00")
    assert result.snapshot.unrealized_pnl == Decimal("130.00")
    assert result.snapshot.reporting_coverage == Decimal("1")
